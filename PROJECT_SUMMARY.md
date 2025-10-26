# 🏪 Smart Inventory Manager - Project Summary

## Overview
A production-ready AI-powered inventory management system for 2 stores with automatic stock transfers, comprehensive security guardrails, and an intuitive web interface.

---

## ✅ Core Features

### 1. **Intelligent Inventory Management**
- **Two Stores**: Store 1 (100 units), Store 2 (200 units)
- **Automatic Transfers**: AI detects which store needs stock and transfers from the other
- **Bidirectional Support**: S1 ↔ S2 transfers based on actual need
- **Smart Logic**: Only ONE direction per plan - no nonsense bidirectional transfers
- **Weekly Simulation**: Track demand, consumption, and unmet demand over weeks

### 2. **AI-Powered Planning**
- **Natural Language Interface**: Just ask "run 2 weeks"
- **Groq LLM Integration**: Fast, intelligent planning
- **Automatic Deficit Detection**: Calculates which store needs help
- **Surplus-Based Transfers**: Never overdraws donor store
- **Clear Rationale**: Each action includes reasoning

### 3. **Modern Web UI**
- **Beautiful Design**: Gradient backgrounds, color-coded alerts
- **Real-time Status**: Live stock levels with progress bars
- **Visual Alerts**: Red warnings when stores run low
- **Interactive Dashboard**: Click and go - no complex forms
- **Results Visualization**: Clear tables with timeline and transfers
- **Mobile Responsive**: Works on all devices

### 4. **Security Guardrails** 🛡️
- **Multi-Layer Validation**: Input, Plan, API, Agent levels
- **Injection Protection**: Blocks malicious patterns and keywords
- **Business Rules**: Enforces max demand (1000), transfers (500), weeks (52)
- **Bidirectional Detection**: Prevents illogical transfer plans
- **Rate Limiting Ready**: Length checks and validation in place
- **Clear Error Messages**: User-friendly feedback with emojis

---

## 📁 Project Structure

```
Agents/
├── main.py                      # FastAPI application entry point
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
├── README.md                    # User documentation
├── PROJECT_SUMMARY.md          # This file
│
├── src/
│   ├── __init__.py
│   ├── config.py               # Settings and environment variables
│   ├── llm_agent.py            # LLM planner with guardrails ⭐
│   ├── simple_agent.py         # Core inventory simulation logic
│   ├── tracing.py              # Optional Phoenix tracing
│   └── routers/
│       └── simple_routes.py    # API endpoints
│
├── templates/
│   ├── simple_agent.html       # Modern web UI ⭐
│   └── simple_agent_old.html   # Backup of old UI
│
├── docs/
│   ├── GUARDRAILS.md           # Detailed security documentation
│   ├── GUARDRAILS_SUMMARY.md   # Quick reference
│   └── EVALUATION.md           # (if exists)
│
└── logs/
    ├── audit/                   # Audit trail (gitignored)
    ├── memory/                  # Memory logs (gitignored)
    └── simple_agent/
        └── state.json           # Persistent state
```

---

## 🚀 Quick Start

### 1. Setup
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 2. Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Use
Open http://localhost:8000 in your browser

---

## 🎯 How It Works

### User Journey
1. **Set Demand**: Choose weekly demand (e.g., S1=30, S2=20)
2. **Ask AI**: Type "run 2 weeks" in AI Advisor
3. **Review Plan**: See parsed actions before execution
4. **Apply**: Click "Apply Plan" to execute
5. **View Results**: Timeline, transfers, and stock levels displayed

### AI Logic
```python
# Simplified logic:
if store1_stock < demand_s1:
    # Store 1 needs help
    transfer(from=store2, to=store1, amount=deficit)
elif store2_stock < demand_s2:
    # Store 2 needs help
    transfer(from=store1, to=store2, amount=deficit)
else:
    # Both have enough - no transfer needed
    just_run_weeks()
```

---

## 🛡️ Security Features

### Guardrails Summary
| Layer | Protection |
|-------|-----------|
| **Prompt Validation** | Blocks: injection, system commands, excessive length |
| **Plan Validation** | Enforces: business rules, no bidirectional transfers |
| **API Validation** | Limits: request size, action count, rate control |
| **Agent Validation** | Runtime: parameter checks, type validation |

### Blocked Examples
```
❌ "delete inventory"          → Forbidden keyword
❌ "run 100 weeks"             → Exceeds max (52)
❌ "set demand s1=-10"         → Negative value
❌ "{{malicious_code}}"        → Injection pattern
❌ Transfer S1→S2 AND S2→S1    → Bidirectional nonsense
```

