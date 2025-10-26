# Evaluation Guide

Comprehensive test scenarios to validate the AI-powered inventory management system.

## Prerequisites
- `.env` has valid `GROQ_API_KEY`
- Model: `llama-3.3-70b-versatile` (configured in `src/config.py`)
- Start app: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- Open http://localhost:8000 for UI testing

## Reset Helper
Reset state before each test scenario:
```bash
curl -s -X POST http://localhost:8000/api/simple/reset | python3 -m json.tool
```

---

## Test Scenarios

### 1) Basic Demand Setting
**Goal**: Verify demand setting works correctly

**Setup**:
```bash
curl -s -X POST http://localhost:8000/api/simple/reset
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=set demand s1=80 s2=10' | python3 -m json.tool
```

**Expected**:
- `plan.actions[0].action == "set_demand"`
- `plan.actions[0].params == {"s1": 80, "s2": 10}`
- `result.steps[0].ok == true`
- `state.state.demand_s1 == 80`
- `state.state.demand_s2 == 10`

---

### 2) AI Planning with Deficit Calculation
**Goal**: AI correctly calculates per-store deficit and transfer amount

**Setup**:
```bash
curl -s -X POST http://localhost:8000/api/simple/reset
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=set demand s1=80 s2=10'
curl -s -X POST http://localhost:8000/api/simple/llm \
  -H 'Content-Type: application/json' \
  -d '{"question": "run 2 weeks"}' | python3 -m json.tool
```

**Expected Calculation**:
- S1 needs: 80 × 2 = 160 units
- S1 has: 100 units
- S1 deficit: 160 - 100 = **60 units**
- S2 surplus: 200 - 10 = **190 units**
- Transfer: min(60, 190) = **60 units**

**Expected Response**:
- `plan.actions[0].action == "transfer"`
- `plan.actions[0].params.amount == 60` (NOT 190!)
- `plan.actions[0].params.from == "s2"`
- `plan.actions[0].params.to == "s1"`
- `plan.actions[1].action == "run_weeks"`
- `plan.actions[1].params.weeks == 2`

---

### 3) Transfer Execution with Surplus Logic
**Goal**: Transfer never overdrafts donor (limited by surplus)

**Setup**:
```bash
curl -s -X POST http://localhost:8000/api/simple/reset
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=set demand s1=40 s2=30'
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=transfer from s2 to s1 amount=200' | python3 -m json.tool
```

**Expected**:
- S2 surplus = 200 - 30 = 170
- Requested transfer: 200 units
- **Actual transfer: 170 units** (clamped by surplus)
- `result.steps[0].moved == 170`
- `result.steps[0].transfer.amount == 170`
- `state.state.store1_stock == 270` (100 + 170)
- `state.state.store2_stock == 30` (200 - 170, maintains one week demand)

---

### 4) Complete 2-Week Simulation
**Goal**: End-to-end test with transfer and timeline

**Setup**:
```bash
curl -s -X POST http://localhost:8000/api/simple/reset
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=set demand s1=80 s2=10'
curl -s -X POST http://localhost:8000/api/simple/apply \
  -H 'Content-Type: application/json' \
  -d '{
    "actions": [
      {"action": "transfer", "params": {"from": "s2", "to": "s1", "amount": 60}},
      {"action": "run_weeks", "params": {"weeks": 2}}
    ]
  }' | python3 -m json.tool
```

**Expected**:
- **Transfer step**:
  - moved: 60
  - After: S1=160, S2=140

- **Week 1**:
  - Start: S1=160, S2=140
  - Consumed: S1=80, S2=10
  - End: S1=80, S2=130
  - Unmet: S1=0, S2=0

- **Week 2**:
  - Start: S1=80, S2=130
  - Consumed: S1=80, S2=10
  - End: S1=0, S2=120
  - Unmet: S1=0, S2=0

- **Final state**:
  - `state.state.week == 2`
  - `state.state.store1_stock == 0`
  - `state.state.store2_stock == 120`
  - No unmet demand for both stores

