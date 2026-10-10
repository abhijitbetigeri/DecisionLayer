# WS5: Buyer agent, Visitor Lab measurement, Jev, telemetry

**Time box: 70 minutes.** Coframe SDK work is cut (no real project id); keep only internal events
and the `data-cf-slot` contract.

**Goal:** prove the "agents are first-class visitors" claim with numbers, and keep measurement
honest. Covers the organizer themes directly: multi-agent simulator, personal agent protocol (the
confirmed brief), agent-to-agent (`agent-evaluation`).

**Read first:**
- `../README.md` (playbook rules)
- `../shared-truth.md` §1, §4, §5
- `../../README.md` sections "LLM and deterministic execution boundaries", "Coframe integration plan", "Event contract and replay"
- `ARCHITECTURE.md` (Second Visitor engine)

## Files you own

- `sv/proofpath/agent.py`
- `sv/proofpath/telemetry.py`
- `sv/proofpath/sim_bridge.py`
- `tests/proofpath/test_agent.py`, `test_telemetry.py`

## Deliverables

1. **`agent.py`** (backs `POST /evaluations/{id}/agent-evaluation`):
   - a bounded tool-calling buyer agent (gpt-oss-120b → Qwen3 235B → labeled "Rule-based
     evaluation") that reads only `GET /agent-context` (same facts, ids and citations as the
     human view) and returns `{decision, per-requirement status, citations, model_id, input_version}`
   - limits: max 6 turns, 60s
   - **reject citations to nonexistent claim/test ids**
   - score the result against the expected decision (shared-truth §4) and store it
2. **`sim_bridge.py`**: the headline numbers, using the existing simulator as a library (do not
   edit `sv/simulator/*` or `sv/facts.py`).
   - **Arm A:** buyer agents read the FlowBridge homepage as fetched text (no JS).
   - **Arm B:** buyer agents read `agent-context`.
   - Same 3 presets, same 4 open models (shared-truth §5), n ≥ 3 each.
   - Correct = matches the expected decision. Write results to `runs/proofpath-*.jsonl` using
     the existing event-log style, plus a summary JSON the report and demo slide read.
3. **Jev checks:** a claim-supported check on any model-written summary text before display
   (unsupported → fall back to the deterministic template). Helper for WS1's injection screen if
   they request it. Use `sv/jev.py`; never for numbers or dates.
4. **`telemetry.py`**:
   - internal events `brief_confirmed`, `poc_started`, `poc_completed`, `report_created`,
     `qualified_evaluation_completed` (only when the brief is confirmed and current, no
     unresolved hard constraints, evidence current)
   - **human, simulated and replay events are kept separate** (a field, and separate counters)
5. **Coframe:** cut for this build. Do not create `coframe.py` or the adapter.
6. **Replay export:**
   - a command that exports sanitized JSONL of one full demo evaluation
   - a replay mode that shows the "Recorded replay" badge and never emits live conversions or fakes a live POC

## Done when

- The agent-evaluation endpoint returns a cited decision for `eu_technical` that matches
  `needs_verification` with gpt-oss-120b; with the LLM disabled it returns the labeled rule-based result.
- `sim_bridge` produces Arm A vs Arm B correct-decision rates with n and 95% Wilson intervals
  (reuse `sv/simulator/run.py:wilson`).
- Telemetry separation is tested.

## Phase 0 is done: what exists now

- `sv/proofpath/contracts.py`: frozen types (import these, never redefine).
- `sv/proofpath/repository.py`: `Repository(path)`; use `Repository(":memory:")` in tests. Raises
  `ConflictError` (HTTP 409) and `NotFoundError` (HTTP 404).
- `sv/proofpath/app.py`: every route is live. Routes call **your functions below** if your module
  exists; otherwise they serve `sv/proofpath/examples/*.json` with `"stub": true`.
- Stub workspace for UI work: `/evaluations/11111111-1111-4111-8111-111111111111`.
- Run: `uv run uvicorn sv.proofpath.app:app --port 8001`. Tests: `uv run pytest tests/proofpath -q`.
- Events: append with `repo.append_event(Event(evaluation_id=..., run_id=..., type=EventType.X, payload={...}))`.
  The app already emits `brief_parsed`, `brief_confirmed`, `workspace_generated`, `poc_queued`,
  `report_created` and `agent_evaluation_finished`, so do not emit those yourself.

## Functions the app calls (frozen signatures)

```python
# agent.py
def agent_context(repo, evaluation_id: str) -> dict          # same facts, ids, citations and limitations as the human workspace
def run_agent_evaluation(repo, evaluation_id: str, model: str | None) -> AgentResult  # stores it via repo.put_agent_result
# telemetry.py
def record(repo, evaluation_id: str, name: str, channel: str = "live") -> None
def qualified_evaluation_completed(repo, evaluation_id: str) -> bool
```
`sim_bridge.py` drives the app in-process with `fastapi.testclient.TestClient(app)` (no server needed) and fetches `/` as text for Arm A.
