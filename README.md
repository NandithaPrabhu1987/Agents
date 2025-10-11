# Supply Chain Inventory Rebalancing Agent

An AI-powered inventory optimization system designed for retail chain operations across India. This agent helps store operations managers optimize inventory distribution, prevent stockouts, reduce overstock situations, and maximize sales opportunities through intelligent inter-store transfers.

## How the UI template is used
- The dashboard HTML is at `templates/inventory_dashboard.html`.
- FastAPI serves it at `/` using `TemplateResponse`.
- The page loads data via fetch calls to the backend APIs and shows badges indicating the data source:
  - Overview, Transfers, Seasonal: Source: API (deterministic engine)
  - AI Assistant, Sample Queries: Source: AI (LLM response)

## Where GenAI is used vs. Code logic
- Deterministic (no LLM): All calculations and decisions
  - Inventory status, gaps, utilization, days of inventory
  - Distances, transport costs, ETA
  - Transfer recommendations (who → whom, quantities, ROI, priority)
  - Seasonal optimization and scheduling
  - Files: `src/inventory_agent.py` (algorithms), `src/routers/inventory_routes.py` (endpoints)
- Generative (LLM): Natural-language explanation and Q&A
  - Endpoint: `POST /api/chat/inventory`
  - Tabs: AI Assistant and Sample Queries
  - Provider: Groq (`AI_PROVIDER=groq`, `GROQ_MODEL=llama-3.3-70b-versatile`)
  - Behavior: Explains context in bullets/headings, prioritizes actions, summarizes risks
  - No rule-based fallback when `AI_PROVIDER=groq` (explicit failure is returned)

## Optional LLM planning (proposal → validated by engine)
- The Groq service includes `analyze_and_propose_plan()` which asks the model to return a compact JSON plan proposal:
  ```json
  {
    "product": "Monsoon Raincoats Premium",
    "product_id": "<id>",
    "from_stores": ["Mysore"],
    "to_stores": ["Bangalore"],
    "quantity_cap": 60,
    "priority": "urgent",
    "rationale": ["short bullet 1", "short bullet 2"]
  }
  ```
- This is not executed directly. The backend should validate any proposal using the deterministic engine (stock levels, capacity, distance, ROI) before acting.

## API overview (how tabs call APIs)
- Overview (API): `GET /api/stores/status-summary`
- Transfers (API): `POST /api/transfers/recommend` (form: `product_id`)
- Seasonal (API): `POST /api/seasonal/optimize` (form: `product_id`, optional `season`)
- AI Assistant (AI): `POST /api/chat/inventory` (form: `query`)
- Sample Queries (AI): routed to `/api/chat/inventory` with prefilled prompts

## Configure AI provider
- Default: rule-based deterministic (`AI_PROVIDER=rule`)
- Groq LLM: set `.env`
  ```bash
  AI_PROVIDER=groq
  GROQ_API_KEY=... # keep this secret (in .env, not committed)
  GROQ_MODEL=llama-3.3-70b-versatile
  ```
- `main.py` loads `.env` via `load_dotenv()` before router initialization.

## Project structure (key files)
```
├── main.py                         # FastAPI bootstrap, registers routers
├── src/
│   ├── inventory_agent.py          # Core business logic, models, distance logic
│   ├── routers/
│   │   └── inventory_routes.py     # All API endpoints and dashboard route
│   ├── services/
│   │   └── ai_service.py           # Rule-based AI service (deterministic)
│   ├── data/
│   │   └── seed.py                 # Sample stores and products
│   └── groq_service.py             # Groq LLM integration (explanations + JSON plan)
├── templates/
│   └── inventory_dashboard.html    # Web interface (with filters + AI tab)
├── requirements.txt                # Dependencies
└── README.md                       # Documentation
```

## Security
- `.env` is in `.gitignore`. Never commit API keys.
- If a key was exposed, rotate it immediately in the provider console.

# Supply Chain Inventory Rebalancing Agent

An AI-powered inventory optimization system designed for retail chain operations across India. This agent helps store operations managers optimize inventory distribution, prevent stockouts, reduce overstock situations, and maximize sales opportunities through intelligent inter-store transfers.

## 🎯 Purpose

As a Store Operations Manager at a mid-size retail chain operating 10 stores across India, you need to:
- Balance inventory levels across all store locations
- Minimize transportation costs while preventing stockouts
- Optimize seasonal inventory distribution
- Make data-driven transfer decisions based on demand patterns

## 🏪 Target Scenarios

