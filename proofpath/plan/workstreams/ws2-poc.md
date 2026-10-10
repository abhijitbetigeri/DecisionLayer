# WS2: POC execution (the "Prove it" button)

**Time box: 60 minutes.** User-facing names per shared-truth §0 (Decision Layer, Evaluation Workspace).

**Goal:** real code that demonstrates bounded failure recovery and idempotent delivery against
local mocks, with a durable lifecycle, honest artifacts and guaranteed cleanup. This is the most
important live moment in the demo, so reliability beats polish.

**Read first:**
- `../README.md` (playbook rules)
- `../shared-truth.md` §1
- `../../README.md` sections "Validate with a scoped POC" and "Executable POC definition"

## Files you own

- `sv/proofpath/poc/adapter.py`
- `sv/proofpath/poc/runner.py`
- `sv/proofpath/poc/__init__.py`
- `tests/proofpath/test_poc.py`

## Inputs

- `POCRun`, `TestResult` and event types from `contracts.py`.
- `Repository` run, event and artifact methods (use `InMemoryRepository` in tests).
- The coordinator's `worker.py` calls `runner.execute(run_id)`. Expose exactly that entry point,
  plus `runner.cancel(run_id)` and `runner.recover_interrupted()`.

## Scenario `crm_warehouse_sync/v1`

- **Mock CRM:** a Python source emitting synthetic opportunities (`opp-001`, `opp-002`), labeled
  "Salesforce stand-in".
- **Destination:** a run-specific SQLite file/table, labeled "Snowflake stand-in", with an upsert
  keyed by idempotency key.
- **Failure:** the adapter itself raises a controlled transient error on the first delivery
  attempt of the second record. This is real behaviour, not a UI animation.

**Four assertions, each producing a `TestResult` with expected vs observed:**
1. `opp-001` inserted with the expected field values.
2. The controlled temporary failure occurs before commit; a `poc_attempt` retry event is emitted.
3. A bounded retry succeeds with the **same** idempotency key.
4. A repeated delivery leaves **exactly one** destination record for that key.

## Lifecycle and limits

- **States:** `queued → provisioning → running → completed|failed|cancelled → cleaning_up → closed`.
  Keep the outcome separate from the cleanup state.
- **Limits:** 30-second deadline, max 3 delivery attempts, one concurrent run per evaluation,
  bounded artifact size.
- **Idempotency:** the same `idempotency_key` with the same payload returns the original run; the
  same key with a different payload raises a conflict (the coordinator maps it to 409).
- **Cleanup** on success, failure, timeout, cancellation and startup recovery. Remove the
  temporary destination; keep non-sensitive artifacts: request ids, attempt counts, final count,
  assertion outputs.
- **Optional presentation delay** via `PROOFPATH_DEMO_MODE` (e.g. 600ms between steps so the
  audience can follow). It must never affect outcomes.
- **Events** appended in order: `poc_queued`, `poc_started`, `poc_attempt`, `poc_test_result`
  ×4, `poc_finished`, `poc_cleanup_finished`.

## Done when (all as automated tests)

- A happy run yields 4 passes, with attempt count 2 for the second record and a final destination count of 1.
- Cancel mid-run → `cancelled`, cleanup recorded, no leftover temp files.
- Deadline exceeded (inject a slow adapter) → `failed` with timeout reason, cleanup recorded.
- Duplicate POST with the same key does not execute twice; a different payload with the same key conflicts.
- `recover_interrupted()` marks `running` runs failed/interrupted and cleans up.
- Artifacts are inspectable JSON with no absolute paths leaked.

## Do not

Make outbound network calls, run shell commands, use model output anywhere in execution, or
claim production connector correctness in any string.

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
# poc/runner.py   (also create poc/__init__.py)
def execute(repo, run_id: str) -> POCRun          # worker calls this for queued runs; owns states queued→...→closed
def cancel(repo, run_id: str) -> POCRun           # idempotent
def recover_interrupted(repo) -> list[str]        # called once at startup
```
The app creates runs (idempotency and the one-active-run rule are enforced in `app.py`, 409 on conflict) and emits `poc_queued`.
You emit `poc_started`, `poc_attempt`, `poc_test_result`, `poc_finished` and `poc_cleanup_finished`, and store `TestResult`s and `Artifact`s
(`test_key` values: `insert_first`, `transient_failure`, `bounded_retry`, `single_record`). Run directories live under
`$PROOFPATH_DATA_DIR/runs/<run_id>/`. Never derive paths from user input.
