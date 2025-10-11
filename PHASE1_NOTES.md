Phase 1: Tool Chaining Foundation
=================================
Objective:
Provide a deterministic, callable tool layer the AI (and external clients) can orchestrate before adding retrieval or more complex agent behavior.

Tools Implemented (src/agent/tools.py):
- recommend_transfers: Recommend inventory transfers for a product
- seasonal_optimize: Seasonal optimization for a product (+ optional season)
- generate_transfer_schedule: Build multi-day transfer schedule from recommendations
- comprehensive_analysis: Full cross-store/product health snapshot

Core Concepts:
- TOOL_REGISTRY: Metadata (name, description, pydantic input model, callable)
- invoke_tool: Dispatcher validating payload via pydantic and executing
- Deterministic logic: All tools rely purely on current in-memory SAMPLE_STORES / SAMPLE_PRODUCTS and InventoryAgent methods
- Extensibility: Adding a new tool requires a pydantic model + function + registry entry

Endpoints Added (inventory_routes.py):
1. GET /api/agent/tools
   Lists available tools with JSON schema for input validation.
2. POST /api/agent/tools/invoke
   Form fields:
     - tool_name (str)
     - payload (JSON string)
   Returns success flag + result or validation error.

Usage Examples (curl):
1. List Tools:
   curl -X GET http://localhost:8000/api/agent/tools

2. Recommend Transfers:
   curl -X POST http://localhost:8000/api/agent/tools/invoke \
     -F tool_name=recommend_transfers \
     -F 'payload={"product_id":"P-MONSOON-001"}'

3. Seasonal Optimize:
   curl -X POST http://localhost:8000/api/agent/tools/invoke \
     -F tool_name=seasonal_optimize \
     -F 'payload={"product_id":"P-FESTIVE-001","season":"festive"}'

4. Generate Transfer Schedule:
   curl -X POST http://localhost:8000/api/agent/tools/invoke \
     -F tool_name=generate_transfer_schedule \
     -F 'payload={"product_id":"P-MONSOON-001","max_daily_transfers":4}'

5. Comprehensive Analysis:
   curl -X POST http://localhost:8000/api/agent/tools/invoke \
     -F tool_name=comprehensive_analysis \
     -F 'payload={}'

Design Notes:
- Phase 1 intentionally excludes retrieval, embeddings, or multi-step reasoning.
- Provides a stable contract so LLM (in future phases) can plan which deterministic actions to call.
- Pydantic schemas exposed let downstream orchestrators auto-generate forms / validation.

Audit / Traceability (Carried Over):
- Existing audit writer unaffected; Phase 1 tools themselves are pure functions and not yet individually audited.
- Future enhancement: wrap tool invocations with audit metadata when called via AI planning loop.

Next Step (Phase 2 Recap):
- Introduce retrieval layer (vector store + document tools) to ground AI planning with external factual snippets.