### Sample Use Cases
1. **Monsoon Gear Transfer**: "Transfer monsoon gear from Mysore to Bangalore"
   - Mysore has overstock (180 units) vs Bangalore critical low stock (45 units)
   - 140km distance, cost-effective transfer with high ROI

2. **Diwali Seasonal Distribution**: "Optimize festive wear distribution for Diwali"
   - Multi-store seasonal demand analysis
   - Prioritize high-demand locations (Delhi, Mumbai, Bangalore)
   - Calculate investment vs revenue potential

## 🚀 Features

### Core Functionality
- **Real-time Inventory Analysis**: Monitor stock levels across all 10 stores
- **Smart Transfer Recommendations**: AI-powered optimization considering distance, cost, and demand
- **Seasonal Planning**: Automatic seasonal demand adjustments for Indian markets
- **ROI Calculations**: Transport cost vs potential revenue analysis
- **Priority-based Scheduling**: Urgent transfers for critical stockouts

### Store Network
- **Bangalore**: Fashion Central Bangalore (High demand, tech hub)
- **Mysore**: Fashion Central Mysore (Lower demand, excess inventory)
- **Chennai**: Fashion Central Chennai (High demand, southern hub)
- **Mumbai**: Fashion Central Mumbai (Premium demand, high operational costs)
- **Delhi**: Fashion Central Delhi (Festive demand, seasonal peaks)
- **Pune**, **Hyderabad**, **Kochi**, **Coimbatore**, **Gurgaon**: Regional stores

### Product Categories
- **Monsoon Gear**: Raincoats, umbrellas (Peak: Jun-Sep)
- **Festive Wear**: Ethnic collections (Peak: Oct-Dec)
- **Summer Essentials**: Cotton wear (Peak: Mar-May)
- **Electronics**: Gadgets and accessories
- **Home Decor**: Seasonal decorative items

## 🛠️ Technical Architecture

### Backend Components
- **FastAPI**: REST API with async support
- **Routers**: All HTTP routes in `src/routers/inventory_routes.py`
- **Inventory Agent**: Core business logic in `src/inventory_agent.py`
- **AI Services**:
  - Rule-based AI in `src/services/ai_service.py` (default)
  - Optional Groq LLM in `src/groq_service.py` (behind flag)
- **Seed Data**: Sample stores and products in `src/data/seed.py`
- **Distance Logic**: Realistic matrix + haversine fallback for Indian cities

### Key Algorithms
- **Stock Status Analysis**: Critical/Low/Balanced/Overstock classification
- **Transfer Optimization**: ROI-based ranking with distance penalties
- **Seasonal Adjustment**: Location-specific demand multipliers
- **Schedule Generation**: Multi-day transfer planning with capacity constraints
- **Distance Estimation**: Uses matrix first; otherwise geodesic with road-factor

## 📊 Dashboard Features

### Store Overview
- Real-time inventory status across all stores
- Critical alerts for stockout risks
- Utilization percentages and demand scores
- Days of inventory remaining calculations

### Transfer Recommendations
- Product-specific transfer analysis
- ROI calculations with transport costs
- Priority-based urgency classification
- Estimated delivery times and routes

### Seasonal Planning
- Auto-season detection based on current month
- Location-specific seasonal multipliers
- Investment vs revenue projections
- Store-wise adjustment requirements

### Sample Queries
- Pre-built common scenarios
- AI-powered analysis results
- Interactive query execution
- Business impact summaries

## 🚀 Quick Start

### Installation
```bash
# Clone and setup
git clone <repository>
cd supply-chain-agent

# Install dependencies
pip install -r requirements.txt

# Optional: Set up Groq AI (for advanced features)
export GROQ_API_KEY="your-groq-api-key"
```

### Running the Application
```bash
# Start the development server (default: rule-based AI)
python main.py

# Or use uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Switch AI Provider (Rule vs Groq)
```bash
# Rule-based (default)
export AI_PROVIDER=rule

