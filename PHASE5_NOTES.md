Phase 5: Memory-Augmented Adaptive Planning
==========================================
Goal:
Leverage previously stored interaction memories (Phase 4) directly inside planning and chat to produce more context-aware, efficient multi-step strategies while adding scoring, pruning, and observability.

Key Enhancements:
1. Memory Injection into Orchestrator Decisions
   - Retrieve top N relevant memory items (hybrid of recency + keyword/goal match heuristic) before each LLM decision.
   - Provide as `memory_context` array (id, type, importance, snippet, goal) in planner prompt.
   - Cap token usage via truncation strategy (e.g., aggregate <= 1200 chars from memory segment).

2. Memory Scoring & Decay
   - Add dynamic importance scoring: base weight by type (summary > tool_result) adjusted by recency decay and goal similarity.
   - Implement exponential time decay: importance *= exp(-age_hours / HALF_LIFE_HOURS).
   - Introduce periodic summarization: when > capacity threshold * 1.2, combine oldest low-importance tool_results into a synthetic summary memory.

3. Unified Context Fusion (Memory + Retrieval)
   - For planning steps that consider retrieval, merge memory-derived insights with vector search results (RRF or simple interleave) and deduplicate by hashed content snippet.
   - Provide fused slice as `context_snippets` in prompt, preserving original source tags (memory vs retrieval).

4. Audit & Metrics Expansion
   - Extend audit records for /api/agent/auto-plan with: `memory_items_used`, `memory_chars`, `token_estimate`, `latency_ms_per_step`.
   - Track step timing inside orchestrator.

5. New Endpoints
   - GET /api/memory/stats -> {total_items, avg_importance, type_breakdown, last_added_ts}
   - POST /api/memory/summarize (optional admin) -> triggers summarization routine.

6. Guardrails & Redundancy Control
   - Reject repeating same tool with identical inputs in consecutive steps unless rationale includes keyword `refine`.
   - If LLM proposes a final answer before minimum_core_tools (config, default=2) executed and not final_attempt, auto-fallback to next missing core tool.

7. Configuration Additions (config.py)
   - memory_max_tokens_per_prompt (int)
   - memory_relevance_limit (int, default 5)
   - memory_half_life_hours (float)
   - min_core_tools_before_final (int)

Data Structures:
- Extended step record: add `latency_ms`, `memory_used_ids` (list) for that decision phase.
- Memory scoring function: compute_importance(item, goal, now_ts) -> float.

Algorithm Sketch:
1. Before each _decide_next:
   a. Collect recent K (recency list)
   b. Keyword filter by goal tokens; union with recency
   c. Score + sort -> take top M
   d. Truncate content fields.
2. Add memory_context to prompt.
3. After tool execution, recalc and persist dynamic importance (update in-memory object, rewrite line if needed) — or store dynamic score separately (Phase 5a simplified: store original importance, compute dynamic on the fly for ranking only).

Simplifications for Initial Phase 5 Commit:
- Implement heuristic scoring (type weight * recency multiplier * goal_overlap_factor) without persisting changed importance.
- Summarization endpoint stub returning TODO message.

Future (Phase 6+):
- True semantic embedding similarity memory search.
- Token accounting from actual API usage.
- Automated anomaly detection on repeated low-yield tool runs.

Next Action:
- Integrate memory selection + prompt injection into orchestrator.
- Add stats endpoint & config fields.
- Update audit payload.
