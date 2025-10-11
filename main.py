from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
import uvicorn
import logging

# Load environment variables early
from dotenv import load_dotenv
load_dotenv()

from src.routers.inventory_routes import router as inventory_router
from src.observability.langfuse import get_langfuse, start_span, end_span, flush  # updated

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('supply_chain_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Supply Chain Inventory Rebalancing Agent",
    description="AI-powered inventory optimization system for retail chain management",
    version="2.0.0"
)

templates = Jinja2Templates(directory="templates")

# --- Langfuse middleware using start_as_current_span ---
@app.middleware("http")
async def langfuse_trace_middleware(request, call_next):
    lf = get_langfuse()
    cm = None
    span = None
    if lf:
        try:
            cm = lf.start_as_current_span(name="http.request", input={"path": str(request.url), "method": request.method}, metadata={"component": "http"})
            span = cm.__enter__()  # enter context to set active span
        except Exception as e:
            logger.debug(f"Langfuse middleware start failed: {e}")
    try:
        response = await call_next(request)
        return response
    finally:
        try:
            if cm:
                cm.__exit__(None, None, None)
            flush()
        except Exception as e:
            logger.debug(f"Langfuse middleware end failed: {e}")

# Register routers
app.include_router(inventory_router)

if __name__ == "__main__":
    logger.info("Starting Supply Chain Inventory Rebalancing Agent")
    uvicorn.run(app, host="0.0.0.0", port=8000)
