from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List, Optional
import logging
import os

from src.inventory_agent import (
    InventoryAgent, Store, Product, StoreLocation, ProductType
)
from src.data.seed import SAMPLE_STORES, SAMPLE_PRODUCTS
from src.services.ai_service import RuleBasedAIService

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")
router = APIRouter()

# Initialize core services & sample data
inventory_agent = InventoryAgent()

AI_PROVIDER = os.getenv("AI_PROVIDER", "rule").lower()
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
async def inventory_chat(query: str = Form(...)):
    context = {
        "store_data": [inventory_agent.analyze_store_inventory_status(store) for store in SAMPLE_STORES],
        "products": [{"id": p.id, "name": p.name, "category": p.category.value} for p in SAMPLE_PRODUCTS]
    }
    if AI_PROVIDER == "groq":
        if ai_service is None:
            raise HTTPException(status_code=500, detail=f"Groq provider unavailable: {GROQ_INIT_ERROR}")
        try:
            ai_response = await ai_service.analyze_inventory_scenario(query, context)
        except Exception as e:
            logger.error(f"Groq analysis failed: {e}")
            raise HTTPException(status_code=502, detail=f"Groq analysis failed: {str(e)}")
    else:
        try:
            ai_response = ai_service.generate_smart_response(query, context)
        except Exception as e:
            logger.error(f"Rule-based analysis failed: {e}")
            raise HTTPException(status_code=500, detail="Rule-based analysis failed")
    logger.info(f"Generated smart response for query: {query[:50]}...")
    return {"query": query, "ai_analysis": ai_response, "context_used": context}
