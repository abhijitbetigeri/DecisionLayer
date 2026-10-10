# WS8 QA status

Implemented C1-C3 API journeys, session isolation and operator authorization checks, idempotency and active-run conflicts, foreign/unconfirmed brief regressions. All tests use a fresh temporary data directory and disable LLM calls. Missing modules skip through `find_spec`; present-but-broken modules fail normally.

Added `scripts/smoke.sh` (local temp data on port 8018 or BASE_URL), `scripts/demo_reset.sh` (explicit dedicated directory with protection checks), and acceptance mapping.

Initial verification: 7 failed, 1 passed. All failures originate in first-request `auth.session_id`: POST create returns 401 despite middleware setting new_session. Reported to coordinator with failing test `test_c1_eu_journey`; Starlette State stores attributes under `_state`, so `request.state.__dict__.get` does not retrieve them. Waiting for coordinator fix before final verification.

Final automated verification: focused QA 10 passed; full `uv run pytest tests/proofpath -q` 59 passed in 36.33s. Initial session bug fixed by coordinator. Scripts pass `bash -n`. Curl smoke requires loopback bind permission outside sandbox (startup succeeds but bind returns Errno 1); coordinator informed. No app files, environment files, commits, or existing runs touched. Browser walkthrough and public deployed smoke remain unperformed.

## Coordinator final smoke result

`scripts/smoke.sh` passed all eight checks with permitted localhost binding on port 8018, including source approval, immutable report history, isolation, restart persistence, and fixture deduplication. Full suite: 59 passed. Browser and public-host checks remain unperformed.