---

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/api/simple/status` | GET | Current state |
| `/api/simple/reset` | POST | Reset to defaults |
| `/api/simple/llm` | POST | Get AI plan (no execution) |
| `/api/simple/apply` | POST | Execute action plan |
| `/api/simple/prompt` | POST | AI plan + execute |

---

## 🧪 Testing

### Valid Test Cases
```bash
# Test 1: Basic simulation
curl -X POST http://localhost:8000/api/simple/llm \
  -H "Content-Type: application/json" \
  -d '{"question": "run 2 weeks"}'

# Test 2: Set demand and run
curl -X POST http://localhost:8000/api/simple/llm \
  -H "Content-Type: application/json" \
  -d '{"question": "set demand s1=30 s2=20 and run 3 weeks"}'

# Test 3: Status check
curl http://localhost:8000/api/simple/status
```

### Invalid Test Cases (Should Fail)
```bash
# Should fail: Exceeds max weeks
curl -X POST http://localhost:8000/api/simple/llm \
  -H "Content-Type: application/json" \
  -d '{"question": "run 100 weeks"}'

# Should fail: Forbidden keyword
curl -X POST http://localhost:8000/api/simple/llm \
  -H "Content-Type: application/json" \
  -d '{"question": "delete all inventory"}'
```

---

## 🔧 Configuration

### Environment Variables (.env)
```bash
AI_PROVIDER=groq
GROQ_API_KEY=your-key-here
GROQ_MODEL=llama-3.1-8b-instant
LOG_LEVEL=INFO

# Optional: Phoenix tracing
# PHOENIX_OTLP_HTTP_ENDPOINT=http://localhost:6006/v1/traces
```

### Guardrail Limits (src/llm_agent.py)
```python
max_prompt_length = 2000
max_weeks = 52
max_demand = 1000
max_transfer = 500
```

---

## 📈 Key Improvements Made

### ✅ Fixed Issues
1. **Bidirectional Transfer Nonsense**: Now prevents S1→S2 AND S2→S1 in same plan
2. **Unclear UI**: New modern design with visual alerts and better layout
3. **No Validation**: Comprehensive guardrails at all layers
4. **Poor Error Messages**: Now emoji-based, clear, actionable feedback
5. **Missing Documentation**: Complete docs for security and usage

### ✅ Added Features
1. Security guardrails with injection protection
2. Bidirectional transfer detection
3. Modern gradient UI with color coding
4. Real-time status monitoring
5. Clear timeline and transfer visualization
6. Comprehensive error handling

---

## 🎓 Best Practices

### For Users
- Start with preset demands to understand behavior
- Use "run 2 weeks" for quick tests
- Check timeline results to verify transfers
- Reset when experimenting with different scenarios

### For Developers
- All validation happens before execution
- State is persisted automatically
- Errors return clear messages
- API follows RESTful patterns
- Code is well-documented

---

## 🔮 Future Enhancements

### Recommended
- [ ] Multiple products (not just ONE)
- [ ] More than 2 stores
- [ ] Historical trend analysis
- [ ] Demand forecasting
- [ ] Email/SMS alerts for low stock
- [ ] Export reports (PDF/Excel)
- [ ] User authentication
- [ ] Role-based access control
- [ ] API rate limiting (Redis)
- [ ] WebSocket for real-time updates

---

## 📝 License & Credits

**Project**: Smart Inventory Manager  
**Technology Stack**: Python, FastAPI, Alpine.js, TailwindCSS, Groq LLM  
**Security**: Multi-layer validation with guardrails  
**Status**: Production-ready ✅  

---

## 🆘 Support

### Common Issues

**Issue**: "GROQ_API_KEY not set"  
**Solution**: Add your Groq API key to `.env` file

**Issue**: Phoenix tracing errors  
**Solution**: Ignore - it's optional monitoring, doesn't affect core functionality

**Issue**: Simulation results not showing  
**Solution**: Check browser console (F12) for debug logs

**Issue**: Bidirectional transfers appearing  
**Solution**: Fixed! Update code and restart server

---

## ✨ Summary

This is a **clean, secure, production-ready** inventory management system with:
- 🤖 AI-powered planning
- 🛡️ Comprehensive security
- 🎨 Modern, intuitive UI
- 📊 Clear visualization
- 🚀 Fast and reliable
- 📚 Well documented

**Ready to deploy and use!**
