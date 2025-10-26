import json
from groq import Groq
from .config import get_settings

SYS_PROMPT = (
    "Inventory manager for 2 stores. Return JSON actions array.\n"
    "\n"
    "When user says 'set demand s1=X s2=Y':\n"
    "Return: {\"actions\":[{\"action\":\"set_demand\",\"params\":{\"s1\":X,\"s2\":Y}}]}\n"
    "\n"
    "When user says 'run N weeks', ALWAYS check if transfer needed FIRST:\n"
    "1. S1 deficit = max(0, demand_s1 × N - store1_stock)\n"
    "2. S2 deficit = max(0, demand_s2 × N - store2_stock)\n"
    "3. S1 surplus = max(0, store1_stock - demand_s1)\n"
    "4. S2 surplus = max(0, store2_stock - demand_s2)\n"
    "5. If S1 deficit > 0 AND S2 surplus > 0: add transfer action with amount = min(S1 deficit, S2 surplus)\n"
    "6. If S2 deficit > 0 AND S1 surplus > 0: add transfer action with amount = min(S2 deficit, S1 surplus)\n"
    "7. Then add run_weeks action\n"
    "\n"
    "Example: store1_stock=100, demand_s1=80, store2_stock=200, demand_s2=10, user says 'run 5 weeks'\n"
    "S1 deficit = 80×5 - 100 = 300, S2 surplus = 200 - 10 = 190\n"
    "Return: {\"actions\":[{\"action\":\"transfer\",\"params\":{\"from\":\"s2\",\"to\":\"s1\",\"amount\":190}},{\"action\":\"run_weeks\",\"params\":{\"weeks\":5}}]}\n"
    "\n"
    "Available actions: set_demand, transfer, run_weeks"
)


def _normalize_plan(plan: dict) -> dict:
    """Return a copy of plan with canonical action names and params."""
    if not isinstance(plan, dict):
        return plan

    alias = {
        "run": "run_weeks",
        "runweek": "run_weeks",
        "runweeks": "run_weeks",
        "run_week": "run_weeks",
        "advance": "run_weeks",
        "advance_week": "run_weeks",
        "advance_weeks": "run_weeks",
        "run_weeks": "run_weeks",
        "set-demand": "set_demand",
        "setdemand": "set_demand",
        "demand": "set_demand",
        "set_demand": "set_demand",
        "move": "transfer",
        "reallocate": "transfer",
        "redistribute": "transfer",
        "transfer_stock": "transfer",
        "shift": "transfer",
        "transfer": "transfer",
        "explain": "explain",
    }

    def norm_step(step: dict) -> dict:
        if not isinstance(step, dict):
            return step
        raw_action = (step.get("action") or "").strip().lower()
        action = alias.get(raw_action, raw_action)
        params = step.get("params") if isinstance(step.get("params"), dict) else {}

        # Infer action when missing based on params or rationale
        if not action:
            if any(k in params for k in ("weeks", "w", "week", "n", "num_weeks", "count")):
                action = "run_weeks"
            elif any(k in params for k in ("s1", "store1", "store1_demand", "demand_s1", "s2", "store2", "store2_demand", "demand_s2")):
                action = "set_demand"
            elif any(k in params for k in ("from", "src", "from_store", "to", "dst", "to_store", "amount", "qty", "quantity", "units")):
                action = "transfer"
            elif isinstance(step.get("rationale"), str) and "run" in step["rationale"].lower():
                action = "run_weeks"

        out = {"action": action}
        if "rationale" in step:
            out["rationale"] = step.get("rationale")
        if action == "run_weeks":
            w = (
                params.get("weeks") or params.get("w") or params.get("week") or params.get("n") or params.get("num_weeks") or params.get("count") or 1
            )
            try:
                w = int(w)
            except Exception:
                w = 1
            out["params"] = {"weeks": max(1, w)}
        elif action == "set_demand":
            s1 = params.get("s1") or params.get("store1") or params.get("store1_demand") or params.get("demand_s1") or 0
            s2 = params.get("s2") or params.get("store2") or params.get("store2_demand") or params.get("demand_s2") or 0
            try:
                s1 = int(s1)
            except Exception:
                s1 = 0
            try:
                s2 = int(s2)
            except Exception:
                s2 = 0
            out["params"] = {"s1": s1, "s2": s2}
        elif action == "transfer":
            src = params.get("from") or params.get("src") or params.get("from_store")
            dst = params.get("to") or params.get("dst") or params.get("to_store")
            amt = params.get("amount") or params.get("qty") or params.get("quantity") or params.get("units") or 0
            try:
                amt = int(amt)
            except Exception:
                amt = 0
            out["params"] = {"from": src, "to": dst, "amount": amt}
        else:
            # explain or unknown -> keep params as-is
            if isinstance(params, dict):
                out["params"] = params
        return out

    if "actions" in plan and isinstance(plan.get("actions"), list):
        return {"actions": [norm_step(x) for x in plan.get("actions") or []]}
    # single action object
    return norm_step(plan)


