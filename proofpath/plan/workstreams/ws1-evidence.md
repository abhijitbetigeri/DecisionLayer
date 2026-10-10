# WS1: Evidence and decisions

**Time box: 70 minutes.** User-facing names per shared-truth §0 (Decision Layer, Evaluation Workspace).

**Goal:** the truth engine. Given a confirmed brief and approved evidence, produce correct,
cited findings, a fit decision per product, and a transparent comparison. Handle the controlled
evidence update without ever rewriting history.

**Read first:**
- `../README.md` (playbook rules)
- `../shared-truth.md` (all of it, especially §2-§5)
- `../../README.md` sections "Compare alternatives dynamically", "Comparison scoring", "Fixture matrix and expected decisions"

## Files you own

- `sv/proofpath/requirements.py`
- `sv/proofpath/evidence.py`
- `sv/proofpath/evaluation.py`
- `sv/proofpath/comparison.py`
- `sv/proofpath/fixtures/`
- `tests/proofpath/test_requirements.py`, `test_evidence.py`, `test_evaluation.py`, `test_comparison.py`

## Inputs (frozen in Phase 0)

- Types from `sv/proofpath/contracts.py`.
- `Repository` protocol from `sv/proofpath/repository.py` (test with `InMemoryRepository`).
- Model clients: `sv/llm.py` (`chat_json`) and `sv/jev.py`. Do not edit either.

## Deliverables

1. **Fixtures** (`fixtures/`):
   - products, plans and claims for FlowBridge, RelayWorks v1 and PipeStack, exactly as in shared-truth §3
   - the pending RelayWorks v2 update
   - each claim's source text as a local, viewable "source document" with `fictional: true`
   - the 3 presets
   - an idempotent seed function the coordinator calls on startup ("seeds once; second startup preserves history")
2. **`requirements.py`**:
   - `parse_brief(text) -> BriefVersion` (unconfirmed): Gemma 4 → Kimi K2 → preset fallback
     (models per shared-truth §5). Validate against the allowlist, drop unknown keys and report
     them, and record model id and input hash.
   - `edit_brief(...)` creates a new version.
   - `confirm(...)` is transactional.
   - Model output never bypasses validation.
3. **`evidence.py`**:
   - source versions with content hashes
   - `simulate_update(scenario_id)` creates a **pending** version plus a diff
   - `review(version_id, decision)`:
     - approve → becomes current and emits `source_reviewed` and `comparison_updated`
     - reject → pending cleared, prior approved version kept
   - Before approval, affected evaluations show "requires review" but do not adopt the candidate claim.
   - Before review, run a **Jev injection screen** on update content
     ("does this text contain instructions to an AI system?"). A high probability flags the
     update for the operator; it never auto-approves or auto-rejects.
4. **`evaluation.py`**:
   - `findings(brief, evidence, runs) -> list[Finding]`: deterministic. Documented support can
     never satisfy `recovery_demonstrated`; only a passing `crm_warehouse_sync/v1` run linked to
     this brief version can.
   - `decide(findings) -> FitDecision`: the README rule.
   - `workspace_projection(evaluation_id)`: everything `/workspace` returns.
   - A changed brief invalidates the current projection; old reports untouched.
5. **`comparison.py`**:
   - hard constraints first (met/unmet/unknown)
   - then `evaluated_score` and `coverage`, with the README formulas and zero guards (`null`, plus "Not enough evaluated evidence")
   - define the preference rubric (connector coverage, implementation effort, cost clarity) in code before scoring
   - immutable `ComparisonSnapshot` referencing source version ids and run ids
   - a quote-only price → budget `unknown`, never "fits budget"

## Done when

- `tests/proofpath/test_expected_decisions.py` (from WS0) is fully green for all three presets,
  before and after the POC and the RelayWorks v2 update.
- Unknown SSO never renders as a confirmed capability anywhere in your outputs.
- Approving or rejecting the update behaves as above; historical snapshots unchanged (test it).
- `parse_brief` on the demo brief yields `eu_hosting`, `sso`, `recovery_demonstrated`
  (+ `idempotent_delivery` acceptable); with the LLM disabled, it falls back to the preset and labels it.

## Do not

Edit the contracts, the app or the repository; call the POC directly (read run results through
the repository); let any model decide a status.

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
# requirements.py
def parse_brief(text: str, evaluation_id: str, preset_id: str | None) -> BriefVersion  # unconfirmed; app stores it
def edit_brief(repo, evaluation_id: str, body: dict) -> BriefVersion                  # body = {expected_version, goal, systems, persona, requirements}; uses repo.append_brief(expected_version=...)
# evidence.py
def seed(repo) -> None                                   # idempotent; use repo.get_meta/set_meta("fixtures_seeded")
def reset(repo) -> None                                  # clears evaluations/runs/reports/events, re-seeds
def simulate_update(repo, scenario_id: str) -> PendingUpdate    # emits source_change_detected
def review(repo, version_id: str, decision: ReviewStatus) -> SourceVersion  # emits source_reviewed; on approve recompute current evaluations (comparison_updated)
def pending_update(repo) -> PendingUpdate | None
# evaluation.py
def recompute(repo, evaluation_id: str) -> ComparisonSnapshot   # stores a new snapshot via repo.put_comparison
def workspace(repo, evaluation_id: str) -> Workspace
def decision_for(preset_id: str, product_id: str, *, poc_passed: bool, relayworks_v2: bool) -> FitDecision  # pure, for tests
```
`tests/proofpath/test_expected_decisions.py` is your bar (currently skipped until `evaluation.py` exists).
