from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from src.inventory_agent import InventoryAgent, Store, Product, ProductType
from src.data.seed import SAMPLE_STORES, SAMPLE_PRODUCTS
from src.retrieval.vector_store import get_vector_store

inventory_agent = InventoryAgent()

# ---- Pydantic Schemas for tool inputs ----
class ProductInput(BaseModel):
    product_id: str

class SeasonalOptimizeInput(BaseModel):
    product_id: str
    season: Optional[str] = None

class TransferScheduleInput(BaseModel):
    product_id: str
    max_daily_transfers: int = 5

class PlanValidationInput(BaseModel):
    product_id: str
    from_stores: List[str]
    to_stores: List[str]
    quantity_cap: int = 100

# Phase 2 retrieval schemas
class AddDocumentInput(BaseModel):
    content: str
    source: Optional[str] = None
    doc_type: Optional[str] = None

class RetrieveRelevantInput(BaseModel):
    query: str
    top_k: int = 3

# ---- Utility lookups ----
PRODUCT_INDEX = {p.id: p for p in SAMPLE_PRODUCTS}
STORE_INDEX = {s.name: s for s in SAMPLE_STORES}

# Category / keyword quick map for fuzzy resolution
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    ProductType.MONSOON_GEAR.value: ["monsoon", "rain", "raincoat"],
    ProductType.FESTIVE_WEAR.value: ["festive", "ethnic", "diwali"],
    ProductType.SUMMER_ESSENTIALS.value: ["summer", "cotton"],
    ProductType.WINTER_WEAR.value: ["winter", "wool"],
    ProductType.ELECTRONICS.value: ["electronic", "gadget"],
    ProductType.HOME_DECOR.value: ["decor", "home"],
    ProductType.FOOTWEAR.value: ["shoe", "footwear"],
    ProductType.ACCESSORIES.value: ["accessory", "accessories"],
}

_DEF_PRODUCT_BY_CATEGORY: Dict[str, Product] = {}
for p in SAMPLE_PRODUCTS:
    _DEF_PRODUCT_BY_CATEGORY.setdefault(p.category.value, p)


def _resolve_product(ref: str) -> Optional[Product]:
    if not ref:
        return None
    ref_l = ref.lower().strip()
    # direct id
    if ref in PRODUCT_INDEX:
        return PRODUCT_INDEX[ref]
    # id case-insensitive
    for pid, prod in PRODUCT_INDEX.items():
        if pid.lower() == ref_l:
            return prod
    # name exact / substring
    for prod in SAMPLE_PRODUCTS:
        if prod.name.lower() == ref_l or ref_l in prod.name.lower():
            return prod
    # category keywords
    for cat, words in _CATEGORY_KEYWORDS.items():
        if ref_l == cat.lower() or any(w in ref_l for w in words):
            return _DEF_PRODUCT_BY_CATEGORY.get(cat)
    return None

# ---- Tool Implementations ----

def tool_recommend_transfers(params: ProductInput) -> Dict[str, Any]:
    product = _resolve_product(params.product_id)
    if not product:
        return {"error": "product_not_found"}
    recs = inventory_agent.recommend_inventory_transfers(SAMPLE_STORES, product)
    return {"product_id": product.id, "product_name": product.name, "recommendations": recs}

def tool_seasonal_optimize(params: SeasonalOptimizeInput) -> Dict[str, Any]:
    product = _resolve_product(params.product_id)
    if not product:
        return {"error": "product_not_found"}
    opt = inventory_agent.seasonal_inventory_optimization(SAMPLE_STORES, product, params.season)
    return opt

def tool_generate_schedule(params: TransferScheduleInput) -> Dict[str, Any]:
    product = _resolve_product(params.product_id)
    if not product:
        return {"error": "product_not_found"}
    recs = inventory_agent.recommend_inventory_transfers(SAMPLE_STORES, product)
    schedule = inventory_agent.generate_transfer_schedule(recs, params.max_daily_transfers)
    return schedule

def tool_comprehensive_analysis() -> Dict[str, Any]:
    return inventory_agent.comprehensive_inventory_analysis(SAMPLE_STORES, SAMPLE_PRODUCTS)

# Phase 2: add document to vector store

def tool_add_document(params: AddDocumentInput) -> Dict[str, Any]:
    vs = get_vector_store()
    meta = {k: v for k, v in {"source": params.source, "doc_type": params.doc_type}.items() if v}
    added = vs.add_document(params.content, meta)
    return {"document_id": added["id"], "metadata": added["metadata"]}

# Phase 2: similarity retrieval

def tool_retrieve_relevant(params: RetrieveRelevantInput) -> Dict[str, Any]:
    vs = get_vector_store()
    matches = vs.similarity_search(params.query, top_k=params.top_k)
    return {"query": params.query, "results": matches}

# ---- Tool Registry Metadata ----
TOOL_REGISTRY = [
    {"name": "recommend_transfers", "description": "Recommend inventory transfers for a specific product to balance stock levels", "input_model": ProductInput, "callable": tool_recommend_transfers},
    {"name": "seasonal_optimize", "description": "Run seasonal optimization for a product and season", "input_model": SeasonalOptimizeInput, "callable": tool_seasonal_optimize},
    {"name": "generate_transfer_schedule", "description": "Generate a feasible multi-day transfer schedule for a product", "input_model": TransferScheduleInput, "callable": tool_generate_schedule},
    {"name": "comprehensive_analysis", "description": "Full inventory health analysis across all stores and products", "input_model": None, "callable": tool_comprehensive_analysis},
    # Phase 2 retrieval tools
    {"name": "add_document", "description": "Add a textual document (policy, forecast, note) to the retrieval store", "input_model": AddDocumentInput, "callable": tool_add_document},
    {"name": "retrieve_relevant", "description": "Retrieve top-k semantically similar documents for a query", "input_model": RetrieveRelevantInput, "callable": tool_retrieve_relevant},
]

# ---- Simple dispatcher ----

def invoke_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    for meta in TOOL_REGISTRY:
        if meta["name"] == name:
            model = meta["input_model"]
            if model is not None:
                try:
                    parsed = model(**payload)
                except Exception as e:
                    return {"error": "validation_error", "detail": str(e)}
                return meta["callable"](parsed)
            else:
                return meta["callable"]()
    return {"error": "unknown_tool"}
