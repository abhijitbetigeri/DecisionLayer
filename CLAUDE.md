# Second Visitor: working notes for agents

Built for the AGI House × Coframe Living Internet Build Day (2026-10-10). Judges include Coframe
and the Glasp/Hashiri founder. Organizer themes: multi-agent simulator on the web, personal agent
protocol, agent-to-agent; also code gen.

**Direction: ProofPath is the product** (proofpath/README.md). Second Visitor (`sv/`) is its engine,
and the vendor-site optimization loop is the Coframe-style top of funnel. Read PLAN.md first, then
proofpath/plan/README.md (multi-agent playbook; each workstream has a self-contained brief in
proofpath/plan/workstreams/), then ARCHITECTURE.md for the engine. The landing page must be built
with the `design-taste-frontend` skill (taste-skill).

## Conventions
- `data/facts.yaml` is the only source of truth. Never hard-code a fact in a template; derive it
  from `facts` (use the `plans_with()` helper). Hard-coded facts make variants inconsistent.
- Variant D must stay a *consistent* lie via `fact_overrides`. A lie only in a banner doesn't
  fool agents, because they trust the tables, and then the demo shows nothing.
- Pass/fail comes from the oracle in `sv/facts.py`, never from an LLM.
- Report results with n and Wilson intervals. n=30 per variant still has overlapping intervals.
- The event schema in `sv/events.py` is frozen: add fields, never rename them.
- Do not commit or push unless the user asks.

## Gotchas
- Respan model ids that work: `claude-haiku-4-5-20251001`, `gpt-5-mini`,
  `openrouter/google/gemini-2.5-flash`, `claude-sonnet-5-5`. A bare `gemini/...` id fails.
- The stored Respan base URL omits `/api`; `sv/llm.py` appends it.
- macOS has no `timeout` command; use the tool's timeout instead.
- The guard is strict: "unsupported" usually means facts.yaml is missing a fact. Add the fact
  rather than loosening the prompt.
