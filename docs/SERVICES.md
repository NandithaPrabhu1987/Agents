# Running Services

## Current Status

### ✅ Inventory Agent (FastAPI)
- **URL**: http://localhost:8000
- **Status**: Running
- **Command**: Via VS Code task "Start Inventory Agent"
- **Features**: 
  - Smart inventory management with AI planning
  - Bidirectional stock transfers between 2 stores
  - LLM-powered decision making via Groq API
  - Real-time state persistence

### ✅ Phoenix Tracing Server
- **URL**: http://localhost:6006
- **Status**: Running
- **Command**: `.venv/bin/python -m phoenix.server.main serve`
- **Features**:
  - OpenTelemetry trace collection
  - Visual trace inspection and analysis
  - Performance monitoring
  - LLM call tracking

## Usage

### Access the Inventory Manager
1. Open http://localhost:8000 in your browser
2. You'll see the Smart Inventory Manager UI with:
   - Store status cards (S1 with 100 units, S2 with 200 units)
   - AI Advisor section for natural language commands
   - Timeline and transfer visualization

### View Traces in Phoenix
1. Open http://localhost:6006 in your browser
2. You'll see all API calls, LLM requests, and system traces
3. Click on individual traces to see:
   - Request/response details
   - Timing information
   - LLM prompts and completions
   - Error stack traces (if any)

## Testing the System

### Basic Test Flow
```
1. Open http://localhost:8000
2. Set demands: S1=80, S2=80
3. Ask AI: "run 2 weeks"
4. Review the plan in "AI Plan Details" section
5. Click "Apply Plan" to execute
6. Check http://localhost:6006 to see traces
```

### Verify Bidirectional Transfer Fix
- Set both stores to same high demand (e.g., 80 each)
- Run simulation for multiple weeks
- Verify only ONE logical transfer occurs (not bidirectional)
- Example: If S1 has surplus, only S1→S2 transfer should happen

## Stopping Services

### Stop Inventory Agent
- In VS Code: Terminal → "Start Inventory Agent" → Click stop button
- Or: Find process and kill: `lsof -ti:8000 | xargs kill`

### Stop Phoenix
- Press Ctrl+C in the Phoenix terminal
- Or: `lsof -ti:6006 | xargs kill`

## Environment Variables

The agent uses these environment variables (configured in tasks.json):
```
AI_PROVIDER=groq
GROQ_MODEL=llama-3.1-8b-instant
LANGFUSE_HOST=https://us.cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-485f0e6f-1e37-4903-b4a9-4b24f9af3958
LANGFUSE_SECRET_KEY=sk-lf-a1013b63-e4e7-4121-be7e-d44aea16da40
```

Phoenix uses default settings:
```
PHOENIX_OTLP_HTTP_ENDPOINT=http://127.0.0.1:4318/v1/traces (default)
```

## Troubleshooting

### Connection Errors
- **Error**: `Connection refused` to Phoenix
- **Solution**: Make sure Phoenix is running on port 6006 first
- The agent will retry automatically; traces are non-blocking

### UI Not Updating
- Hard refresh browser: Cmd+Shift+R (Mac) or Ctrl+F5 (Windows)
- Check browser console for JavaScript errors
- Verify agent is responding: `curl http://localhost:8000/api/simple/status`

### AI Plan Not Showing
- **Fixed in latest update**: AI Plan Details now always visible when AI responds
- Includes debug section to view raw JSON plan
- Shows clear message for informational responses

## Architecture

```
┌─────────────────────┐
│   Browser Client    │
│  (Alpine.js + UI)   │
└──────────┬──────────┘
           │ HTTP/JSON
           ▼
┌─────────────────────┐      ┌──────────────────┐
│   FastAPI Server    │─────▶│   Groq API       │
│   (port 8000)       │      │   (LLM Planning) │
└──────────┬──────────┘      └──────────────────┘
           │
           │ OTLP traces
           ▼
┌─────────────────────┐
│  Phoenix Server     │
│  (port 6006)        │
│  Trace Analysis UI  │
└─────────────────────┘
```

## Next Steps

1. **Test the fixed bidirectional logic** with high demands
2. **Monitor traces** in Phoenix to see LLM decision making
3. **Review error handling** via Phoenix trace details
4. **Consider production hardening** per GUARDRAILS_SUMMARY.md
