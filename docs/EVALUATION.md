# Evaluation Guide

This guide contains 5 concise tests to validate logic, normalization, and UI.

Prerequisites
- .env has valid GROQ_API_KEY
- Start the app: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
- Open http://localhost:8000 for UI

Reset helper
- Reset state before each scenario:
  curl -s -X POST http://localhost:8000/api/simple/reset | jq

1) Surplus-only transfer clamp
- Goal: Transfer never overdrafts a donor (limited by surplus = stock − demand)
- Setup:
  curl -s -X POST -H 'Content-Type: application/x-www-form-urlencoded' \
    -d 'prompt=set demand s1=40 s2=30' http://localhost:8000/api/simple/prompt | jq
  curl -s -X POST -H 'Content-Type: application/x-www-form-urlencoded' \
    -d 'prompt=transfer from s2 to s1 amount=50' http://localhost:8000/api/simple/prompt | jq
- Expect:
  result.steps[0].moved == 30 (S2 surplus 60−30) and state stocks not negative.

2) Run weeks timeline correctness
- Setup:
  curl -s -X POST -H 'Content-Type: application/x-www-form-urlencoded' \
    -d 'prompt=set demand s1=30 s2=20' http://localhost:8000/api/simple/prompt | jq
  curl -s -X POST -H 'Content-Type: application/x-www-form-urlencoded' \
    -d 'prompt=run 2 weeks' http://localhost:8000/api/simple/prompt | jq
- Expect:
  result.steps[0].timeline length == 2
  For each row: consumed.s1 == min(stocks_start_of_week.store1, 30), consumed.s2 == min(stocks_start_of_week.store2, 20), end stocks computed correctly, unmet matches when start < demand.

3) Alias and missing-action normalization
- Commands that should work without "Unknown action":
  curl -s -X POST -H 'Content-Type: application/x-www-form-urlencoded' \
    -d 'prompt=advance 3 weeks' http://localhost:8000/api/simple/prompt | jq
- Expect:
  Interpreted as run_weeks with weeks=3 and returns a timeline with 3 entries.

4) Embedded plan in explain (type vs action)
- To avoid LLM variability, apply a plan directly:
  curl -s -X POST -H 'Content-Type: application/json' \
    -d '{"actions":[{"action":"run_weeks","params":{"weeks":2}}, {"action":"transfer","params":{"from":"s2","to":"s1","amount":10}}]}' \
    http://localhost:8000/api/simple/apply | jq
- Expect:
  result.steps contains a run_weeks step with timeline and a transfer step with transfer object.

5) UI behavior and summaries
- In the browser:
  1) Reset → Set Demand (e.g., S1=30, S2=20) → Run 2 weeks
  2) Ensure tables show two rows; unmet cells in red if > 0
  3) Toggle "Show all weeks" to accumulate subsequent runs
  4) Check "Weeks, Unmet S1/S2" totals update
  5) In Transfers, verify S2→S1 / S1→S2 totals and Net to S1

Tips
- Use "Status" to refresh top cards
- Use browser DevTools Network tab to inspect /api/simple responses
- If the LLM returns a plan with aliases or missing action, the server normalizes it.

Security
- Do not share real API keys; rotate GROQ_API_KEY when necessary.
