import os

os.environ["PROOFPATH_ENABLE_LLM"] = "0"

from sv.proofpath import evaluation, evidence, requirements
from sv.proofpath.contracts import (EvidenceStatus, Evaluation, FindingStatus, FitDecision, POCRun,
                                    RunOutcome, RunState, TestResult, TestStatus)
from sv.proofpath.repository import Repository


def _setup(preset="eu_technical"):
    repo = Repository(":memory:")
    evidence.seed(repo)
    ev = repo.create_evaluation(Evaluation(session_id="s", preset_id=preset, brief_text="x"))
    brief = repo.append_brief(requirements.preset_brief(preset, ev.id))
    repo.confirm_brief(brief.id)
    evaluation.recompute(repo, ev.id)
    return repo, ev, brief


def _product(snap, pid):
    return next(p for p in snap.products if p.product_id == pid)


def _finding(p, key):
    return next(f for f in p.findings if f.requirement_key == key)


def test_unknown_sso_is_never_confirmed():
    repo, ev, brief = _setup()
    evaluation.add_passing_run(repo, ev.id, brief.id)
    ws = evaluation.workspace(repo, ev.id)
    fb = _product(ws.comparison, "flowbridge")
    sso = _finding(fb, "sso")
    assert sso.status == FindingStatus.unknown and sso.basis == EvidenceStatus.unknown and not sso.claim_ids
    assert ws.flowbridge_decision == FitDecision.needs_verification
    assert any("Single sign-on" in g for g in fb.gaps)


def test_documentation_never_satisfies_recovery_demonstrated():
    repo, ev, brief = _setup("us_operations")
    snap = repo.latest_comparison(ev.id)
    rw = _finding(_product(snap, "relayworks"), "recovery_demonstrated")
    assert rw.status == FindingStatus.unknown and rw.basis == EvidenceStatus.documented and rw.claim_ids
    fb = _finding(_product(snap, "flowbridge"), "recovery_demonstrated")
    assert fb.status == FindingStatus.unknown


def test_passing_run_for_another_brief_version_does_not_count():
    repo, ev, brief = _setup("us_operations")
    evaluation.add_passing_run(repo, ev.id, brief.id)
    body = {"expected_version": 1, "goal": "g", "systems": [], "requirements": [
        {"key": "us_hosting", "hard": True}, {"key": "recovery_demonstrated", "hard": True}]}
    v2 = requirements.edit_brief(repo, ev.id, body)
    ws = evaluation.workspace(repo, ev.id)
    assert ws.stale and ws.flowbridge_decision is None          # changed brief invalidates projection
    repo.confirm_brief(v2.id)
    snap = evaluation.recompute(repo, ev.id)
    assert _product(snap, "flowbridge").decision == FitDecision.needs_verification


def test_poc_pass_moves_us_operations_to_fit_via_workspace_refresh():
    repo, ev, brief = _setup("us_operations")
    assert evaluation.workspace(repo, ev.id).flowbridge_decision == FitDecision.needs_verification
    run = evaluation.add_passing_run(repo, ev.id, brief.id)
    ws = evaluation.workspace(repo, ev.id)
    assert ws.flowbridge_decision == FitDecision.fit
    assert run.id in ws.comparison.run_ids
    rec = _finding(_product(ws.comparison, "flowbridge"), "recovery_demonstrated")
    assert rec.basis == EvidenceStatus.demonstrated and len(rec.test_result_ids) == 4


def test_failed_run_is_contradicted_not_met():
    repo, ev, brief = _setup("us_operations")
    run = repo.create_run(POCRun(evaluation_id=ev.id, brief_version_id=brief.id, idempotency_key="k",
                                 state=RunState.closed, outcome=RunOutcome.failed))
    repo.put_result(TestResult(run_id=run.id, test_key="single_record", status=TestStatus.fail,
                               expected=1, observed=2))
    ws = evaluation.workspace(repo, ev.id)
    rec = _finding(_product(ws.comparison, "flowbridge"), "recovery_demonstrated")
    assert rec.status == FindingStatus.unknown and rec.basis == EvidenceStatus.contradicted
    assert ws.flowbridge_decision == FitDecision.needs_verification


def test_strict_budget_cost_and_zero_guard():
    repo, ev, _ = _setup("strict_budget")
    snap = repo.latest_comparison(ev.id)
    fb = _product(snap, "flowbridge")
    assert fb.cheapest_qualifying_plan == "business" and fb.monthly_price_usd == 999.0
    assert _finding(fb, "budget_monthly_usd").status == FindingStatus.unmet
    ps = _product(snap, "pipestack")
    assert ps.cheapest_qualifying_plan is None and ps.evaluated_score is None and ps.coverage == 0.0


def test_preferences_never_override_decision():
    repo, ev, _ = _setup("eu_technical")
    snap = repo.latest_comparison(ev.id)
    rw = _product(snap, "relayworks")
    assert rw.evaluated_score == 1.0                       # connectors documented...
    assert rw.decision == FitDecision.needs_verification   # ...but recovery not demonstrated