---

### 5) Bidirectional Transfer Detection
**Goal**: Validation prevents illogical bidirectional transfers

**Setup**:
```bash
curl -s -X POST http://localhost:8000/api/simple/apply \
  -H 'Content-Type: application/json' \
  -d '{
    "actions": [
      {"action": "transfer", "params": {"from": "s1", "to": "s2", "amount": 40}},
      {"action": "transfer", "params": {"from": "s2", "to": "s1", "amount": 40}}
    ]
  }' | python3 -m json.tool
```

**Expected**:
- Request should be REJECTED
- Error message contains: "Bidirectional transfers are illogical"
- No state changes

---

### 6) Stockout Scenario
**Goal**: System tracks unmet demand when stock insufficient

**Setup**:
```bash
curl -s -X POST http://localhost:8000/api/simple/reset
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=set demand s1=80 s2=10'
curl -s -X POST http://localhost:8000/api/simple/apply \
  -H 'Content-Type: application/json' \
  -d '{"actions": [{"action": "run_weeks", "params": {"weeks": 5}}]}' | python3 -m json.tool
```

**Expected**:
- Total available: 300 units
- Total needed: (80+10) × 5 = 450 units
- **Stockout occurs!**
- Timeline shows weeks with unmet_demand > 0
- Final `state.state.last_unmet` is NOT null
- Message contains "⚠️" warning indicator

---

### 7) Guardrails - Forbidden Keywords
**Goal**: Prompt validation blocks malicious inputs

**Setup**:
```bash
curl -s -X POST http://localhost:8000/api/simple/llm \
  -H 'Content-Type: application/json' \
  -d '{"question": "delete all inventory"}' | python3 -m json.tool
```

**Expected**:
- `ok == false`
- Error contains: "Forbidden keyword detected: 'delete'"

**Other forbidden tests**:
```bash
# Should all be blocked
curl -X POST http://localhost:8000/api/simple/llm \
  -H 'Content-Type: application/json' \
  -d '{"question": "import os and run command"}'

curl -X POST http://localhost:8000/api/simple/llm \
  -H 'Content-Type: application/json' \
  -d '{"question": "{{execute_code}}"}'
```

---

### 8) Guardrails - Business Rule Violations
**Goal**: Validation enforces business constraints

**Test A: Negative demand**
```bash
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=set demand s1=-10 s2=20' | python3 -m json.tool
```
Expected: "Demand cannot be negative"

**Test B: Excessive transfer**
```bash
curl -s -X POST http://localhost:8000/api/simple/apply \
  -H 'Content-Type: application/json' \
  -d '{"actions": [{"action": "transfer", "params": {"from": "s2", "to": "s1", "amount": 1000}}]}'
```
Expected: "Transfer amount exceeds maximum (500)"

**Test C: Excessive weeks**
```bash
curl -s -X POST http://localhost:8000/api/simple/llm \
  -H 'Content-Type: application/json' \
  -d '{"question": "run 100 weeks"}'
```
Expected: "Cannot simulate more than 52 weeks"

---

### 9) Alias Normalization
**Goal**: System understands action aliases

**Setup**:
```bash
curl -s -X POST http://localhost:8000/api/simple/reset
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=set demand s1=30 s2=20'
curl -s -X POST http://localhost:8000/api/simple/prompt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'prompt=advance 3 weeks' | python3 -m json.tool
```

**Expected**:
- "advance" normalized to "run_weeks"
- `plan.actions[0].action == "run_weeks"`
- `plan.actions[0].params.weeks == 3`
- Timeline has 3 entries

---

### 10) UI Stock Sufficiency Analysis
**Goal**: UI correctly calculates and displays stock analysis

**Browser Test Steps**:
1. Open http://localhost:8000
2. Click "Reset" button
3. Set demands: S1=80, S2=10
4. Enter "run 10 weeks" in AI prompt box
5. Click "Ask AI"