class LLMPlanner:
    def __init__(self, model=None):
        s = get_settings()
        self.model = model or s.groq_model
        if not s.groq_api_key:
            raise ValueError("GROQ_API_KEY not set")
        self.client = Groq(api_key=s.groq_api_key)
        
        # Guardrails configuration
        self.max_prompt_length = 2000
        self.max_weeks = 52  # Maximum weeks to simulate
        self.max_demand = 1000  # Maximum demand per store
        self.max_transfer = 500  # Maximum transfer amount
        self.forbidden_keywords = [
            "delete", "drop", "truncate", "exec", "eval", "import", 
            "system", "os.", "subprocess", "__", "file", "open("
        ]
        
        # Prompt injection / jailbreak patterns
        self.prompt_injection_patterns = [
            "ignore previous", "ignore all previous", "disregard previous", 
            "forget previous", "forget everything", "forget all",
            "new instructions", "new instruction", "new role", "new task",
            "you are now", "act as", "pretend to be", "roleplay as",
            "system:", "assistant:", "user:", "[system]", "[assistant]",
            "repeat your instructions", "show your prompt", "your system prompt",
            "what are your instructions", "reveal your", "bypass",
            "jailbreak", "override", "admin mode", "developer mode",
            "god mode", "sudo", "root access"
        ]

    def _validate_prompt(self, user_goal: str) -> tuple[bool, str]:
        """Validate user prompt for safety and constraints."""
        if not user_goal or not isinstance(user_goal, str):
            return False, "Prompt cannot be empty"
        
        # Length check
        if len(user_goal) > self.max_prompt_length:
            return False, f"Prompt too long (max {self.max_prompt_length} characters)"
        
        # Check for forbidden keywords (case-insensitive)
        user_goal_lower = user_goal.lower()
        for keyword in self.forbidden_keywords:
            if keyword in user_goal_lower:
                return False, f"Forbidden keyword detected: '{keyword}'"
        
        # Check for prompt injection / jailbreak attempts
        for pattern in self.prompt_injection_patterns:
            if pattern in user_goal_lower:
                return False, f"Prompt injection attempt detected: '{pattern}'"
        
        # Check for potential injection patterns
        suspicious_patterns = ["{{", "}}", "${", "<%", "%>", "<script", "javascript:"]
        for pattern in suspicious_patterns:
            if pattern in user_goal_lower:
                return False, f"Suspicious pattern detected: '{pattern}'"
        
        return True, "Valid"

    def _validate_plan(self, plan: dict) -> tuple[bool, str]:
        """Validate the generated plan for safety and business rules."""
        if not isinstance(plan, dict):
            return False, "Invalid plan format"
        
        actions = plan.get("actions", [plan]) if "actions" in plan else [plan]
        
        # Check for forbidden explain action
        for action in actions:
            if isinstance(action, dict):
                action_type = action.get("action", "").lower()
                if action_type == "explain":
                    return False, "AI returned 'explain' action which is forbidden. Only executable actions allowed: set_demand, transfer, run_weeks"
        
        # Check for bidirectional transfers (illogical)
        transfer_directions = []
        
        for action in actions:
            if not isinstance(action, dict):
                continue
                
            action_type = action.get("action", "").lower()
            params = action.get("params", {})
            
            # Validate set_demand action
            if action_type == "set_demand":
                s1 = params.get("s1", 0)
                s2 = params.get("s2", 0)
                if s1 < 0 or s2 < 0:
                    return False, "Demand cannot be negative"
                if s1 > self.max_demand or s2 > self.max_demand:
                    return False, f"Demand exceeds maximum allowed ({self.max_demand})"
            
            # Validate transfer action
            elif action_type == "transfer":
                amount = params.get("amount", 0)
                if amount < 0:
                    return False, "Transfer amount cannot be negative"
                if amount > self.max_transfer:
                    return False, f"Transfer amount exceeds maximum ({self.max_transfer})"
                src = params.get("from", "")
                dst = params.get("to", "")
                if not src or not dst:
                    return False, "Transfer requires valid source and destination"
                if str(src).lower() == str(dst).lower():
                    return False, "Cannot transfer to the same store"
                
                # Track transfer direction to detect bidirectional transfers
                direction = f"{str(src).lower()}->{str(dst).lower()}"
                reverse_direction = f"{str(dst).lower()}->{str(src).lower()}"
                
                if reverse_direction in transfer_directions:
                    return False, "Bidirectional transfers are illogical! Cannot transfer S1→S2 AND S2→S1 in the same plan"
                
                transfer_directions.append(direction)
            
            # Validate run_weeks action
            elif action_type == "run_weeks":
                weeks = params.get("weeks", 1)
                if weeks < 1:
                    return False, "Weeks must be at least 1"
                if weeks > self.max_weeks:
                    return False, f"Cannot simulate more than {self.max_weeks} weeks"
        
        return True, "Valid"

    def plan(self, state, user_goal):
        # Validate input prompt
        is_valid, error_msg = self._validate_prompt(user_goal)
        if not is_valid:
            return {
                "action": "explain", 
                "params": {}, 
                "rationale": f"⚠️ Prompt validation failed: {error_msg}"
            }
        
        # Sanitize the prompt (strip extra whitespace, limit length)
        sanitized_goal = user_goal.strip()[:self.max_prompt_length]
        
        try:
            user = {"role": "user", "content": json.dumps({"state": state, "goal": sanitized_goal}, ensure_ascii=False)}
            sys = {"role": "system", "content": SYS_PROMPT}
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[sys, user],
                temperature=0,  # Deterministic output
                max_tokens=512,  # Increased for detailed rationale
            )
            text = resp.choices[0].message.content.strip()
            cand = text
            
            # Extract JSON from markdown code blocks
            if '```' in cand:
                for p in cand.split('```'):
                    p = p.strip()
                    if p.startswith('json'):
                        p = p[4:].strip()
                    if p.startswith('{') and p.endswith('}'):
                        cand = p
                        break
            
            # Try to parse the JSON
            raw = json.loads(cand)
            
            # If LLM returned "explain" with embedded JSON, extract it
            if isinstance(raw, dict) and raw.get("action") == "explain":
                rationale = raw.get("rationale", "")
                # Look for JSON in the rationale
                if "```json" in rationale or "```" in rationale:
                    for p in rationale.split('```'):
                        p = p.strip()
                        if p.startswith('json'):
                            p = p[4:].strip()
                        if p.startswith('{') and p.endswith('}'):
                            try:
                                embedded = json.loads(p)
                                if "actions" in embedded or "action" in embedded:
                                    raw = embedded
                                    break
                            except:
                                pass
            
            normalized_plan = _normalize_plan(raw)
            
            # Validate the generated plan
            is_valid_plan, plan_error = self._validate_plan(normalized_plan)
            if not is_valid_plan:
                return {
                    "action": "explain", 
                    "params": {}, 
                    "rationale": f"⚠️ Plan validation failed: {plan_error}"
                }
            
            return normalized_plan
            
        except json.JSONDecodeError:
            return {"action": "explain", "params": {}, "rationale": text[:600]}
        except Exception as e:
            return {
                "action": "explain", 
                "params": {}, 
                "rationale": f"⚠️ Error generating plan: {str(e)[:200]}"
            }
