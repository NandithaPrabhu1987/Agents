from fastapi import FastAPI
import uvicorn
import logging

from dotenv import load_dotenv
load_dotenv()

from src.routers.simple_routes import router as simple_router
from src.tracing import setup_tracing
from starlette.middleware.gzip import GZipMiddleware

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LLM Inventory Transfer Simulator",
    description="Two-store simulator with LLM-only planning, explicit transfers (no auto-redistribution), and optional Phoenix tracing",
    version="1.0.0"
)

# gzip responses for faster loads
app.add_middleware(GZipMiddleware, minimum_size=500)

# init tracing (FastAPI + httpx)
setup_tracing(app)

app.include_router(simple_router)

if __name__ == "__main__":
    logger.info("Starting LLM Inventory Transfer Simulator")
    uvicorn.run(app, host="0.0.0.0", port=8000)
