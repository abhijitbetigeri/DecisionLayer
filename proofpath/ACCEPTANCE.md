# Decision Layer acceptance evidence

QA commands (no external model calls, temporary data only):

```bash
uv run pytest tests/proofpath/test_api_journey.py tests/proofpath/test_isolation.py -q
scripts/smoke.sh
# Existing deployment, optional operator authorization supplied via environment:
BASE_URL=https://your-deployment.example scripts/smoke.sh
# Explicit dedicated local demo database, stop the existing server first:
PROOFPATH_DATA_DIR=/tmp/decision-layer-demo scripts/demo_reset.sh
```

## Required end-to-end checks

- [x] Fresh startup seeds once; restart preserves evaluations/history: `scripts/smoke.sh` restart plus source-version count check.
- [x] Three presets match expected decisions, SSO stays unknown: `test_c1_eu_journey`, `test_us_operations_reaches_fit`, `test_c2_pending_approve_preserves_report`, `test_expected_decisions.py`.
- [ ] Brief edits require confirmation and invalidate current conclusions without rewriting reports: `test_unconfirmed_brief_cannot_run`; edit an existing brief manually, verify stale banner and re-confirmation, compare old report JSON.
- [ ] Persona switching preserves facts, scores, references: `test_reports.py::test_persona_switch_is_presentation_only`; browser walkthrough in both views.
- [x] Live POC records actual attempts, bounded retry, idempotency, artifacts: `test_c1_eu_journey`, `test_poc.py`, `scripts/smoke.sh`.
- [x] Duplicate runs execute once; cancellations, failures, expiry clean resources: `test_run_idempotency_and_active_conflict`, `test_poc.py` lifecycle tests.
- [x] Pending evidence cannot become truth; approval updates and rejection preserves: `test_c2_pending_approve_preserves_report`, `test_c2_rejection_preserves_approved_evidence`.
- [ ] Reports retain source versions/results; unknown coverage and zero division handled (report immutability passed; dedicated zero-coverage edge verification still needed): `test_c2_pending_approve_preserves_report`, `test_reports.py`, decision/comparison unit tests.
- [x] Human/agent evidence and IDs agree; fake model citations rejected: `test_c3_agent_uses_workspace_ids_and_rule_based_fallback`, `test_agent.py` citation validation tests.
- [x] Cross-session evaluation/report/run/artifact reads blocked; operator authorization required: `test_second_session_cannot_read_owned_objects`, `test_operator_routes_require_authorization`, `test_foreign_brief_cannot_be_confirmed_or_run`.
- [ ] Coframe absent works; live/sim/replay counters separate: full journey with no Coframe configuration, telemetry tests and manual Visitor Lab inspection.
- [ ] Browser homepage through report works with visible failures and no essential console errors: manual four-minute walkthrough at 1280px/375px in light/dark themes. **Not yet performed.**

## Results

Latest enhancement verification: **91 automated tests passed**. `scripts/browser_acceptance.py` passed in installed Chrome with temporary data and models disabled: US operations becomes Fit, EU remains Needs verification with SSO next step, four live assertions, decision timeline refresh, report creation, competitor source approval, frozen history, desktop/mobile overflow checks, Visitor Lab actual results, and no page JavaScript errors. Added API ownership checks for insights and historical source links. This does not establish production readiness or real-model availability.

`uv run pytest tests/proofpath -q`: **59 passed in 36.33s**. The focused QA suite passed **10 tests**. Initial QA identified a first-request session initialization bug; the coordinator fixed it and the regression passes. Shell syntax checks pass. Permitted localhost curl smoke passed all eight stages: health, create/confirm, idempotency/conflict, four live assertions, demonstrated recovery/report, approved update/frozen history, isolation/operator authorization, and restart persistence without duplicate fixtures. Automated results do not establish unperformed browser, deployed-host, or real-model checks.

## Scope and limitations

Products/evidence are fictional, POC integrations are local mocks, and rule-based evaluation is explicitly labeled. Deployment smoke without an operator token skips the controlled source update. Reset refuses ambiguous/protected paths and existing directories without a `proofpath.db`; it starts a foreground server and does not kill another server. No `.env` files were read.
