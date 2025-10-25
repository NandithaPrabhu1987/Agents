import json
from groq import Groq
from .config import get_settings

SYS_PROMPT = (
    "You are an inventory agent managing ONE product across TWO stores. "
    "State fields: week, store1_stock, store2_stock, demand_s1, demand_s2. "
    "Your goal is to minimize unmet demand using explicit transfers planned by you (no automatic redistribution). "
    "Planning policy (LLM-only): "
    "1) Compute each store's pre-consumption deficit = max(demand - stock, 0) and each store's surplus = max(stock - demand, 0). "
    "2) Fill the LARGEST deficit first by pulling from the store with the LARGEST surplus. "
    "3) Never overdraw a donor: limit transfers to its current surplus so it can still meet its own demand. "
    "4) Clamp amounts to integers; never make stocks negative. "
    "5) Sequence actions as: optionally set_demand, then one or more transfer steps, then run_weeks. "
    "6) If the goal mentions 'run' (e.g., 'run 2 weeks'), you MUST include a run_weeks action with that number. "
    "7) If no transfers are needed, still return run_weeks (do NOT return only 'explain'). "
    "Return compact JSON: either a single action object or {\"actions\":[...]} list. "
    "Allowed actions: "
    "- set_demand: params {s1:int, s2:int} "
    "- transfer: params {from: 's1|s2', to: 's1|s2', amount:int} "
    "- run_weeks: params {weeks:int} "
    "Each action may include a short 'rationale'. Keep outputs minimal and strictly JSON if possible."
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

    def plan(self, state, user_goal):
        user = {"role": "user", "content": json.dumps({"state": state, "goal": user_goal}, ensure_ascii=False)}
        sys = {"role": "system", "content": SYS_PROMPT}
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[sys, user],
            temperature=0.2,
            max_tokens=256,
        )
        text = resp.choices[0].message.content.strip()
        cand = text
        if '```' in cand:
            for p in cand.split('```'):
                p = p.strip()
                if p.startswith('{') and p.endswith('}'):
                    cand = p
                    break
        try:
            raw = json.loads(cand)
            return _normalize_plan(raw)
        except Exception:
            return {"action": "explain", "params": {}, "rationale": text[:600]}
