import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from src.config import get_settings
from src.observability.langfuse import start_span, end_span  # added

try:
    from groq import Groq
except ImportError:  # pragma: no cover
    Groq = None  # type: ignore

@dataclass
class JudgeResult:
    raw: str
    parsed: Dict[str, Any]
    latency_ms: float

RUBRIC_DESCRIPTION = {
    "fields": {
        "goal_alignment": "0-5: How well final answer addresses the original goal?",
        "tool_sequence_quality": "0-5: Logical ordering, minimal redundancy.",
        "reasoning_clarity": "0-5: Clear, actionable synthesis (even if truncated).",
        "action_efficiency": "0-5: Useful distinct tools / total steps; penalize wasted steps.",
        "memory_utilization": "0-5: Did answer benefit from prior context (if available)?",
        "risk_identification": "0-3: Identification of risks / constraints.",
        "overall": "0-10: Weighted aggregate not exceeding 10.",
        "feedback": "Array of short actionable improvement bullets (max 5)."
    }
}

SYSTEM_PROMPT = (
    "You are an impartial evaluator of inventory planning agent outputs. "
    "Return ONLY strict JSON with required numeric scores and feedback. "
    "Do NOT include any text outside JSON. Scores must respect bounds."
)

RUBRIC_WEIGHTS = {
    "goal_alignment": 0.25,
    "tool_sequence_quality": 0.2,
    "reasoning_clarity": 0.15,
    "action_efficiency": 0.15,
    "memory_utilization": 0.1,
    # Risk is on 0-3 scale; we normalize the value to 0-5 in _compute_overall,
    # so the weight should stay at the intended share (0.15), not scaled.
    "risk_identification": 0.15,
}

def _compute_overall(sc: Dict[str, Any]) -> float:
    total = 0.0
    for k, w in RUBRIC_WEIGHTS.items():
        if k in sc and isinstance(sc[k], (int, float)):
            # normalize risk_identification to 0-5 scale for weighting if needed
            val = sc[k]
            if k == 'risk_identification':
                val = (val / 3) * 5
            total += (val / 5.0) * w * 10.0
    return round(min(10.0, total), 2)

class LLMJudge:
    def __init__(self, client=None, model: Optional[str] = None):
        settings = get_settings()
        api_key = settings.groq_api_key
        self.client = client or (Groq(api_key=api_key) if Groq and api_key else None)
        self.model = model or settings.groq_model
        self._settings = settings

    def judge(self, goal: str, plan_result: Dict[str, Any], deterministic_metrics: Dict[str, Any]) -> JudgeResult:
        start = time.time()
        final_answer = plan_result.get('final_answer', '')
        steps = plan_result.get('steps', [])
        # Truncate large excerpts
        compact_steps: List[Dict[str, Any]] = []
        for s in steps:
            compact_steps.append({
                'step': s.get('step'),
                'action': s.get('action'),
                'reasoning': (s.get('reasoning') or '')[:180],
                'result_excerpt': (s.get('result_excerpt') or '')[:260]
            })
        payload = {
            'rubric': RUBRIC_DESCRIPTION,
            'goal': goal,
            'final_answer': final_answer[:1200],
            'steps': compact_steps,
            'metrics': deterministic_metrics,
            'instructions': 'Score each field within defined bounds. Provide feedback as array of <=5 short actionable bullet strings.'
        }
        if not self.client:
            # Rule fallback simple heuristic scoring
            heuristic = {
                'goal_alignment': 3,
                'tool_sequence_quality': 3,
                'reasoning_clarity': 3,
                'action_efficiency': 3,
                'memory_utilization': 2,
                'risk_identification': 1,
            }
            heuristic['overall'] = _compute_overall(heuristic)
            heuristic['feedback'] = ["LLM judge disabled; using heuristic baseline."]
            raw = json.dumps(heuristic)
            return JudgeResult(raw=raw, parsed=heuristic, latency_ms=round((time.time()-start)*1000,2))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        ]
        def _call():
            span = start_span("judge.call", input=messages, metadata={"model": self.model})
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.15,
                    max_tokens=getattr(self._settings, 'judge_max_tokens', 200),
                    top_p=0.9,
                    stream=False,
                )
                out = resp.choices[0].message.content.strip()
                end_span(span, output=out)
                return out
            except Exception as e:
                end_span(span, error=str(e))
                raise
        raw = _call()
        parsed = self._parse_json(raw)
        if not parsed:
            # retry once
            retry_payload = {"clarification": "Return ONLY JSON with rubric fields.", "original": payload}
            messages[1]['content'] = json.dumps(retry_payload, ensure_ascii=False)
            raw = _call()
            parsed = self._parse_json(raw) or {}
        # fill missing numeric fields with 0
        for f in ['goal_alignment','tool_sequence_quality','reasoning_clarity','action_efficiency','memory_utilization','risk_identification']:
            if f not in parsed or not isinstance(parsed.get(f), (int,float)):
                parsed[f] = 0
        # clamp to rubric bounds
        def _clamp(v, lo, hi):
            try:
                return max(lo, min(hi, float(v)))
            except Exception:
                return lo
        parsed['goal_alignment'] = _clamp(parsed['goal_alignment'], 0, 5)
        parsed['tool_sequence_quality'] = _clamp(parsed['tool_sequence_quality'], 0, 5)
        parsed['reasoning_clarity'] = _clamp(parsed['reasoning_clarity'], 0, 5)
        parsed['action_efficiency'] = _clamp(parsed['action_efficiency'], 0, 5)
        parsed['memory_utilization'] = _clamp(parsed['memory_utilization'], 0, 5)
        parsed['risk_identification'] = _clamp(parsed['risk_identification'], 0, 3)
        # compute overall from clamped scores
        parsed['overall'] = _compute_overall(parsed)
        # sanitize feedback list
        if 'feedback' not in parsed or not isinstance(parsed.get('feedback'), list):
            parsed['feedback'] = []
        else:
            parsed['feedback'] = [str(x)[:300] for x in parsed['feedback'][:5]]
        return JudgeResult(raw=raw, parsed=parsed, latency_ms=round((time.time()-start)*1000,2))

    @staticmethod
    def _parse_json(txt: str) -> Optional[Dict[str, Any]]:
        cand = txt.strip()
        if '```' in cand:
            parts = cand.split('```')
            for p in parts:
                p = p.strip()
                if p.startswith('{') and p.endswith('}'):
                    cand = p
                    break
        try:
            start = cand.find('{')
            end = cand.rfind('}')
            if start != -1 and end != -1 and end > start:
                return json.loads(cand[start:end+1])
        except Exception:
            return None
        return None
