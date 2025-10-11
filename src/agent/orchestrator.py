import json
import asyncio
from typing import List, Dict, Any, Optional
from uuid import uuid4
from datetime import datetime
import logging

from src.config import get_settings
from src.agent.tools import TOOL_REGISTRY, invoke_tool
from src.retrieval.vector_store import get_vector_store
from src.data.seed import SAMPLE_PRODUCTS  # added for product mapping
from src.agent.memory import get_memory  # Phase 4 memory integration
from src.observability.langfuse import start_span, end_span  # added

logger = logging.getLogger(__name__)

class OrchestrationError(Exception):
    pass

class Orchestrator:
    """Phase 3 multi-step autonomous planner.

    Loop:
      - LLM decides next action (tool / retrieve / final)
      - Execute action (invoke tool / retrieval)
      - Append step record
      - Stop on final or step cap
    """
    def __init__(self, model_client=None, model_name: Optional[str] = None):
        self.settings = get_settings()
        self.max_steps_default = self.settings.max_auto_steps
        self.model_client = model_client  # optional injected client (Groq)
        self.model_name = model_name or self.settings.groq_model
        self._last_product_id: Optional[str] = None  # remember last resolved product
        # Build product reference map
        self._products_index = {p.id: p for p in SAMPLE_PRODUCTS}
        self._keyword_map = {}
        for p in SAMPLE_PRODUCTS:
            base_tokens = set([t.lower() for t in p.name.split() if len(t) > 2])
            base_tokens.add(p.category.value.lower())
            for tok in base_tokens:
                self._keyword_map.setdefault(tok, set()).add(p.id)

    async def run(self, goal: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
        max_steps = max_steps or self.max_steps_default
        max_steps = max(1, min(15, max_steps))
        steps: List[Dict[str, Any]] = []
        used_tools: List[str] = []
        retrieval_docs: List[Dict[str, Any]] = []
        working_tool_results: List[Dict[str, Any]] = []
        memory = get_memory()
        forced_sequence = ["comprehensive_analysis", "recommend_transfers"]  # enforce first two logical steps for grounding

        for step_index in range(1, max_steps + 1):
            try:
                decision = await self._decide_next(goal, steps, working_tool_results, retrieval_docs, final_attempt=(step_index == max_steps))
            except Exception:
                logger.exception(f"Decision phase failed at step {step_index}")
                raise
            raw_model = decision.pop('_raw_model', None)
            action_type = decision.get("action_type")
            # Enforce deterministic first steps if not following expected pattern
            if step_index <= len(forced_sequence):
                required_tool = forced_sequence[step_index - 1]
                if action_type != "tool" or decision.get("tool_name") != required_tool:
                    inferred = self._last_product_id or self._infer_product_id(goal)
                    tool_input: Dict[str, Any] = {}
                    if required_tool != "comprehensive_analysis" and inferred:
                        tool_input["product_id"] = inferred
                    decision = {"action_type": "tool", "tool_name": required_tool, "tool_input": tool_input, "reasoning": f"Forced sequence: {required_tool}"}
                    action_type = "tool"
            # Validate action_type; fallback if invalid (after enforcing sequence)
            if action_type not in {"tool", "retrieve", "final"}:
                decision = self._heuristic_fallback(goal, steps, working_tool_results, retrieval_docs, final_attempt=(step_index == max_steps))
                decision['_origin'] = 'fallback'
                action_type = decision.get('action_type')

            try:
                if action_type == "tool":
                    tool_name = decision.get("tool_name")
                    tool_input = decision.get("tool_input") or {}
                    # normalize tool input (ensure dict)
                    if not isinstance(tool_input, dict):
                        tool_input = {}
                    # Auto-fill product_id if required and missing
                    if tool_name in {"recommend_transfers", "seasonal_optimize", "generate_transfer_schedule"}:
                        if "product_id" not in tool_input or not tool_input.get("product_id"):
                            if self._last_product_id:
                                tool_input["product_id"] = self._last_product_id
                            else:
                                inferred = self._infer_product_id(goal)
                                if inferred:
                                    tool_input["product_id"] = inferred
                    # Map fuzzy reference to real product id
                    resolved = self._resolve_product(tool_input.get("product_id"))
                    if resolved:
                        tool_input["product_id"] = resolved
                    result = invoke_tool(tool_name, tool_input)
                    # memory record
                    try:
                        memory.add_tool_result(tool_name, result, goal=goal)
                    except Exception:
                        logger.debug("Memory add_tool_result failed", exc_info=True)
                    excerpt = json.dumps(result, ensure_ascii=False)[:600]
                    steps.append({
                        "step": step_index,
                        "reasoning": decision.get("reasoning"),
                        "action": {"type": "tool", "tool_name": tool_name, "input": tool_input},
                        "result_excerpt": excerpt,
                        "raw_model": (raw_model or '')[:400]
                    })
                    # update last product id if success
                    if 'error' not in result and tool_name in {"recommend_transfers", "seasonal_optimize", "generate_transfer_schedule", "comprehensive_analysis"}:
                        if tool_name != "comprehensive_analysis":
                            self._last_product_id = tool_input.get("product_id", self._last_product_id)
                        used_tools.append(tool_name)
                    working_tool_results.append({"tool": tool_name, "output": result})
                elif action_type == "retrieve":
                    query = decision.get("retrieve_query") or goal
                    top_k = int(decision.get("top_k", 3))
                    vs = get_vector_store()
                    matches = vs.similarity_search(query, top_k=top_k)
                    retrieval_docs.extend(matches)
                    steps.append({
                        "step": step_index,
                        "reasoning": decision.get("reasoning"),
                        "action": {"type": "retrieve", "query": query, "top_k": top_k},
                        "result_excerpt": json.dumps(matches, ensure_ascii=False)[:600],
                        "raw_model": (raw_model or '')[:400]
                    })
                elif action_type == "final":
                    final_answer = decision.get("final_answer") or decision.get("reasoning") or "No answer produced"
                    steps.append({
                        "step": step_index,
                        "reasoning": decision.get("reasoning"),
                        "action": {"type": "final"},
                        "result_excerpt": final_answer[:600],
                        "raw_model": (raw_model or '')[:400]
                    })
                    return {
                        "final_answer": final_answer,
                        "steps": steps,
                        "used_tools": used_tools,
                        "retrieval_docs": retrieval_docs[:10],
                    }
            except Exception:
                logger.exception(f"Execution phase failed at step {step_index} for action {action_type}")
                raise
        synthesized = self._synthesize_answer(goal, steps, working_tool_results, retrieval_docs)
        try:
            memory.add_summary(synthesized, goal=goal)
        except Exception:
            logger.debug("Memory add_summary failed", exc_info=True)
        return {
            "final_answer": synthesized,
            "steps": steps,
            "used_tools": used_tools,
            "retrieval_docs": retrieval_docs[:10],
        }

    def _heuristic_fallback(self, goal: str, steps: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], retrieval_docs: List[Dict[str, Any]], *, final_attempt: bool) -> Dict[str, Any]:
        """Provide a safe next action when model output is invalid.
        Preference order: comprehensive_analysis -> recommend_transfers -> retrieve -> final.
        """
        used = [tr.get('tool') for tr in tool_results]
        if 'comprehensive_analysis' not in used:
            return {
                "action_type": "tool",
                "tool_name": "comprehensive_analysis",
                "tool_input": {},
                "reasoning": "Fallback: run baseline comprehensive analysis"
            }
        if 'recommend_transfers' not in used:
            ti: Dict[str, Any] = {}
            inferred = self._last_product_id or self._infer_product_id(goal)
            if inferred:
                ti["product_id"] = inferred
            return {
                "action_type": "tool",
                "tool_name": "recommend_transfers",
                "tool_input": ti,
                "reasoning": "Fallback: propose transfers for inferred product"
            }
        if not retrieval_docs:
            return {
                "action_type": "retrieve",
                "retrieve_query": goal,
                "top_k": 3,
                "reasoning": "Fallback: retrieve small set of related docs"
            }
        if final_attempt:
            return {
                "action_type": "final",
                "final_answer": "Fallback final: baseline analysis and transfers considered.",
                "reasoning": "Fallback: last attempt"
            }
        # Default: nudge another consolidate step
        return {
            "action_type": "final",
            "final_answer": "Fallback final: sufficient info compiled for initial actions.",
            "reasoning": "Fallback default"
        }

    def _resolve_product(self, ref: Optional[str]) -> Optional[str]:
        if not ref:
            return None
        ref_l = ref.lower().strip()
        # direct id
        if ref in self._products_index:
            return ref
        for pid, prod in self._products_index.items():
            if pid.lower() == ref_l:
                return pid
            n = prod.name.lower()
            if n == ref_l or ref_l in n:
                return pid
            if prod.category.value.lower() == ref_l:
                return pid
        # keyword match
        if ref_l in self._keyword_map:
            # choose first deterministic sorted
            return sorted(self._keyword_map[ref_l])[0]
        return None

    def _infer_product_id(self, text: str) -> Optional[str]:
        words = {w.strip('.,').lower() for w in text.split()}
        scores = {}
        for w in words:
            if w in self._keyword_map:
                for pid in self._keyword_map[w]:
                    scores[pid] = scores.get(pid, 0) + 1
        if not scores:
            return None
        return max(scores.items(), key=lambda x: x[1])[0]

    async def _decide_next(self, goal: str, steps: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], retrieval_docs: List[Dict[str, Any]], *, final_attempt: bool) -> Dict[str, Any]:
        settings = self.settings
        memory = get_memory()
        # Reduce memory chars to keep prompt small
        mem_char_cap = min(settings.memory_max_prompt_chars, 600)
        memory_slice = memory.select_relevant(goal, settings.memory_relevance_limit, mem_char_cap, settings.memory_half_life_hours)
        if self.model_client is None:  # Heuristic fallback (rule mode)
            if not tool_results:
                return {"action_type": "tool", "tool_name": "comprehensive_analysis", "tool_input": {}, "reasoning": "Start with overall inventory picture", "_raw_model": "rule-fallback", "memory_used": memory_slice}
            return {"action_type": "final", "final_answer": "Heuristic summary: performed analysis; integrate LLM for richer reasoning.", "reasoning": "Fallback final due to missing LLM", "_raw_model": "rule-fallback", "memory_used": memory_slice}
        # Defensive: coerce tool_results to list if somehow a dict leaked in
        if not isinstance(tool_results, list):
            logger.warning(f"Orchestrator: tool_results not list (type={type(tool_results)}); coercing to empty list")
            tool_results_list: List[Dict[str, Any]] = []
        else:
            tool_results_list = tool_results
        # Keep tool catalog concise (name + short description)
        available_tools_summary = []
        for t in TOOL_REGISTRY:
            desc = (t["description"] or "")[:120]
            available_tools_summary.append({"name": t["name"], "description": desc})
        # Provide a small product catalog to LLM to encourage correct ids
        product_catalog = [
            {"id": p.id, "name": p.name, "category": p.category.value} for p in SAMPLE_PRODUCTS[:6]
        ]
        # Trim context sizes further
        recent_tool_results = [{"tool": r.get("tool"), "output": r.get("output") } for r in tool_results_list[-2:]] if tool_results_list else []
        tool_names_used = [r.get('tool') for r in tool_results_list]
        prompt = {
            "goal": goal,
            "current_step": len(steps) + 1,
            "previous_steps": steps[-2:],
            "recent_tool_results": recent_tool_results,
            "retrieved_docs": retrieval_docs[-1:],
            "products": product_catalog,
            "available_tools": available_tools_summary,
            "already_used_tools": tool_names_used,
            "schema_required": {
                "action_type": "tool|retrieve|final",
                "reasoning": "short rationale",
                "tool_name": "required if action_type=tool",
                "tool_input": {"only": "JSON object if action_type=tool"},
                "retrieve_query": "string if action_type=retrieve",
                "top_k": "int (1-5) if action_type=retrieve (default 3)",
                "final_answer": "string if action_type=final"
            },
            "rules": [
                "NEVER invent tool names outside available_tools list",
                "Use only product.id field exactly as given when needed",
                "Prefer at least 2 tools before final unless goal trivially satisfied or final_attempt is true",
                "Consider a retrieval step if additional context could refine recommendations and none retrieved yet",
                "Return ONLY compact JSON with required fields for the chosen action_type"
            ],
            "examples": [
                {"action_type": "tool", "tool_name": "comprehensive_analysis", "tool_input": {}, "reasoning": "baseline overview first"},
                {"action_type": "retrieve", "retrieve_query": "festive wear stock imbalance causes", "top_k": 3, "reasoning": "gather context"},
                {"action_type": "final", "final_answer": "Summary of actions and recommendations", "reasoning": "enough info compiled"}
            ],
            "memory_context": memory_slice,
            "min_core_tools_before_final": settings.min_core_tools_before_final,
        }
        if final_attempt:
            prompt["final_attempt"] = True
        system_msg = {
            "role": "system",
            "content": (
                "You are an autonomous inventory optimization planner. Return ONLY VALID STRICT JSON. "
                "Allowed action_type values: tool, retrieve, final. Do not add commentary outside JSON." )
        }
        user_content = json.dumps(prompt, ensure_ascii=False)
        # Safety clamp: reduce user content length if very large
        if len(user_content) > 5000:
            user_content = user_content[:5000]
        user_msg = {"role": "user", "content": user_content}
        raw = await asyncio.to_thread(self._call_model, [system_msg, user_msg])
        logger.debug(f"Orchestrator raw model output: {raw[:500]}")
        decision = self._parse_json_block(raw)
        if not decision:
            # retry with clarification
            retry_msg = {"role": "user", "content": json.dumps({"clarification": "Previous output invalid JSON. Return ONLY compact JSON now.", "original_prompt": prompt}, ensure_ascii=False)}
            raw2 = await asyncio.to_thread(self._call_model, [system_msg, retry_msg])
            decision = self._parse_json_block(raw2) or {"action_type": "final", "final_answer": "Unable to parse model planning output", "reasoning": "Parsing failed twice"}
            decision['_raw_model'] = raw2
        else:
            decision['_raw_model'] = raw
            if decision.get("action_type") == "tool":
                ti = decision.get("tool_input")
                if isinstance(ti, dict) and "product_id" in ti:
                    resolved = self._resolve_product(ti.get("product_id"))
                    if resolved:
                        ti["product_id"] = resolved
        if decision and decision.get("action_type") == "final":
            core_used = sum(1 for t in tool_results if t.get('tool') in {"comprehensive_analysis", "recommend_transfers"})
            if core_used < settings.min_core_tools_before_final and not final_attempt:
                needed = "comprehensive_analysis" if all(tr.get('tool') != 'comprehensive_analysis' for tr in tool_results) else "recommend_transfers"
                tool_input = {}
                if needed == "recommend_transfers":
                    inferred = self._infer_product_id(goal)
                    if inferred:
                        tool_input["product_id"] = inferred
                decision = {"action_type": "tool", "tool_name": needed, "tool_input": tool_input, "reasoning": "Enforced core tool before final", "_raw_model": decision.get('_raw_model')}
        if decision:
            decision['memory_used'] = memory_slice
        return decision

    def _call_model(self, messages: List[Dict[str, str]]) -> str:
        max_tokens = getattr(self.settings, 'planner_max_tokens', 250)
        max_tokens = min(max_tokens, 150)
        span = start_span("planner.call", input=messages, metadata={"model": self.model_name})
        try:
            resp = self.model_client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.15,
                max_tokens=max_tokens,
                top_p=0.9,
                stream=False,
            )
            text = resp.choices[0].message.content.strip()
            end_span(span, output=text)
            return text
        except Exception as e:
            end_span(span, error=str(e))
            raise

    @staticmethod
    def _parse_json_block(text: str) -> Optional[Dict[str, Any]]:
        candidate = text.strip()
        if '```' in candidate:
            parts = candidate.split('```')
            for part in parts:
                part = part.strip()
                if part.startswith('{') and part.endswith('}'):
                    candidate = part
                    break
        try:
            start = candidate.find('{')
            end = candidate.rfind('}')
            if start != -1 and end != -1 and end > start:
                return json.loads(candidate[start:end+1])
        except Exception:
            return None
        return None

    @staticmethod
    def _synthesize_answer(goal: str, steps: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], retrieval_docs: List[Dict[str, Any]]) -> str:
        lines = [f"Goal: {goal}", "Outcome: Step cap reached."]
        if tool_results:
            tool_names = [r['tool'] for r in tool_results]
            lines.append(f"Tools used: {', '.join(tool_names)}")
        if retrieval_docs:
            lines.append(f"Retrieved docs: {len(retrieval_docs)} snippets")
        lines.append("Consider enabling LLM for richer final synthesis.")
        return "\n".join(lines)