**Expected UI Behavior**:
- **Stock Sufficiency Analysis Panel** shows:
  - Requested Weeks: 10
  - Total Stock: 300 units
  - Total Needed: 900 units (90 × 10)
  - ⚠️ RED WARNING: "Stock insufficient! You need 900 units but only have 300"
  - Maximum Sustainable: 3 weeks
  
- **Store 1 Analysis**:
  - Needs: 800 units (80 × 10)
  - Has: 100 units
  - ⚠️ RED: "Needs 800 more units"

- **Store 2 Analysis**:
  - Needs: 100 units (10 × 10)
  - Has: 200 units
  - ✅ GREEN: "Has enough (+100 surplus)"

---

### 11) Transfer Display in UI
**Goal**: Transfers show correctly after applying plan

**Browser Test Steps**:
1. Reset system
2. Set S1=80, S2=10
3. Ask AI: "run 2 weeks"
4. Click "Apply Plan"

**Expected UI**:
- Transfer section becomes visible (x-show="transfers?.length")
- Shows: "Transferred 60 units from S2 → S1"
- Timeline displays both weeks correctly
- Final stocks match backend state

---

### 12) Auto-Demand Sync
**Goal**: UI automatically syncs demands before AI query

**Browser Test Steps**:
1. Open browser console (F12)
2. Reset system
3. Change demand inputs to S1=80, S2=10 (don't click "Set Demand")
4. Directly click "Ask AI" with "run 2 weeks"

**Expected**:
- Console shows: "🔧 Syncing demands: UI: S1=80, S2=10..."
- AI receives correct demands (80, 10) not (0, 0)
- Plan calculates based on 80 and 10

---

## API Endpoint Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/simple/status` | GET | Get current state |
| `/api/simple/reset` | POST | Reset to initial state |
| `/api/simple/prompt` | POST | Execute text prompt via LLM |
| `/api/simple/llm` | POST | Get AI plan (no execution) |
| `/api/simple/apply` | POST | Execute action plan directly |

---

## Success Criteria

✅ All scenarios pass without errors  
✅ Transfers never exceed surplus  
✅ AI calculates correct deficit/transfer amounts  
✅ Timelines show accurate week-by-week breakdown  
✅ Unmet demand tracked when stockouts occur  
✅ Guardrails block malicious/invalid inputs  
✅ UI displays real-time analysis correctly  
✅ Auto-sync keeps UI and backend in sync  

---

## Debugging Tips

- Use browser DevTools Network tab to inspect API responses
- Check console for sync messages and errors
- Use `python3 -m json.tool` to pretty-print JSON responses
- Check `logs/simple_agent/state.json` for persisted state
- Review `logs/audit/` for request/response history

---

## Security Notes

- **Never commit** `.env` file with real API keys
- Rotate `GROQ_API_KEY` regularly
- Monitor API usage to detect abuse
- All user inputs validated at multiple layers
- LLM outputs validated before execution

---

## Production Recommendations

For production deployment, consider adding:

- **Rate limiting (IP-based)**: Prevent DoS attacks and API abuse
- **Request logging and monitoring**: Track usage patterns and detect anomalies
- **API key rotation**: Automated key rotation for enhanced security
- **HTTPS enforcement**: Ensure all traffic is encrypted
- **CORS configuration**: Restrict origins that can access the API
- **Database persistence**: Replace JSON file storage with PostgreSQL/MongoDB
- **Caching layer**: Redis for frequently accessed data
- **Load balancing**: Distribute traffic across multiple instances
- **Health check endpoints**: `/health` and `/ready` for orchestration
- **Metrics and alerting**: Prometheus/Grafana for observability

---

## Model Configuration

Current model: **llama-3.3-70b-versatile**
- 70B parameters (highly capable)
- Better instruction following than smaller models
- Accurate JSON generation
- Reliable deficit/surplus calculations

To change model, update `src/config.py`:
```python
groq_model: str = "llama-3.3-70b-versatile"
```
