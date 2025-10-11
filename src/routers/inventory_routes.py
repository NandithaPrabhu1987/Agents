from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List, Optional
import logging
import os
from uuid import uuid4
import hashlib
import json
from datetime import datetime
from pathlib import Path

from src.inventory_agent import (
    InventoryAgent, Store, Product, StoreLocation, ProductType
)
from src.data.seed import SAMPLE_STORES, SAMPLE_PRODUCTS
from src.services.ai_service import RuleBasedAIService
from src.config import get_settings
from src.agent.tools import TOOL_REGISTRY, invoke_tool
from src.retrieval.vector_store import get_vector_store  # Phase 2 retrieval
from src.agent.orchestrator import Orchestrator  # Phase 3+ LLM orchestrator
from src.agent.memory import get_memory  # Phase 4 memory endpoints
from src.auditing.writer import write_audit as _write_audit, context_digest as _context_digest
from src.observability.langfuse import get_langfuse, start_span, end_span  # updated

settings = get_settings()

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")
router = APIRouter()

# Initialize core services & sample data
inventory_agent = InventoryAgent()

AI_PROVIDER = settings.ai_provider.lower()
ai_service = None
GROQ_INIT_ERROR: Optional[str] = None
if AI_PROVIDER == "groq":
    try:
        from src.groq_service import GroqInventoryService  # only import when enabled
        ai_service = GroqInventoryService()
        logger.info("AI provider: GroqInventoryService")
    except Exception as e:
        GROQ_INIT_ERROR = str(e)
        logger.error(
            f"Groq provider failed to initialize: {GROQ_INIT_ERROR}. "
            "Rule-based fallback is disabled. Set AI_PROVIDER=rule to use deterministic mode."
        )
else:
    ai_service = RuleBasedAIService()
    logger.info("AI provider: RuleBasedAIService")

# Simple in-memory chat session store (session_id -> list[ {role, content} ])
CHAT_SESSIONS = {}
MAX_HISTORY_MESSAGES = settings.max_history_messages

AUDIT_BASE = settings.audit_base
AUDIT_BASE.mkdir(parents=True, exist_ok=True)

# session id -> meta (e.g., last assistant correlation id)
SESSION_META = {}

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("inventory_dashboard.html", {"request": request})

@router.get("/api/stores", response_model=List[Store])
async def get_stores():
    logger.info("Fetching all stores data")
    return SAMPLE_STORES