class SimpleOrchestrator:
    """Deterministic lightweight planner (reverted simpler version).
    Sequence (bounded by max_steps):
      1. comprehensive_analysis
      2. recommend_transfers (inferred product)
      3. seasonal_optimize (same product, monsoon season if relevant)
      4. generate_transfer_schedule (optional if capacity)
      Final: synthesize answer.
    No LLM calls; safe for rule or groq mode.
    """
    def __init__(self):
        self._products_index = {p.id: p for p in SAMPLE_PRODUCTS}
        self._monsoon_id = self._infer_product_id("monsoon") or next(iter(self._products_index.keys()))

    def _infer_product_id(self, text: str) -> Optional[str]:
        text_l = text.lower()
        for p in SAMPLE_PRODUCTS:
            if p.category.value.lower().startswith("monsoon") or "monsoon" in p.name.lower():
                return p.id
        return None

    def run(self, goal: str, max_steps: int = 4) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = []
        used_tools: List[str] = []
        product_id = self._infer_product_id(goal) or self._monsoon_id

        def _add_step(name: str, payload: Dict[str, Any]):
            result = invoke_tool(name, payload)
            steps.append({
                "step": len(steps)+1,
                "action": {"type": "tool", "tool_name": name, "input": payload},
                "result_excerpt": json.dumps(result, ensure_ascii=False)[:500]
            })
            if 'error' not in result:
                used_tools.append(name)
            return result

        if max_steps >= 1:
            _add_step("comprehensive_analysis", {})
        if max_steps >= 2:
            _add_step("recommend_transfers", {"product_id": product_id})
        if max_steps >= 3:
            _add_step("seasonal_optimize", {"product_id": product_id, "season": "monsoon"})
        if max_steps >= 4:
            _add_step("generate_transfer_schedule", {"product_id": product_id, "max_daily_transfers": 5})

        final_answer = (
            f"Goal: {goal}\nExecuted {len(steps)} deterministic steps for product {product_id}. "
            f"Tools used: {', '.join(used_tools)}. Review individual step outputs for details." )
        return {
            "final_answer": final_answer,
            "steps": steps,
            "used_tools": used_tools,
            "retrieval_docs": [],
            "product_id": product_id
        }
