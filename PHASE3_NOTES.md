Phase 3: Orchestrated Multi-Step Agent Planning
==============================================
Goal:
Enable an autonomous planning loop: interpret user intent, decide which deterministic tools (Phase 1) and retrieval (Phase 2) to call, gather results, refine, and produce a final structured answer with traceability.

Key Additions (planned):
1. Orchestrator module (e.g., src/agent/orchestrator.py)
   - Input: user goal (string)
   - Internal Loop (bounded by MAX_AUTO_STEPS):
     a. Reason about next best action (LLM) -> JSON: {"action_type":"tool|retrieve|final", "tool_name"?, "tool_input"?:{}, "notes":"..."}
     b. If tool: invoke via existing invoke_tool, capture output, append to working context
     c. If retrieve: call retrieve_relevant tool, append snippets to context
     d. Maintain step transcript (thought, action, result summary)
     e. Stop on action_type=final or step cap
   - Output: {"final_answer": str, "steps": [...], "used_tools": [...], "retrieval_docs": [...]} plus correlation_id

2. New Endpoint: POST /api/agent/auto-plan
   - Form fields: goal (str), max_steps? (optional override)
   - Returns orchestrator output

3. Audit: Write full orchestration trace including each step.

Settings Update:
- Added max_auto_steps (default 5) in config for safety.

LLM Prompts (conceptual):
- Step Planner Prompt: Provide current goal, elapsed steps, available tools (names + short descriptions + JSON schema summary), last tool results (truncated), retrieved docs (truncated). Ask for STRICT JSON with fields: action_type, reasoning, (tool_name & tool_input) OR (final_answer if action_type=final).

Data Structures:
- Step record: {"step": n, "reasoning": str, "action": { ... }, "result_excerpt": str}
- Working memory: {"tool_results": [...], "retrieved": [...]} limited for token control.

Safety / Controls:
- Enforce JSON parse; on parse failure attempt one retry with clarification.
- Hard cap steps via max_auto_steps or user override (min 1, max 15).
- Truncate any single tool result to 2k chars before feeding back to LLM.

Minimal Initial Implementation Plan:
1. Create orchestrator class with run(goal, max_steps) coroutine.
2. Implement _llm_decide_next(...) using Groq model (temperature low 0.1-0.2).
3. Integrate existing tool list + retrieval.
4. Expose endpoint and audit record.

Future Enhancements:
- Add scoring for each tool result (relevance, confidence) using a secondary lightweight heuristic.
- Add guardrail for forbidden actions (e.g., if future external tools are added).
- Add cost tracking (token usage from Groq responses if accessible).
- Add parallel retrieval + planning for first step (speculative execution).

Next Action:
- Implement orchestrator scaffolding file and endpoint when approved.
