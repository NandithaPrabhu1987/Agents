Phase 4: Memory & Tool Outcome Scoring (Initial Memory Only)
===========================================================
Scope Implemented:
- Persistent lightweight memory store (JSONL) at logs/memory/memory.jsonl
- Captures tool_result snippets (truncated) and final synthesized summaries
- Exposed endpoints:
  * GET /api/memory/recent?limit=10
  * GET /api/memory/query?q=keyword&limit=5
- Integrated memory writes in orchestrator (tool results + final answer)

Config Additions (config.py):
- memory_dir (default logs/memory)
- memory_max_items (default 300)

Data Model:
- MemoryItem: id, ts, type (tool_result|summary|user_goal), importance (0-1), content, metadata
- Append-only with pruning by importance + recency when exceeding capacity

Usage Examples:
1. Recent:
   curl -X GET 'http://localhost:8000/api/memory/recent?limit=5'
2. Keyword Query:
   curl -X GET 'http://localhost:8000/api/memory/query?q=monsoon&limit=5'

Next Possible Enhancements:
- Add heuristic scoring: importance based on ROI, urgency, or tool type
- Summarize old items and reduce content size (decay)
- Tag provenance (correlation_id, session_id) for cross-linking audits
- Integrate memory snippets automatically into /api/chat/inventory context (top 3 relevant)
- Add endpoint to purge / compact memory

Not Implemented Yet (Scoring Placeholder):
- Dynamic importance calculation (currently fixed defaults: tool_result=0.4, summary=0.6)
- LLM-based summarization of accumulated tool results

Ready for further expansion when needed.
