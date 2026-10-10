import os

os.environ["PROOFPATH_ENABLE_LLM"] = "0"

import pytest

from sv.proofpath import evaluation, evidence
from sv.proofpath.contracts import (Evaluation, EventType, FindingStatus, FitDecision, ReportVersion,
                                    ReviewStatus)
from sv.proofpath.repository import ConflictError, Repository
from sv.proofpath.requirements import preset_brief


def _setup(preset="eu_technical"):
    repo = Repository(":memory:")
    evidence.seed(repo)
    ev = repo.create_evaluation(Evaluation(session_id="s", preset_id=preset, brief_text="x"))
    brief = repo.append_brief(preset_brief(preset, ev.id))
    repo.confirm_brief(brief.id)
    snap = evaluation.recompute(repo, ev.id)
    return repo, ev, brief, snap


def _rw(snap):
    return next(p for p in snap.products if p.product_id == "relayworks")


def test_seed_is_idempotent_and_preserves_history():
    repo, *_ = _setup()
    upd = evidence.simulate_update(repo, "relayworks_v2", screen=False)
    evidence.review(repo, upd.source_version.id, ReviewStatus.approved)
    evidence.seed(repo)                                  # second startup
    ids = [s.id for s in repo.list_source_versions()]
    assert ids.count("src-relayworks-v1") == 1 and "src-relayworks-v2" in ids
    assert {s.source_id: s.id for s in evidence.current_sources(repo)}["relayworks-docs"] == "src-relayworks-v2"


def test_pending_update_is_not_adopted_before_review():
    repo, ev, brief, snap = _setup()
    upd = evidence.simulate_update(repo, "relayworks_v2", screen=False)
    assert upd.source_version.review_status == ReviewStatus.pending
    assert upd.source_version.supersedes == "src-relayworks-v1"
    assert ev.id in upd.affected_evaluation_ids
    assert any(d["requirement_key"] == "eu_hosting" for d in upd.diff)
    ws = evaluation.workspace(repo, ev.id)
    assert ws.stale and ws.pending_update is not None
    assert "src-relayworks-v2" not in ws.comparison.source_version_ids
    assert _rw(ws.comparison).cheapest_qualifying_plan == "business"
    assert [e.type for e in repo.list_events(ev.id)][-1] == EventType.source_change_detected


def test_approve_makes_current_recomputes_and_keeps_old_snapshot_and_report():
    repo, ev, brief, snap = _setup("strict_budget")
    report = repo.create_report(ReportVersion(evaluation_id=ev.id, brief_version_id=brief.id,
                                              comparison_snapshot_id=snap.id, run_ids=[], findings=[],
                                              decision=FitDecision.not_fit, snapshot=snap, brief=brief))
    upd = evidence.simulate_update(repo, "relayworks_v2", screen=False)
    sv = evidence.review(repo, upd.source_version.id, ReviewStatus.approved)
    assert sv.review_status == ReviewStatus.approved
    new = repo.latest_comparison(ev.id)
    assert new.id != snap.id and "src-relayworks-v2" in new.source_version_ids
    rw = _rw(new)
    budget = next(f for f in rw.findings if f.requirement_key == "budget_monthly_usd")
    assert budget.status == FindingStatus.unknown and rw.monthly_price_usd is None
    assert rw.cheapest_qualifying_plan == "enterprise" and rw.decision == FitDecision.needs_verification
    # history untouched
    assert repo.get_comparison(snap.id).model_dump() == snap.model_dump()
    assert _rw(repo.get_report(report.id).snapshot).monthly_price_usd == 899.0
    assert repo.get_source_version("src-relayworks-v1").review_status == ReviewStatus.approved
    types = [e.type for e in repo.list_events(ev.id)]
    assert EventType.source_reviewed in types and types[-1] == EventType.comparison_updated
    assert evidence.pending_update(repo) is None
    with pytest.raises(ConflictError):
        evidence.review(repo, sv.id, ReviewStatus.approved)


def test_reject_clears_pending_and_keeps_prior_version():
    repo, ev, brief, snap = _setup()
    upd = evidence.simulate_update(repo, "relayworks_v2", screen=False)
    sv = evidence.review(repo, upd.source_version.id, ReviewStatus.rejected)
    assert sv.review_status == ReviewStatus.rejected
    assert evidence.pending_update(repo) is None
    assert {s.source_id: s.id for s in evidence.current_sources(repo)}["relayworks-docs"] == "src-relayworks-v1"
    ws = evaluation.workspace(repo, ev.id)
    assert not ws.stale and "src-relayworks-v1" in ws.comparison.source_version_ids
    # re-simulating keeps the rejected record in history
    again = evidence.simulate_update(repo, "relayworks_v2", screen=False)
    assert again.source_version.id != sv.id
    assert repo.get_source_version(sv.id).review_status == ReviewStatus.rejected


def test_injection_screen_flags_but_never_decides(monkeypatch):
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "1")
    from sv import jev
    monkeypatch.setattr(jev, "yes_probability", lambda state, q: 0.97)
    repo, ev, *_ = _setup()
    upd = evidence.simulate_update(repo, "relayworks_v2")
    assert upd.injection_flag == 0.97
    assert upd.source_version.review_status == ReviewStatus.pending


def test_injection_screen_unavailable_is_tolerated(monkeypatch):
    monkeypatch.setenv("PROOFPATH_ENABLE_LLM", "1")
    from sv import jev

    def boom(*a, **k):
        raise jev.JevUnavailable("no key")

    monkeypatch.setattr(jev, "yes_probability", boom)
    repo, *_ = _setup()
    assert evidence.simulate_update(repo, "relayworks_v2").injection_flag is None


def test_reset_clears_demo_state_and_reseeds():
    repo, ev, *_ = _setup()
    evidence.simulate_update(repo, "relayworks_v2", screen=False)
    evidence.reset(repo)
    assert repo.list_runs() == [] and evidence.pending_update(repo) is None
    assert len(evidence.current_sources(repo)) == 3