# Groq LLM (requires GROQ_API_KEY)
export AI_PROVIDER=groq
export GROQ_API_KEY=your-groq-api-key
python main.py
```
Add the same variables to `.env` for persistence.

### Access the Dashboard
- **Web Dashboard**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Store Status**: http://localhost:8000/api/stores/status-summary

## 📡 API Endpoints

### Store Management
- `GET /api/stores` - List all stores
- `GET /api/stores/{store_id}` - Store details with analysis
- `GET /api/stores/status-summary` - System-wide status overview

### Transfer Operations
- `POST /api/transfers/recommend` - Get transfer recommendations for a product
- `POST /api/transfers/schedule` - Generate optimized transfer schedule
- `POST /api/seasonal/optimize` - Seasonal inventory optimization

### Sample Queries
- `POST /api/query/monsoon-transfer` - Monsoon gear transfer analysis
- `POST /api/query/festive-distribution` - Diwali season optimization

### AI Chat
- `POST /api/chat/inventory` - Natural language inventory analysis
  - Content-Type: `application/x-www-form-urlencoded`
  - Body: `query=your question`

### Analytics
- `GET /api/analysis/comprehensive` - Full system analysis
- `GET /api/products` - Product catalog

## 🧮 Business Metrics

### Cost Optimization
- **Transport Cost**: ₹2.5 per unit per km
- **Minimum Transfer**: 10 units (economical threshold)
- **Safety Stock**: 20% buffer above minimum levels

### Performance KPIs
- **ROI Ratio**: Revenue potential vs transport cost
- **Stockout Prevention**: Critical status alerts
- **Utilization Rate**: Store capacity optimization
- **Demand Score**: Market potential assessment (1-10 scale)

### Seasonal Patterns
- **Monsoon** (Jun-Sep): 1.3-1.6x demand multiplier for coastal cities
- **Festive** (Oct-Dec): 1.3-1.5x demand for metros and northern cities  
- **Summer** (Mar-May): 1.2-1.5x demand for warmer regions

## 📈 Sample Scenarios

### Scenario 1: Urgent Transfer
```
Status: Bangalore (Critical - 45 units) ← Mysore (Overstock - 180 units)
Product: Monsoon Raincoats Premium
Distance: 140km | Cost: ₹17,500 | Revenue: ₹44,950 | ROI: 2.6x
Priority: URGENT | Delivery: 2.8 hours
```

### Scenario 2: Seasonal Distribution
```
Season: Festive (Diwali)
Investment: ₹2,40,000 | Potential Revenue: ₹4,79,700 | Margin: 50%
Priority Stores: Delhi (+85 units), Mumbai (+65 units), Bangalore (+45 units)
```

## 🔧 Configuration

### Environment Variables
```bash
AI_PROVIDER=groq               # rule | groq (default: rule)
GROQ_API_KEY=your-groq-api-key # Required only if AI_PROVIDER=groq
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### Distance Matrix
Update `DISTANCE_MATRIX` in `src/inventory_agent.py` (realistic road distances). Unknown pairs use a haversine-based fallback.

### Seasonal Patterns
Modify seasonal multipliers in `seasonal_inventory_optimization()`.

## 📋 Development

### Project Structure
```
├── main.py                         # FastAPI bootstrap, registers routers
├── src/
│   ├── inventory_agent.py          # Core business logic, models, distance logic
│   ├── routers/
│   │   └── inventory_routes.py     # All API endpoints and dashboard route
│   ├── services/
│   │   └── ai_service.py           # Rule-based AI service
│   ├── data/
│   │   └── seed.py                 # Sample stores and products
│   └── groq_service.py             # Optional Groq AI integration
├── templates/
│   └── inventory_dashboard.html    # Web interface (with filters + AI tab)
├── requirements.txt                # Dependencies
└── README.md                       # Documentation
```

### Key Classes
- **InventoryAgent**: Main optimization engine
- **Store / Product**: Domain models
- **TransferRequest**: Transfer planning model

### Testing Sample Queries
```bash
# Test monsoon transfer
curl -X POST http://localhost:8000/api/query/monsoon-transfer

# Test festive distribution
curl -X POST http://localhost:8000/api/query/festive-distribution

# Get store status
curl http://localhost:8000/api/stores/status-summary

# Ask AI (form-encoded)
curl -X POST \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'query=What stores need urgent inventory transfers?' \
  http://localhost:8000/api/chat/inventory
```

## 🎯 Business Impact

### Operational Benefits
- **Reduce Stockouts**: Prevent lost sales through proactive transfers
- **Optimize Inventory**: Minimize carrying costs and waste
- **Improve Cash Flow**: Better inventory turnover across locations
- **Enhance Customer Experience**: Right products at right locations

### Financial Impact
- **Cost Savings**: Optimized transport routes and quantities
- **Revenue Growth**: Better product availability at high-demand stores
- **Efficiency Gains**: Automated decision-making for transfer operations
- **Risk Mitigation**: Early alerts for critical inventory situations

---

Built for retail chains operating across India with focus on seasonal demand patterns, regional preferences, and cost-effective logistics optimization.