@router.get("/api/stores/status-summary")
async def stores_status_summary():
    try:
        summaries = [inventory_agent.analyze_store_inventory_status(store) for store in SAMPLE_STORES]
        status_counts = {}
        for summary in summaries:
            status = summary["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        logger.info(f"Generated status summary for {len(summaries)} stores")
        return {
            "total_stores": len(summaries),
            "status_breakdown": status_counts,
            "store_summaries": summaries,
            "critical_stores": [s for s in summaries if s["status"] in ["critical", "stockout"]],
            "balanced_stores": [s for s in summaries if s["status"] == "balanced"]
        }
    except Exception as e:
        logger.error(f"Error generating stores status summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating stores status summary: {str(e)}")

@router.get("/api/stores/{store_id}")
async def get_store_details(store_id: str):
    store = next((s for s in SAMPLE_STORES if s.id == store_id), None)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    analysis = inventory_agent.analyze_store_inventory_status(store)
    logger.info(f"Generated analysis for store {store_id}")
    return {"store_info": store, "analysis": analysis}

@router.get("/api/products", response_model=List[Product])
async def get_products():
    logger.info("Fetching all products data")
    return SAMPLE_PRODUCTS

@router.post("/api/transfers/recommend")
async def recommend_transfers(product_id: str):
    product = next((p for p in SAMPLE_PRODUCTS if p.id == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    recommendations = inventory_agent.recommend_inventory_transfers(SAMPLE_STORES, product)
    logger.info(f"Generated {len(recommendations)} transfer recommendations for product {product_id}")
    return {"product_id": product_id, "product_name": product.name, "recommendations": recommendations}

@router.post("/api/seasonal/optimize")
async def seasonal_optimization(product_id: str, season: Optional[str] = None):
    product = next((p for p in SAMPLE_PRODUCTS if p.id == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    optimization = inventory_agent.seasonal_inventory_optimization(SAMPLE_STORES, product, season)
    logger.info(f"Generated seasonal optimization for product {product_id}, season: {season}")
    return optimization

@router.post("/api/transfers/schedule")
async def generate_transfer_schedule(product_id: str, max_daily_transfers: int = 5):
    product = next((p for p in SAMPLE_PRODUCTS if p.id == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    recommendations = inventory_agent.recommend_inventory_transfers(SAMPLE_STORES, product)
    schedule = inventory_agent.generate_transfer_schedule(recommendations, max_daily_transfers)
    logger.info(f"Generated transfer schedule with {schedule['total_transfers']} transfers")
    return schedule

@router.get("/api/analysis/comprehensive")
async def comprehensive_analysis():
    analysis = inventory_agent.comprehensive_inventory_analysis(SAMPLE_STORES, SAMPLE_PRODUCTS)
    logger.info("Generated comprehensive inventory analysis")
    return analysis

@router.post("/api/query/monsoon-transfer")
async def monsoon_transfer_query():
    monsoon_product = next(p for p in SAMPLE_PRODUCTS if p.category == ProductType.MONSOON_GEAR)
    bangalore_store = next(s for s in SAMPLE_STORES if s.location == StoreLocation.BANGALORE)
    mysore_store = next(s for s in SAMPLE_STORES if s.location == StoreLocation.MYSORE)
    distance = inventory_agent.get_distance_between_stores(StoreLocation.MYSORE, StoreLocation.BANGALORE)
    transfer_cost = 50 * distance * inventory_agent.TRANSFER_COST_PER_KM
    potential_revenue = 50 * monsoon_product.selling_price
    result = {
        "query": "Transfer monsoon gear from Mysore to Bangalore",
        "scenario": {
            "product": monsoon_product.name,
            "from_store": mysore_store.name,
            "to_store": bangalore_store.name,
            "distance_km": distance,
            "recommended_quantity": 50,
            "transport_cost": round(transfer_cost, 2),
            "potential_revenue": round(potential_revenue, 2),
            "roi_ratio": round(potential_revenue / transfer_cost, 2),
            "delivery_time_hours": round(distance / 50, 1)
        },
        "analysis": f"Transfer 50 units of {monsoon_product.name} from {mysore_store.name} to {bangalore_store.name}. Distance: {distance}km, Cost: ₹{transfer_cost:,.2f}, Expected Revenue: ₹{potential_revenue:,.2f}, ROI: {potential_revenue/transfer_cost:.1f}x"
    }
    logger.info("Generated monsoon transfer query analysis")
    return result

@router.post("/api/query/festive-distribution")
async def festive_distribution_query():
    festive_product = next(p for p in SAMPLE_PRODUCTS if p.category == ProductType.FESTIVE_WEAR)
    optimization = inventory_agent.seasonal_inventory_optimization(SAMPLE_STORES, festive_product, "festive")
    stores_needing_stock = optimization["stores_needing_stock"]
    total_investment = sum(s["adjustment_needed"] * festive_product.unit_cost for s in stores_needing_stock)
    total_potential_revenue = sum(s["adjustment_needed"] * festive_product.selling_price for s in stores_needing_stock)
    result = {
        "query": "Optimize festive wear distribution for Diwali season",
        "season_analysis": optimization,
        "investment_summary": {
            "total_investment_needed": round(total_investment, 2),
            "total_potential_revenue": round(total_potential_revenue, 2),
            "expected_profit_margin": round(((total_potential_revenue - total_investment) / total_potential_revenue) * 100, 1),
            "stores_requiring_stock": len(stores_needing_stock)
        },
        "priority_stores": sorted(stores_needing_stock, key=lambda x: x["adjustment_needed"], reverse=True)[:3]
    }
    logger.info("Generated festive distribution query analysis")
    return result

@router.post("/api/chat/inventory")
async def inventory_chat(query: str = Form(...), session_id: Optional[str] = Form(None)):
    context = {
        "store_data": [inventory_agent.analyze_store_inventory_status(store) for store in SAMPLE_STORES],
        "products": [{"id": p.id, "name": p.name, "category": p.category.value} for p in SAMPLE_PRODUCTS]
    }
    new_session_created = False
    correlation_id = str(uuid4())
    ctx_digest = _context_digest(context)
    model_name = None
    if AI_PROVIDER == "groq":
        if ai_service is None:
            raise HTTPException(status_code=500, detail=f"Groq provider unavailable: {GROQ_INIT_ERROR}")
        # Fetch or create session history
        if not session_id:
            session_id = str(uuid4())
            CHAT_SESSIONS[session_id] = []
            SESSION_META[session_id] = {}
            new_session_created = True
        history = CHAT_SESSIONS.get(session_id, [])
        try:
            ai_response = await ai_service.analyze_inventory_scenario(query, context, history=history)
            model_name = getattr(ai_service, 'model', 'groq-model')
            # Update history (append user + assistant)
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": ai_response, "correlation_id": correlation_id})
            SESSION_META.setdefault(session_id, {})['last_correlation_id'] = correlation_id
            # Trim history if too long
            if len(history) > MAX_HISTORY_MESSAGES:
                CHAT_SESSIONS[session_id] = history[-MAX_HISTORY_MESSAGES:]
            else:
                CHAT_SESSIONS[session_id] = history
        except Exception as e:
            logger.error(f"Groq analysis failed: {e}")
            raise HTTPException(status_code=502, detail=f"Groq analysis failed: {str(e)}")
    else:
        try:
            ai_response = ai_service.generate_smart_response(query, context)
            model_name = 'rule-engine'
        except Exception as e:
            logger.error(f"Rule-based analysis failed: {e}")
            raise HTTPException(status_code=500, detail="Rule-based analysis failed")
    logger.info(f"Generated smart response for query: {query[:50]}...")
    record = {
        "type": "chat_response",
        "correlation_id": correlation_id,
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat(),
        "model": model_name,
        "query": query,
        "ai_analysis": ai_response[:2000],  # truncate in audit
        "context_digest": ctx_digest,
        "provider": AI_PROVIDER,
        "history_length": len(CHAT_SESSIONS.get(session_id, [])) if AI_PROVIDER == "groq" else 0
    }
    _write_audit(correlation_id, record)
    return {
        "query": query,
        "ai_analysis": ai_response,
        "context_used": {"digest": ctx_digest, "store_count": len(context['store_data']), "product_count": len(context['products'])},
        "session_id": session_id,
        "new_session": new_session_created,
        "history_length": record["history_length"],
        "correlation_id": correlation_id,
        "model": model_name
    }

@router.post("/api/chat/refine")
async def refine_chat(session_id: str = Form(...), instruction: str = Form(...)):
    if AI_PROVIDER != "groq":
        raise HTTPException(status_code=400, detail="Refinement requires AI_PROVIDER=groq")
    if ai_service is None:
        raise HTTPException(status_code=500, detail=f"Groq provider unavailable: {GROQ_INIT_ERROR}")
    history = CHAT_SESSIONS.get(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Session not found or empty")
    last_assistant = next((m.get("content") for m in reversed(history) if m.get("role") == "assistant"), None)
    parent_correlation_id = next((m.get("correlation_id") for m in reversed(history) if m.get("role") == "assistant" and m.get("correlation_id")), None)
    if not last_assistant:
        raise HTTPException(status_code=400, detail="No assistant response to refine")
    context = {
        "store_data": [inventory_agent.analyze_store_inventory_status(store) for store in SAMPLE_STORES],
        "products": [{"id": p.id, "name": p.name, "category": p.category.value} for p in SAMPLE_PRODUCTS]
    }
    correlation_id = str(uuid4())
    ctx_digest = _context_digest(context)
    try:
        refined = await ai_service.refine_previous(instruction, last_assistant, context)
        history.append({"role": "user", "content": instruction})
        history.append({"role": "assistant", "content": refined, "correlation_id": correlation_id, "parent_correlation_id": parent_correlation_id})
        if len(history) > MAX_HISTORY_MESSAGES:
            CHAT_SESSIONS[session_id] = history[-MAX_HISTORY_MESSAGES:]
        SESSION_META.setdefault(session_id, {})['last_correlation_id'] = correlation_id
        logger.info(f"Refined AI response for session {session_id}")
        record = {
            "type": "refine_response",
            "correlation_id": correlation_id,
            "parent_correlation_id": parent_correlation_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "model": getattr(ai_service, 'model', 'groq-model'),
            "instruction": instruction,
            "ai_analysis": refined[:2000],
            "context_digest": ctx_digest,
            "provider": AI_PROVIDER,
            "history_length": len(CHAT_SESSIONS[session_id])
        }
        _write_audit(correlation_id, record)
        return {
            "session_id": session_id,
            "instruction": instruction,
            "ai_analysis": refined,
            "history_length": len(CHAT_SESSIONS[session_id]),
            "correlation_id": correlation_id,
            "parent_correlation_id": parent_correlation_id
        }
    except Exception as e:
        logger.error(f"Groq refinement failed: {e}")
        raise HTTPException(status_code=502, detail=f"Groq refinement failed: {str(e)}")

@router.post("/api/chat/plan")
async def inventory_plan(query: str = Form(...)):
    if AI_PROVIDER != "groq":
        raise HTTPException(status_code=400, detail="AI planning requires AI_PROVIDER=groq")
    if ai_service is None:
        raise HTTPException(status_code=500, detail=f"Groq provider unavailable: {GROQ_INIT_ERROR}")

    # Build compact context for LLM
    context = {
        "store_data": [inventory_agent.analyze_store_inventory_status(store) for store in SAMPLE_STORES],
        "products": [{"id": p.id, "name": p.name, "category": p.category.value} for p in SAMPLE_PRODUCTS]
    }

    try:
        plan = await ai_service.analyze_and_propose_plan(query, context)
    except Exception as e:
        logger.error(f"Groq planning failed: {e}")
        raise HTTPException(status_code=502, detail=f"Groq planning failed: {str(e)}")

    # Resolve product
    product: Optional[Product] = None
    pid = plan.get("product_id") if isinstance(plan, dict) else None
    pname = plan.get("product") if isinstance(plan, dict) else None
    if pid:
        product = next((p for p in SAMPLE_PRODUCTS if p.id == pid), None)
    if not product and pname:
        product = next((p for p in SAMPLE_PRODUCTS if p.name.lower() == str(pname).lower()), None)
    if not product:
        # fallback: choose monsoon gear as default
        product = next(iter(SAMPLE_PRODUCTS), None)
    if not product:
        raise HTTPException(status_code=500, detail="No products available to validate plan")

    from_names = [str(n) for n in plan.get("from_stores", [])] if isinstance(plan, dict) else []
    to_names = [str(n) for n in plan.get("to_stores", [])] if isinstance(plan, dict) else []
    quantity_cap = int(plan.get("quantity_cap", 0)) if isinstance(plan, dict) else 0
    priority = str(plan.get("priority", "medium")) if isinstance(plan, dict) else "medium"

    # Build lookups
    name_to_store = {s.name: s for s in SAMPLE_STORES}
    loc_to_store = {s.location.value: s for s in SAMPLE_STORES}

    def resolve_store(name: str) -> Optional[Store]:
        return name_to_store.get(name) or loc_to_store.get(name)

    from_stores: List[Store] = [resolve_store(n) for n in from_names if resolve_store(n)]
    to_stores: List[Store] = [resolve_store(n) for n in to_names if resolve_store(n)]

    # If model omitted names, heuristically choose top surplus and top deficit stores
    if not from_stores or not to_stores:
        analyses = [inventory_agent.analyze_store_inventory_status(s) for s in SAMPLE_STORES]
        surplus_sorted = sorted(
            [a for a in analyses if a["current_stock"] > a["optimal_stock"]],
            key=lambda x: x["current_stock"] - x["optimal_stock"],
            reverse=True,
        )
        deficit_sorted = sorted(
            [a for a in analyses if a["stock_gap"] > 0],
            key=lambda x: (x["urgency"] == "urgent", x["stock_gap"]),
            reverse=True,
        )
        if not from_stores and surplus_sorted:
            from_stores = [name_to_store.get(a["store_name"]) for a in surplus_sorted[:2] if name_to_store.get(a["store_name"]) ]
        if not to_stores and deficit_sorted:
            to_stores = [name_to_store.get(a["store_name"]) for a in deficit_sorted[:2] if name_to_store.get(a["store_name"]) ]

    # Compute feasible transfers within cap
    analyses_map = {s.id: inventory_agent.analyze_store_inventory_status(s) for s in SAMPLE_STORES}
    cap_remaining = max(quantity_cap, 0) or 100  # default small cap if not provided
    feasible_transfers = []

    for src in from_stores:
        src_analysis = analyses_map[src.id]
        available = max(0, src_analysis["current_stock"] - src_analysis["optimal_stock"])
        if available <= 0:
            continue
        for dst in to_stores:
            if src.id == dst.id:
                continue
            dst_analysis = analyses_map[dst.id]
            need = max(0, dst_analysis["optimal_stock"] - dst_analysis["current_stock"])
            if need <= 0:
                continue
            qty = min(available, need, cap_remaining)
            if qty <= 0:
                continue
            distance = inventory_agent.get_distance_between_stores(dst.location, src.location)
            cost = qty * distance * inventory_agent.TRANSFER_COST_PER_KM
            revenue = qty * product.selling_price
            feasible_transfers.append({
                "product_id": product.id,
                "product_name": product.name,
                "from_store": src.name,
                "to_store": dst.name,
                "from_location": src.location.value,
                "to_location": dst.location.value,
                "transfer_quantity": qty,
                "distance_km": distance,
                "transport_cost": round(cost, 2),
                "potential_revenue": round(revenue, 2),
                "roi_ratio": round(revenue / max(cost, 1), 2),
                "priority": priority,
            })
            cap_remaining -= qty
            available -= qty
            if cap_remaining <= 0:
                break
        if cap_remaining <= 0:
            break

    # Build summary string for UI
    if feasible_transfers:
        top = feasible_transfers[:3]
        bullets = []
        for t in top:
            bullets.append(
                f"- {t['from_store']} → {t['to_store']}: {t['transfer_quantity']} units, {t['distance_km']}km, ROI {t['roi_ratio']}x"
            )
        summary = (
            f"Proposed plan for {product.name} (cap {quantity_cap or 'default'}).\n" +
            "\n".join(bullets)
        )
    else:
        summary = "No feasible transfers found for the proposed plan."

    response = {
        "query": query,
        "plan": plan,
        "validation": {
            "product_id": product.id,
            "product_name": product.name,
            "from_stores": [s.name for s in from_stores],
            "to_stores": [s.name for s in to_stores],
            "feasible_transfers": feasible_transfers,
            "cap_remaining": cap_remaining,
        },
        "ai_analysis": summary,
    }

    # Add traceability
    correlation_id = str(uuid4())
    ctx_digest = _context_digest(context)
    response["correlation_id"] = correlation_id
    response["context_digest"] = ctx_digest
    response["model"] = getattr(ai_service, 'model', 'groq-model') if AI_PROVIDER == 'groq' else 'rule-engine'
    audit_record = {
        "type": "plan_response",
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat(),
        "model": response["model"],
        "query": query,
        "plan_raw": response.get("plan"),
        "feasible_count": len(response.get("validation", {}).get("feasible_transfers", [])),
        "context_digest": ctx_digest,
        "provider": AI_PROVIDER,
        "ai_summary": response.get("ai_analysis", "")[:1000]
    }
    _write_audit(correlation_id, audit_record)
    logger.info(f"Generated AI plan and validation for query: {query[:60]}... corr={correlation_id}")
    return response

@router.post("/api/chat/plan+retrieve")
async def inventory_plan_with_retrieval(query: str = Form(...), top_k: int = Form(3)):
    if AI_PROVIDER != "groq":
        raise HTTPException(status_code=400, detail="AI planning requires AI_PROVIDER=groq")
    if ai_service is None:
        raise HTTPException(status_code=500, detail=f"Groq provider unavailable: {GROQ_INIT_ERROR}")

    base_context = {
        "store_data": [inventory_agent.analyze_store_inventory_status(store) for store in SAMPLE_STORES],
        "products": [{"id": p.id, "name": p.name, "category": p.category.value} for p in SAMPLE_PRODUCTS]
    }
    # Retrieval augmentation
    vs = get_vector_store()
    retrieved = vs.similarity_search(query, top_k=top_k)
    retrieval_block = [
        {"id": r["id"], "score": r["score"], "snippet": r["content_snippet"], "metadata": r.get("metadata")}
        for r in retrieved
    ]
    context = {**base_context, "retrieved_docs": retrieval_block}

    try:
        plan = await ai_service.analyze_and_propose_plan(query, context)
    except Exception as e:
        logger.error(f"Groq planning (retrieval) failed: {e}")
        raise HTTPException(status_code=502, detail=f"Groq planning failed: {str(e)}")

    # Reuse existing validation logic by lightly adapting (inline minimal duplication)
    product: Optional[Product] = None
    pid = plan.get("product_id") if isinstance(plan, dict) else None
    pname = plan.get("product") if isinstance(plan, dict) else None
    if pid:
        product = next((p for p in SAMPLE_PRODUCTS if p.id == pid), None)
    if not product and pname:
        product = next((p for p in SAMPLE_PRODUCTS if p.name.lower() == str(pname).lower()), None)
    if not product:
        product = next(iter(SAMPLE_PRODUCTS), None)
    if not product:
        raise HTTPException(status_code=500, detail="No products available to validate plan")

    from_names = [str(n) for n in plan.get("from_stores", [])] if isinstance(plan, dict) else []
    to_names = [str(n) for n in plan.get("to_stores", [])] if isinstance(plan, dict) else []
    quantity_cap = int(plan.get("quantity_cap", 0)) if isinstance(plan, dict) else 0
    priority = str(plan.get("priority", "medium")) if isinstance(plan, dict) else "medium"

    name_to_store = {s.name: s for s in SAMPLE_STORES}
    loc_to_store = {s.location.value: s for s in SAMPLE_STORES}

    def resolve_store(name: str) -> Optional[Store]:
        return name_to_store.get(name) or loc_to_store.get(name)

    from_stores: List[Store] = [resolve_store(n) for n in from_names if resolve_store(n)]
    to_stores: List[Store] = [resolve_store(n) for n in to_names if resolve_store(n)]

    # If model omitted names, heuristically choose top surplus and top deficit stores
    if not from_stores or not to_stores:
        analyses = [inventory_agent.analyze_store_inventory_status(s) for s in SAMPLE_STORES]
        surplus_sorted = sorted(
            [a for a in analyses if a["current_stock"] > a["optimal_stock"]],
            key=lambda x: x["current_stock"] - x["optimal_stock"],
            reverse=True,
        )
        deficit_sorted = sorted(
            [a for a in analyses if a["stock_gap"] > 0],
            key=lambda x: (x["urgency"] == "urgent", x["stock_gap"]),
            reverse=True,
        )
        if not from_stores and surplus_sorted:
            from_stores = [name_to_store.get(a["store_name"]) for a in surplus_sorted[:2] if name_to_store.get(a["store_name"]) ]
        if not to_stores and deficit_sorted:
            to_stores = [name_to_store.get(a["store_name"]) for a in deficit_sorted[:2] if name_to_store.get(a["store_name"]) ]

    # Compute feasible transfers within cap
    analyses_map = {s.id: inventory_agent.analyze_store_inventory_status(s) for s in SAMPLE_STORES}
    cap_remaining = max(quantity_cap, 0) or 100  # default small cap if not provided
    feasible_transfers = []

    for src in from_stores:
        src_analysis = analyses_map[src.id]
        available = max(0, src_analysis["current_stock"] - src_analysis["optimal_stock"])
        if available <= 0:
            continue
        for dst in to_stores:
            if src.id == dst.id:
                continue
            dst_analysis = analyses_map[dst.id]
            need = max(0, dst_analysis["optimal_stock"] - dst_analysis["current_stock"])
            if need <= 0:
                continue
            qty = min(available, need, cap_remaining)
            if qty <= 0:
                continue
            distance = inventory_agent.get_distance_between_stores(dst.location, src.location)
            cost = qty * distance * inventory_agent.TRANSFER_COST_PER_KM
            revenue = qty * product.selling_price
            feasible_transfers.append({
                "product_id": product.id,
                "product_name": product.name,
                "from_store": src.name,
                "to_store": dst.name,
                "from_location": src.location.value,
                "to_location": dst.location.value,
                "transfer_quantity": qty,
                "distance_km": distance,
                "transport_cost": round(cost, 2),
                "potential_revenue": round(revenue, 2),
                "roi_ratio": round(revenue / max(cost, 1), 2),
                "priority": priority,
            })
            cap_remaining -= qty
            available -= qty
            if cap_remaining <= 0:
                break
        if cap_remaining <= 0:
            break

    # Build summary string for UI
    if feasible_transfers:
        top = feasible_transfers[:3]
        bullets = [f"- {t['from_store']} → {t['to_store']}: {t['transfer_quantity']} units, {t['distance_km']}km, ROI {t['roi_ratio']}x" for t in top]
        summary = (
            f"(Retrieval-Augmented) Plan for {product.name} (cap {quantity_cap or 'default'}).\nRetrieved {len(retrieval_block)} related docs.\n" + "\n".join(bullets)
        )
    else:
        summary = f"No feasible transfers found. Retrieved {len(retrieval_block)} docs; consider adding more operational data."

    correlation_id = str(uuid4())
    ctx_digest = _context_digest(context)
    response = {
        "query": query,
        "plan": plan,
        "validation": {
            "product_id": product.id,
            "product_name": product.name,
            "from_stores": [s.name for s in from_stores],
            "to_stores": [s.name for s in to_names],
            "feasible_transfers": feasible_transfers,
            "cap_remaining": cap_remaining,
        },
        "retrieval": {"documents": retrieval_block, "top_k": top_k},
        "ai_analysis": summary,
        "correlation_id": correlation_id,
        "context_digest": ctx_digest,
        "model": getattr(ai_service, 'model', 'groq-model')
    }
    audit_record = {
        "type": "plan_retrieval_response",
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat(),
        "model": response["model"],
        "query": query,
        "retrieved_count": len(retrieval_block),
        "feasible_count": len(feasible_transfers),
        "context_digest": ctx_digest,
        "provider": AI_PROVIDER,
        "ai_summary": response.get("ai_analysis", "")[:1000]
    }
    _write_audit(correlation_id, audit_record)
    logger.info(f"Generated retrieval-augmented plan for query: {query[:60]}... corr={correlation_id}")
    return response

@router.get("/api/audit/{correlation_id}")
async def get_audit_record(correlation_id: str):
    for day in sorted(AUDIT_BASE.glob('*'))[::-1]:  # search latest days first
        candidate = day / f"{correlation_id}.json"
        if candidate.exists():
            try:
                with candidate.open('r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed reading audit record: {e}")
    raise HTTPException(status_code=404, detail="Audit record not found")

@router.get("/api/agent/tools")
async def list_tools():
    return [
        {"name": t["name"], "description": t["description"], "schema": (t["input_model"].model_json_schema() if t["input_model"] else None)}
        for t in TOOL_REGISTRY
    ]

@router.post("/api/agent/tools/invoke")
async def call_tool(tool_name: str = Form(...), payload: str = Form("{}")):
    try:
        import json as _json
        data = _json.loads(payload or '{}')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
    result = invoke_tool(tool_name, data)
    if 'error' in result:
        return {"tool": tool_name, "success": False, "result": result}
    return {"tool": tool_name, "success": True, "result": result}

@router.post("/api/agent/auto-plan")
async def auto_plan(goal: str = Form(...), max_steps: Optional[int] = Form(None)):
    if AI_PROVIDER != "groq":  # restrict to groq LLM mode
        raise HTTPException(status_code=400, detail="Auto planning requires AI_PROVIDER=groq")
    if ai_service is None:
        raise HTTPException(status_code=500, detail=f"Groq provider unavailable: {GROQ_INIT_ERROR}")
    # Re-enable full LLM-driven Orchestrator (replaces previous SimpleOrchestrator deterministic path)
    orchestrator = Orchestrator(model_client=getattr(ai_service, 'client', None), model_name=getattr(ai_service, 'model', None))
    steps_cap = max_steps or settings.max_auto_steps
    try:
        result = await orchestrator.run(goal, max_steps=steps_cap)
    except Exception:
        logger.exception("Auto-plan LLM orchestration failed")
        raise HTTPException(status_code=500, detail="Auto-plan failed (LLM orchestration)")
    correlation_id = str(uuid4())
    mem = get_memory()
    mem_stats = mem.stats()
    audit_payload = {
        "type": "auto_plan_llm",
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat(),
        "goal": goal,
        "steps_count": len(result.get("steps", [])),
        "used_tools": result.get("used_tools", []),
        "retrieval_docs_count": len(result.get("retrieval_docs", [])),
        "final_answer_excerpt": result.get("final_answer", "")[:800],
        "model": getattr(ai_service, 'model', 'groq-model'),
        "max_steps_requested": steps_cap,
        "memory_total_items": mem_stats.get('total_items'),
        "memory_avg_importance": mem_stats.get('avg_importance'),
    }
    _write_audit(correlation_id, audit_payload)
    result["correlation_id"] = correlation_id
    return result

@router.post("/api/eval/auto-plan")
async def eval_auto_plan(goal: str = Form(...), max_steps: Optional[int] = Form(None)):
    if AI_PROVIDER != "groq":
        raise HTTPException(status_code=400, detail="Evaluation requires AI_PROVIDER=groq")
    if ai_service is None:
        raise HTTPException(status_code=500, detail=f"Groq provider unavailable: {GROQ_INIT_ERROR}")
    orchestrator = Orchestrator(model_client=getattr(ai_service, 'client', None), model_name=getattr(ai_service, 'model', None))
    steps_cap = max_steps or settings.max_auto_steps
    try:
        plan_result = await orchestrator.run(goal, max_steps=steps_cap)
    except Exception:
        logger.exception("Eval auto-plan orchestration failed")
        raise HTTPException(status_code=500, detail="Planning failed")
    # Deterministic metrics
    steps = plan_result.get('steps', [])
    distinct_tools = len({s.get('action',{}).get('tool_name') for s in steps if s.get('action',{}).get('type')=='tool'})
    total_tool_steps = sum(1 for s in steps if s.get('action',{}).get('type')=='tool')
    efficiency = round(distinct_tools / max(1,total_tool_steps), 3)
    core_present = all(any(s.get('action',{}).get('tool_name')==t for s in steps) for t in ["comprehensive_analysis","recommend_transfers"])
    deterministic_metrics = {
        "step_count": len(steps),
        "distinct_tools": distinct_tools,
        "tool_steps": total_tool_steps,
        "action_efficiency_ratio": efficiency,
        "core_tools_present": core_present,
    }
    from src.eval.judge import LLMJudge
    judge = LLMJudge(client=getattr(ai_service,'client',None), model=getattr(ai_service,'model',None))
    jr = judge.judge(goal, plan_result, deterministic_metrics)
    correlation_id = str(uuid4())
    audit_payload = {
        "type": "eval_plan",
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat(),
        "goal": goal,
        "deterministic_metrics": deterministic_metrics,
        "judge_scores": jr.parsed,
        "judge_latency_ms": jr.latency_ms,
        "model": getattr(ai_service,'model','groq-model')
    }
    _write_audit(correlation_id, audit_payload)
    return {
        "goal": goal,
        "plan": plan_result,
        "metrics": deterministic_metrics,
        "judge": jr.parsed,
        "judge_latency_ms": jr.latency_ms,
        "correlation_id": correlation_id
    }

@router.get("/api/memory/recent")
async def memory_recent(limit: int = 10):
    mem = get_memory()
    return {"items": mem.recent(limit=limit)}

@router.get("/api/memory/query")
async def memory_query(q: str, limit: int = 5):
    mem = get_memory()
    return {"query": q, "results": mem.query(q, limit=limit)}

@router.get("/api/memory/stats")
async def memory_stats():
    mem = get_memory()
    return mem.stats()

@router.post("/api/memory/summarize")
async def memory_summarize():
    # Placeholder for future summarization logic
    return {"status": "ok", "message": "Summarization not yet implemented"}

@router.post("/api/stores/update_stock")
async def update_store_stock(store_id: str = Form(...), new_stock: int = Form(...), auto_recalc: bool = Form(True)):
    if new_stock < 0:
        raise HTTPException(status_code=400, detail="new_stock must be >= 0")
    store = next((s for s in SAMPLE_STORES if s.id == store_id), None)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    try:
        store.current_stock = new_stock  # mutate in-memory
        analysis = inventory_agent.analyze_store_inventory_status(store)
        # Recompute summary if requested
        summary = None
        if auto_recalc:
            summaries = [inventory_agent.analyze_store_inventory_status(s) for s in SAMPLE_STORES]
            status_counts = {}
            for sm in summaries:
                status = sm["status"]
                status_counts[status] = status_counts.get(status, 0) + 1
            summary = {
                "total_stores": len(summaries),
                "status_breakdown": status_counts,
                "critical_stores": [s for s in summaries if s["status"] in ["critical", "stockout"]],
                "balanced_stores": [s for s in summaries if s["status"] == "balanced"]
            }
        logger.info(f"Updated stock for store {store_id} -> {new_stock}")
        record = {
            "type": "stock_adjustment",
            "correlation_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "store_id": store_id,
            "new_stock": new_stock,
            "auto_recalc": auto_recalc
        }
        _write_audit(record["correlation_id"], record)
        return {"store": store, "analysis": analysis, "summary": summary}
    except Exception as e:
        logger.exception("Stock update failed")
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")

@router.get("/api/diag/langfuse")
async def diag_langfuse():
    try:
        s = get_settings()
        enabled = bool(s.langfuse_host and s.langfuse_public_key and s.langfuse_secret_key)
        lf = get_langfuse()
        trace_id = None
        span_created = False
        if lf:
            try:
                trace_id = lf.get_current_trace_id()
            except Exception:
                trace_id = None
            sp = start_span("diag.span", input={"ping": "ok"}, metadata={"component": "diag"})
            if sp:
                span_created = True
                end_span(sp, output="ok")
            try:
                lf.flush()
            except Exception:
                pass
        return {"enabled": enabled, "trace_id": trace_id, "span_created": span_created, "host": s.langfuse_host}
    except Exception as e:
        logger.error(f"Langfuse diag failed: {e}")
        return {"enabled": False, "error": str(e)}
