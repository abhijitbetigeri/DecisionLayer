# WS8: QA, smoke tests and acceptance (external agent)

**Time box: 60 minutes.** Goal: integration is fast because the checks already exist. You write
the end-to-end tests and the smoke script **against the frozen contracts now**; they go green
as the other workstreams land.

**Read first:**
- `../README.md` (rules)
- `../integration.md` (checkpoints C1-C4, smoke script steps)
- `../shared-truth.md` §4 (expected decisions)
- `sv/proofpath/contracts.py`, `sv/proofpath/app.py`, `sv/proofpath/examples/*.json`
- `proofpath/README.md` "Acceptance checklist"

## Files you own

- `tests/proofpath/test_api_journey.py`
- `tests/proofpath/test_isolation.py`
- `scripts/smoke.sh`
- `scripts/demo_reset.sh`
- `proofpath/ACCEPTANCE.md`
- Your status file: `proofpath/plan/status/ws8.md`

## Deliverables

1. **`test_api_journey.py`** (fastapi `TestClient`, fresh temp `PROOFPATH_DATA_DIR` per test):
   - **C1:** create (demo brief) → confirm → FlowBridge `needs_verification` with SSO unknown →
     start run → poll until closed → 4 passes → recovery `met` with basis `demonstrated` → still
     `needs_verification` → create report
   - `us_operations` reaches `fit` after the run
   - **C2:** operator simulates the RelayWorks v2 update → pending does not change decisions → approve →
     `comparison_updated` event → the earlier report unchanged → reject path keeps prior evidence
   - **C3:** `agent-context` uses the same ids as the workspace; `agent-evaluation` with
     `PROOFPATH_ENABLE_LLM=0` returns `mode == "rule_based"`
   - Mark each test `skipif` when its module is missing (`importlib.util.find_spec`), so the suite
     stays green-or-skipped while others build.
2. **`test_isolation.py`:**
   - a second session gets 404 on the first session's evaluation, report, run and artifact
   - operator routes without a token → 403
   - idempotent run POST returns the same id; a different payload with the same key → 409;
     a second active run → 409
3. **`scripts/smoke.sh`:**
   - starts the app on a temp data dir and port 8018
   - curl + `python -c` JSON checks for the same journey
   - restarts on the same data dir: history kept, fixtures not duplicated
   - prints PASS/FAIL per step and exits non-zero on failure
   - accepts `BASE_URL` to run against a deployed URL
4. **`scripts/demo_reset.sh`:** clears only `PROOFPATH_DATA_DIR` (never `runs/` or Pulse), then
   restarts.
5. **`proofpath/ACCEPTANCE.md`:**
   - the README's "Required end-to-end checks" as a checklist, each mapped to the test or manual step that proves it
   - fill in results as checks go green

## Rules

Never edit application modules; if a test reveals a bug, write it up in your status file with
the failing test name and leave the fix to the owner. Use port 8018 and a temp data dir only.
Never read `.env`.
