from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
import uvicorn
import logging

# Load environment variables early
from dotenv import load_dotenv
load_dotenv()

from src.routers.inventory_routes import router as inventory_router

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

# Register routers
app.include_router(inventory_router)

if __name__ == "__main__":
    logger.info("Starting Supply Chain Inventory Rebalancing Agent")
    uvicorn.run(app, host="0.0.0.0", port=8000)
