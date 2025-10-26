# Smart Inventory Manager

AI-powered inventory management for 2 stores with automatic stock transfers.

## Quick Start

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure .env file
AI_PROVIDER=groq
GROQ_API_KEY=your-key-here
GROQ_MODEL=llama-3.3-70b-versatile

# Run
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000

## Overview

- **Store 1**: 100 units initial stock
- **Store 2**: 200 units initial stock
- **AI Agent**: Automatically plans transfers between stores
- **Bidirectional**: Either store can help the other

## How to Use

1. **Set Demand**: Enter S1 and S2 weekly demand (e.g., 80 and 10)
2. **Ask AI**: Type "run 10 weeks" 
3. **Review**: See stock analysis and execution plan
4. **Apply**: Click to execute

**Note**: System automatically syncs demands before AI planning!

## Key Features

- 🧠 **AI-Powered Planning**: Uses Groq's llama-3.3-70b-versatile model for intelligent decisions
- 📊 **Stock Sufficiency Analysis**: Real-time calculations with warnings
- 🔄 **Smart Transfers**: Only when needed, using surplus logic (stock - ONE week demand)
- 🎨 **Visual Alerts**: Red for warnings, green for OK
- 💼 **Professional UI**: Clean, modern, data-driven interface
- 🛡️ **Comprehensive Security**: 6 layers of validation and guardrails
  - Prompt injection protection
  - Jailbreak attempt blocking
  - Forbidden keyword filtering
  - Business rule enforcement
  - Max limits (demand ≤ 1000, transfer ≤ 500, weeks ≤ 52)
- 💾 **State Persistence**: JSON-based state management
- 📝 **Audit Logging**: Complete request/response history

## API Examples

```bash
# Get status
curl http://localhost:8000/api/simple/status

# Reset to defaults
curl -X POST http://localhost:8000/api/simple/reset

# Ask AI for plan (auto-syncs demands)
curl -X POST http://localhost:8000/api/simple/llm \
  -H "Content-Type: application/json" \
  -d '{"question": "run 5 weeks"}'

# Apply specific action
curl -X POST http://localhost:8000/api/simple/apply \
  -H "Content-Type: application/json" \
  -d '{"action": "set_demand", "params": {"s1": 80, "s2": 10}}'
```

## Security Features

The system includes comprehensive protection against:
- ✅ Prompt injection attacks ("ignore previous instructions")
- ✅ Jailbreak attempts ("you are now in admin mode")
- ✅ System prompt leaks ("repeat your instructions")
- ✅ Code execution attempts (`exec`, `eval`, `import`)
- ✅ SQL-like injections (`delete`, `drop`, `truncate`)
- ✅ Template injections (`{{`, `${`, `<%`)

See `docs/PROMPT_INJECTION_PROTECTION.md` for details.

## Architecture

```
Web UI → FastAPI → LLM Agent → Groq API
                 → SimpleAgent (Simulation)
```

## Files

- `main.py`: FastAPI application entry point
- `src/llm_agent.py`: AI planning with Groq (llama-3.3-70b-versatile)
- `src/simple_agent.py`: Core inventory simulation logic
- `src/config.py`: Configuration management
- `src/tracing.py`: Phoenix observability integration
- `src/routers/simple_routes.py`: API endpoints
- `templates/simple_agent.html`: Modern web UI with Alpine.js
- `logs/simple_agent/state.json`: Persistent state storage
- `logs/audit/`: Request/response audit logs

## Documentation

- `README.md`: This file - Quick start guide
- `PROJECT_SUMMARY.md`: Complete project overview
- `docs/EVALUATION.md`: Comprehensive test scenarios (12+ tests)
- `docs/GUARDRAILS_SUMMARY.md`: Security validation overview
- `docs/PROMPT_INJECTION_PROTECTION.md`: Prompt security guide
- `docs/SERVICES.md`: Running services documentation

## License

MIT
