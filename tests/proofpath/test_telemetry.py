"""WS5 telemetry: live / simulated / replay separation, qualification milestone, replay export."""
import pytest

from sv.proofpath import telemetry as T
from sv.proofpath.contracts import (BriefVersion, ComparisonSnapshot, Evaluation, Event, EventType,
                                    Finding, FindingStatus, EvidenceStatus, FitDecision,
                                    ProductComparison, Requirement)
from sv.proofpath.repository import Repository


def test_channels_are_counted_separately():
    repo = Repository(":memory:")
    T.record(repo, "e1", "brief_confirmed", "live")
    T.record(repo, "e1", "poc_completed", "simulated")
    T.record(repo, "e1", "poc_completed", "simulated")
    T.record(repo, "e1", "report_created", "replay")
    assert T.counters(repo, "live")["brief_confirmed"] == 1
    assert T.counters(repo, "live")["poc_completed"] == 0
    assert T.counters(repo, "simulated")["poc_completed"] == 2
    assert T.counters(repo, "replay")["report_created"] == 1
    assert T.counters(repo, "live")["report_created"] == 0
    assert [e["name"] for e in T.events(repo, "e1", "live")] == ["brief_confirmed"]


def test_domain_events_split_by_event_channel():
    repo = Repository(":memory:")
    repo.append_event(Event(evaluation_id="e1", type=EventType.poc_started, channel="live"))
    repo.append_event(Event(evaluation_id="e1", type=EventType.poc_started, channel="simulated"))
    T.record(repo, "e1", "poc_started", "replay")
    c = T.channel_counts(repo, "e1")
    assert c["live"] == {"poc_started": 1}
    assert c["simulated"] == {"poc_started": 1}
    assert c["replay"] == {"telemetry.poc_started": 1}


def test_rejects_unknown_names_and_channels():
    repo = Repository(":memory:")
    with pytest.raises(ValueError):
        T.record(repo, "e1", "conversion", "live")
    with pytest.raises(ValueError):
        T.record(repo, "e1", "poc_started", "human")


def _qualified_setup(sso_status=FindingStatus.met, confirm=True):
    repo = Repository(":memory:")
    ev = repo.create_evaluation(Evaluation(session_id="s", preset_id="us_operations", brief_text=""))
    reqs = [Requirement(id="r1", key="us_hosting", label="US", hard=True),
            Requirement(id="r2", key="recovery_demonstrated", label="Rec", hard=True),
            Requirement(id="r3", key="sso", label="SSO", hard=False, weight=1.0)]
    brief = repo.append_brief(BriefVersion(evaluation_id=ev.id, version=1, goal="g", systems=[], requirements=reqs))
    if confirm:
        repo.confirm_brief(brief.id)
    f = lambda rid, key, st: Finding(requirement_id=rid, requirement_key=key, product_id="flowbridge",
                                     status=st, basis=EvidenceStatus.documented, reason="")
    repo.put_comparison(ComparisonSnapshot(
        evaluation_id=ev.id, brief_version_id=brief.id, source_version_ids=[], run_ids=[],
        products=[ProductComparison(product_id="flowbridge", product_name="FlowBridge", decision=FitDecision.fit,
                                    findings=[f("r1", "us_hosting", FindingStatus.met),
                                              f("r2", "recovery_demonstrated", sso_status),
                                              f("r3", "sso", FindingStatus.unknown)])]))
    return repo, ev.id


def test_qualified_evaluation_completed_only_when_conditions_hold():
    repo, eid = _qualified_setup()
    assert T.qualified_evaluation_completed(repo, eid) is True
    assert T.qualified_evaluation_completed(repo, eid) is True        # idempotent
    assert T.counters(repo, "live")["qualified_evaluation_completed"] == 1
    repo, eid = _qualified_setup(sso_status=FindingStatus.unknown)    # unresolved hard constraint
    assert T.qualified_evaluation_completed(repo, eid) is False
    repo, eid = _qualified_setup(confirm=False)                       # brief not confirmed
    assert T.qualified_evaluation_completed(repo, eid) is False


def test_replay_export_is_relabeled_and_never_overwrites(tmp_path):
    repo = Repository(":memory:")
    repo.append_event(Event(evaluation_id="e1", type=EventType.brief_parsed,
                            payload={"brief_text": "secret", "version": 1}))
    T.record(repo, "e1", "brief_confirmed", "live")
    out = tmp_path / "replay.jsonl"
    assert T.export_replay(repo, "e1", out) == 2
    rows = T.load_replay(out)
    assert all(r["channel"] == "replay" and r["badge"] == "Recorded replay" for r in rows)
    assert "brief_text" not in rows[0]["payload"]
    with pytest.raises(FileExistsError):
        T.export_replay(repo, "e1", out)
    assert T.counters(repo, "replay")["brief_confirmed"] == 0          # exporting never counts
