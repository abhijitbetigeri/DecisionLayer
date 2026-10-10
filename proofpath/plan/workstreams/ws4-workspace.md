# WS4: Workspace and report experience

**Time box: 70 minutes.** User-facing names per shared-truth §0 (Decision Layer, Evaluation Workspace).

**Goal:** the evaluation workspace the homepage turns into, plus the immutable report. This is
product UI (taste-skill explicitly does not cover dashboards), so reuse WS3's `tokens.css`
and the same typography, and follow taste-skill's AI-tell bans (no em-dashes, no
decorative dots, no fake previews, status never by colour alone).

**Read first:**
- `../README.md` (playbook rules)
- `../shared-truth.md` §1, §4, §6
- `../../README.md` sections "Homepage and workspace" and "Four-minute presentation"

## Files you own

- `sv/proofpath/templates/workspace.html`, `templates/report.html`, `templates/_partials/`
- `sv/proofpath/static/workspace.js`, `static/workspace.css`
- `sv/proofpath/reports.py`
- `tests/proofpath/test_reports.py`

## Inputs

- Build against `sv/proofpath/examples/*.json` (served by the coordinator's stubs) until real
  modules land.
- `tokens.css` from WS3 (until it lands, use a temporary local copy of the token names with
  placeholder values, deleted at integration).

## Workspace panels (README order)

1. **Confirmed brief** with editable requirements. Editing → `PUT brief` → shows "Confirm to
   re-evaluate", and current conclusions show as invalidated.
2. **Workflow diagram:** CRM source → FlowBridge sync → warehouse destination, as inline
   SVG built from data, labeled as stand-ins.
3. **Requirement matrix** (the hero of the page):
   - per requirement: status (Met/Unmet/Unknown with icon and text), evidence basis
     (Documented/Demonstrated), plan applicability, and citation links that open the source
     document in a side panel
4. **POC panel:**
   - the plan of 4 assertions, the mock label, and "Prove it" / "Cancel"
   - a live event list from polling `GET /events?after=` with no duplicates
   - each assertion with expected vs observed and inspectable artifacts
5. **Comparison table:** 3 products × hard constraints, then score and coverage, gaps listed;
   "Not enough evaluated evidence" when null.
6. **Evidence-change banner:**
   - pending update → "Requires review" (affected rows marked, values unchanged)
   - approved → diff view and "Comparison updated"
   - operator-only approve/reject controls are shown only in an operator session
7. **Report and agent result:**
   - "Create report" → link to the frozen `/reports/{id}`
   - agent result card (from WS5) showing model id, decision and citations

## Persona switch

Technical view foregrounds workflow, evidence and tests; Finance view foregrounds plan
assumptions, quote unknowns and implementation cost. **Switching never changes truth, weights,
statuses or test outcomes.** Test this.

## States (README: never a perpetual spinner)

Loading, empty, failed, cancelled, stale, and "Recorded replay" each get explicit UI. Polling
backs off, and stops on terminal states.

## `reports.py`

`create_report(evaluation_id, brief_version_id, comparison_snapshot_id)` returns an immutable
`ReportVersion` referencing exact source versions and run ids. The HTML view renders only
from the frozen JSON, so after the RelayWorks v2 update an old report still shows v1 evidence. Test
exactly that.

## Done when

- The full journey works against stubs in a browser at 375px and 1280px, both themes.
- The persona switch preserves facts.
- The report stays frozen across an evidence update (test).
- No essential console errors.
- Every status has an icon and a text label.

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
# reports.py
def create_report(repo, evaluation_id: str, brief_version_id: str, comparison_snapshot_id: str) -> ReportVersion  # freeze a full copy of snapshot + brief
```
Templates: `workspace.html` gets `{evaluation_id, operator, demo_mode}`, and JS loads everything from the API (workspace, events polling,
runs). `report.html` gets `{report}` (the frozen ReportVersion as a dict) and must render only from it. Operator controls show only when
`operator` is true; operators log in by POSTing a form `{token}` to `/operator/login`.
