from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..llm_agent import LLMPlanner
from ..simple_agent import SimpleInventoryAgent
from ..config import get_settings
import json

router = APIRouter()
templates = Jinja2Templates(directory="templates")
_agent = SimpleInventoryAgent()


def _extract_json(text: str):
    if not text:
        return None
    cand = text.strip()
    if '```' in cand:
        for p in cand.split('```'):
            p = p.strip()
            if p.startswith('{') and p.endswith('}'):
                try:
                    return json.loads(p)
                except Exception:
                    pass
    try:
        return json.loads(cand)
    except Exception:
        return None


def _normalize_action_and_params(step: dict):
    """Return (action, params) with canonical action names and normalized params keys/values."""
    if not isinstance(step, dict):
        return "", {}
    raw_action = (step.get("action") or step.get("type") or "").strip().lower()
    params = (step.get("params") or {}) if isinstance(step.get("params"), dict) else {}

    # Map common aliases to canonical actions
    alias_map = {
        "run": "run_weeks",
        "runweek": "run_weeks",
        "runweeks": "run_weeks",
        "run_week": "run_weeks",
        "run_weeks": "run_weeks",
        "advance": "run_weeks",
        "advance_week": "run_weeks",
        "advance_weeks": "run_weeks",
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
    action = alias_map.get(raw_action, raw_action)

    # Infer action if missing but params reveal intent
    if not action:
        if any(k in params for k in ("weeks", "w", "week", "n", "num_weeks", "count")):
            action = "run_weeks"
        elif any(k in params for k in ("s1", "store1", "store1_demand", "demand_s1", "s2", "store2", "store2_demand", "demand_s2")):
            action = "set_demand"
        elif any(k in params for k in ("from", "src", "from_store", "to", "dst", "to_store", "amount", "qty", "quantity", "units")):
            action = "transfer"

    # Normalize parameter keys per action
    if action == "run_weeks":
        w = (
            params.get("weeks")
            or params.get("w")
            or params.get("week")
            or params.get("n")
            or params.get("num_weeks")
            or params.get("count")
            or 1
        )
        try:
            w = int(w)
        except Exception:
            w = 1
        params = {"weeks": max(1, w)}
    elif action == "set_demand":
        s1 = (
            params.get("s1")
            or params.get("store1")
            or params.get("store1_demand")
            or params.get("demand_s1")
            or 0
        )
        s2 = (
            params.get("s2")
            or params.get("store2")
            or params.get("store2_demand")
            or params.get("demand_s2")
            or 0
        )
        try:
            s1 = int(s1)
        except Exception:
            s1 = 0
        try:
            s2 = int(s2)
        except Exception:
            s2 = 0
        params = {"s1": s1, "s2": s2}
    elif action == "transfer":
        src = params.get("from") or params.get("src") or params.get("from_store")
        dst = params.get("to") or params.get("dst") or params.get("to_store")
        amt = params.get("amount") or params.get("qty") or params.get("quantity") or params.get("units") or 0
        try:
            amt = int(amt)
        except Exception:
            amt = 0
        params = {"from": src, "to": dst, "amount": amt}
    else:
        # leave params as-is for explain/unknown
        params = params or {}

    return action, params


def _apply_single(step: dict):
    action, params = _normalize_action_and_params(step)
    if action == "set_demand":
        s1 = int(params.get("s1") or 0)
        s2 = int(params.get("s2") or 0)
        return _agent.set_demand(s1, s2)
    if action == "transfer":
        src = params.get("from") or params.get("src")
        dst = params.get("to") or params.get("dst")
        amount = params.get("amount") or params.get("qty") or 0
        if not src or not dst:
            return {"ok": False, "message": "transfer requires 'from' and 'to'"}
        return _agent.transfer(str(src), str(dst), int(amount))
    if action == "run_weeks":
        w = int(params.get("weeks") or params.get("w") or 1)
        return _agent.step_week(w)
    if action == "explain":
        plan_text = step.get("rationale") or params.get("rationale")
        parsed = _extract_json(plan_text) if plan_text else None
        if isinstance(parsed, dict) and (parsed.get("action") or parsed.get("actions")):
            return _apply_plan(parsed)
        return {"ok": True, "message": step.get("rationale") or "No changes"}
    return {"ok": False, "message": "Unknown action"}


def _apply_plan(plan: dict):
    results = []
    actions = plan.get("actions") if isinstance(plan, dict) else None
    try:
        if isinstance(actions, list):
            for step in actions:
                single = _apply_single(step or {})
                # Flatten nested plans returned from 'explain' parsing
                if isinstance(single, dict) and isinstance(single.get("steps"), list):
                    results.extend(single.get("steps") or [])
                else:
                    results.append(single)
        else:
            single = _apply_single(plan or {})
            if isinstance(single, dict) and isinstance(single.get("steps"), list):
                results.extend(single.get("steps") or [])
            else:
                results.append(single)
        return {"ok": True, "steps": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("simple_agent.html", {"request": request})


@router.get("/api/simple/status")
async def simple_status():
    return _agent.status()


@router.post("/api/simple/reset")
async def simple_reset():
    return _agent.reset()


@router.post("/api/simple/prompt")
async def simple_prompt(prompt: str = Form(...)):
    # Validation guardrails
    if not prompt or len(prompt.strip()) == 0:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    
    if len(prompt) > 2000:
        raise HTTPException(status_code=400, detail="Prompt too long (max 2000 characters)")
    
    # Rate limiting check (basic)
    sanitized_prompt = prompt.strip()[:2000]
    
    status_obj = _agent.status()
    plain_state = status_obj.get("state", {})
    try:
        planner = LLMPlanner()
        plan = planner.plan(plain_state, sanitized_prompt)
        
        # Check if plan validation failed
        if plan.get("action") == "explain" and "validation failed" in plan.get("rationale", "").lower():
            raise HTTPException(status_code=400, detail=plan.get("rationale"))
        
        applied = _apply_plan(plan)
        return {"mode": "groq", "plan": plan, "result": applied, "state": _agent.status()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM planning failed: {str(e)[:200]}")


@router.post("/api/simple/llm")
async def llm_analyze(request: Request):
    data = await request.json()
    question = (data.get("question") or "").strip()
    
    # Validation guardrails
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="Question too long (max 2000 characters)")
    
    status_obj = _agent.status()
    plain_state = status_obj.get("state", {})
    try:
        planner = LLMPlanner()
        plan = planner.plan(plain_state, question)
        
        # Check if plan validation failed
        if plan.get("action") == "explain" and "validation failed" in plan.get("rationale", "").lower():
            return {"ok": False, "error": plan.get("rationale"), "state": status_obj}
        
        return {"ok": True, "plan": plan, "state": status_obj}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "state": status_obj}


@router.post("/api/simple/apply")
async def simple_apply(request: Request):
    body = await request.json()
    
    # Validation guardrails
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Plan must be a valid JSON object")
    
    # Validate actions array if present
    actions = body.get("actions", [body]) if "actions" in body else [body]
    if len(actions) > 50:
        raise HTTPException(status_code=400, detail="Too many actions (max 50)")
    
    try:
        applied = _apply_plan(body)
        return {"ok": applied.get("ok", False), "result": applied, "state": _agent.status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply plan: {str(e)[:200]}")
