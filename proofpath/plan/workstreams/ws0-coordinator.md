# WS0: Coordinator / API (Phase 0 freeze, then integration)

**Read first:** `../README.md` (playbook), `../shared-truth.md`, `../../README.md` sections
"Contract freeze", "HTTP contracts", "Event contract and replay".

## Phase 0 deliverables (must finish before any other agent starts)

1. **`sv/proofpath/contracts.py`**: every type in the README "Contract freeze" table as Pydantic
   models, schema version `1`, UUID ids, UTC ISO timestamps, string enums:
   - FindingStatus `met/unmet/unknown`
   - EvidenceStatus `documented/demonstrated/unknown/contradicted`
   - ReviewStatus `pending/approved/rejected`
   - TestStatus `pass/fail/blocked`
   - FitDecision `fit/not_fit/needs_verification`
   - POC states `draft → awaiting_approval → queued → provisioning → running → completed/failed/cancelled → cleaning_up → closed`
   - Event types from the README
   - Plus `Envelope` / `ErrorEnvelope`.
2. **`sv/proofpath/examples/*.json`**: one valid example per HTTP response, generated from the
   models (so they validate), using the `eu_technical` preset and the fixture names. WS4 builds
   the UI against these.
3. **`sv/proofpath/repository.py`**: the shared interface from the README ("Shared repository
   interface to freeze") as a `Repository` protocol, plus two implementations:
   - `SqliteRepository` (standard-library sqlite3, transactions for multi-record writes, migrations on startup)
   - `InMemoryRepository` (for other agents' unit tests)
4. **`sv/proofpath/app.py`**: FastAPI app on :8001, serving:
   - every route in the README HTTP table, under `/api/v1`, with `{schema_version, data}` envelopes
   - **stubs that return the example payloads** until the real modules land
   - `/` → home template, `/evaluations/{id}` → workspace template, `/reports/{id}` → report template
   - static mount at `/static`
5. **`sv/proofpath/auth.py`**:
   - local session cookie issued on first visit, with evaluation-ownership checks
   - operator token from `PROOFPATH_OPERATOR_TOKEN`, checked server-side only, never sent to page JS
6. **`sv/proofpath/worker.py`**:
   - one bounded in-process worker that processes queued POC runs from SQLite
   - on startup, mark interrupted `running` jobs `failed/interrupted` and clean their run directories
7. **`tests/proofpath/test_expected_decisions.py`**: the expected-decision tables in
   `shared-truth.md` §4 as parametrized tests, red until WS1 lands.
8. **Config:** read `PROOFPATH_DATA_DIR` (default `./.proofpath-data`, gitignored),
   `PROOFPATH_DEMO_MODE`, `PROOFPATH_OPERATOR_TOKEN`, `PROOFPATH_COFRAME_PROJECT_ID`,
   `PROOFPATH_ENABLE_LLM`. Add them to `.env.example` with descriptions, no values.
9. **Dependencies:** add `pydantic` (already transitively present) and `pytest` (dev) only.

**Phase 0 exit:**
- `uv run uvicorn sv.proofpath.app:app --port 8001` serves every route.
- `uv run pytest tests/proofpath -q` runs, with the decision tests failing as expected.
- `examples/*.json` validate against the models.

## Phase 1 (while agents build)

Answer contract questions, keep the status board current, and do nothing else that touches
files owned by agents.

## Phase 2: integration

Follow [../integration.md](../integration.md): replace stubs with real modules one checkpoint at
a time, run the smoke script after each.

## Phase 3

Deployment ([../deployment.md](../deployment.md)), demo reset command, replay export,
acceptance checklist, handoff docs in `proofpath/`.

## Rules

- Contract changes: update the model, the example JSON, and notify consumers in one step.
- Bind to `127.0.0.1` by default. Public deployment only per deployment.md.
- Never read or print `.env` values.
