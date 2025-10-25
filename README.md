# LLM Inventory Transfer Simulator

A minimal, prompt-driven simulator for managing one product across two stores with LLM (Groq) planning.

- Store 1 starts with 100 units; Store 2 starts with 200 units
- You set weekly demand per store
- Each simulated week consumes demand at each store (no automatic transfers)
- Transfers are explicit actions planned by the LLM or triggered by the user
- Tracks week, stocks, consumption, unmet demand, transfers; state persists between requests
- Optional tracing to Arize Phoenix via OpenTelemetry

## Quick Start

1) Create venv and install
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

2) Configure .env
```bash
AI_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.1-8b-instant
# Phoenix (optional)
PHOENIX_OTLP_HTTP_ENDPOINT=http://localhost:6006/v1/traces
OTEL_SERVICE_NAME=inventory-agent
```

3) Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Open http://localhost:8000

## UI Usage
- Step 1: Set weekly demand (e.g., S1=30, S2=20) → Set Demand
- Step 2: Run N weeks (e.g., 2) → Run or Advance 1 week
- Status: refreshes the top cards with current week and stocks
- Reset: returns to S1=100, S2=200, week=0, demand=0
- LLM Advisor: ask for a plan; review parsed actions; click Apply plan to execute
- Last action: shows the final applied action and its result message
- Timeline tables:
  - Latest run or Show all weeks toggle to view cumulative weeks
  - End-of-week stocks and unmet demand per store
  - Consumption detail (start, consumed, unmet, end) per week
- Transfers table: lists transfers from the latest applied plan

Notes
- Stocks won’t change if weekly demand is 0
- Transfers are clamped by donor surplus: you can only move up to (stock − its demand)

## API
- GET /api/simple/status → { ok, state }
- POST /api/simple/reset → reset state
- POST /api/simple/prompt (form: prompt) → returns { mode: "groq", plan, result, state }
- POST /api/simple/llm (json: { question }) → LLM plan/explanation only
- POST /api/simple/apply (json: { actions: [...] }) → apply multiple actions atomically

Behavior & Normalization
- LLM is guided to output actions: set_demand, transfer, run_weeks
- Backend tolerates aliases (run/advance → run_weeks, set-demand → set_demand, move → transfer) and normalizes params
- If the LLM returns an "explain" with an embedded JSON plan, the server parses and executes that plan
- If an action label is missing but params imply intent (e.g., weeks present), the server infers the correct action

## Configuration
- src/config.py reads .env variables
- src/llm_agent.py calls Groq and normalizes the returned plan
- src/simple_agent.py simulates stock, demand, transfers; state saved in logs/simple_agent/state.json
- src/routers/simple_routes.py serves UI and LLM endpoints and applies plans

## Phoenix Tracing (optional)
- Install and run Phoenix:
```bash
. .venv/bin/activate
pip install -U arize-phoenix
phoenix serve --host 127.0.0.1 --port 6006
```
- Ensure .env has PHOENIX_OTLP_HTTP_ENDPOINT=http://localhost:6006/v1/traces
- Restart the app and use it; open http://localhost:6006 → Traces
- Traces include FastAPI requests and outbound calls to Groq

## Project Structure
```
main.py
requirements.txt
src/
  config.py
  llm_agent.py
  simple_agent.py
  routers/
    simple_routes.py
  tracing.py
templates/
  simple_agent.html
logs/
  simple_agent/state.json
```

## Security
- Never commit real API keys. Keep .env private and rotate any exposed keys.
