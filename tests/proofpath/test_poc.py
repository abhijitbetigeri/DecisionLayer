"""WS2: POC runner for crm_warehouse_sync/v1 (lifecycle, assertions, cleanup, artifacts)."""
from __future__ import annotations

import json
import threading
import time
import uuid

import pytest

from sv.proofpath.contracts import (BriefVersion, Evaluation, Event, EventType, POCRun, RunOutcome, RunState, TestStatus)
from sv.proofpath.poc import runner
from sv.proofpath.poc.adapter import SyncAdapter
from sv.proofpath.repository import Repository


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PROOFPATH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PROOFPATH_DEMO_MODE", raising=False)
    return tmp_path


@pytest.fixture
def repo(data_dir):
    return Repository(":memory:")


def _queue(repo) -> POCRun:
    ev = repo.create_evaluation(Evaluation(session_id="s1", brief_text="demo"))
    run = repo.create_run(POCRun(evaluation_id=ev.id, brief_version_id="b1",
                                 idempotency_key=str(uuid.uuid4()), payload_hash="h"))
    repo.append_event(Event(evaluation_id=ev.id, run_id=run.id, type=EventType.poc_queued))
    return run


def _types(repo, run):
    return [e.type for e in repo.list_events(run.evaluation_id) if e.run_id == run.id]


def _assert_clean(data_dir, run_id):
    run_dir = data_dir / "runs" / run_id
    assert not run_dir.exists(), f"leftover: {list(run_dir.iterdir())}"


def _assert_no_paths(repo, run_id, data_dir):
    blob = json.dumps([a.model_dump(mode="json") for a in repo.list_artifacts(run_id)]
                      + [r.model_dump(mode="json") for r in repo.list_results(run_id)])
    assert str(data_dir) not in blob
    assert ".sqlite" not in blob
    for marker in ("/Users/", "/tmp/", "/private/", "/home/", "C:\\"):
        assert marker not in blob


def _assert_order(types):
    assert types[0] == EventType.poc_queued
    assert types[1] == EventType.poc_started
    assert types[-2] == EventType.poc_finished
    assert types[-1] == EventType.poc_cleanup_finished
    assert types.count(EventType.poc_finished) == 1
    assert types.count(EventType.poc_cleanup_finished) == 1


def test_happy_path(repo, data_dir):
    run = _queue(repo)
    final = runner.execute(repo, run.id)
    assert final.state == RunState.closed
    assert final.outcome == RunOutcome.passed
    assert final.error is None
    results = {r.test_key: r for r in repo.list_results(run.id)}
    assert set(results) == set(runner.TEST_KEYS)
    assert all(r.status == TestStatus.pass_ for r in results.values()), {k: r.observed for k, r in results.items()}
    assert results["bounded_retry"].observed["attempts"] == 2
    assert results["single_record"].observed["destination_rows_for_key"] == 1
    assert results["transient_failure"].observed["rows_committed"] == 0

    [art] = repo.list_artifacts(run.id)
    assert art.name == "delivery_log.json"
    assert art.content["attempts_by_record"] == {"opp-001": 1, "opp-002": 2}
    assert art.content["destination_count"] == {"opp-001": 1, "opp-002": 1}
    assert len(art.content["request_ids"]) == len(set(art.content["request_ids"])) == 4
    retry_keys = {a["idempotency_key"] for a in art.content["attempts"] if a["record"] == "opp-002"}
    assert len(retry_keys) == 1
    assert all(art.id in r.artifact_ids for r in results.values())
    assert len(json.dumps(art.content)) <= runner.MAX_ARTIFACT_BYTES

    types = _types(repo, run)
    _assert_order(types)
    assert types.count(EventType.poc_test_result) == 4
    attempts = [e for e in repo.list_events(run.evaluation_id) if e.type == EventType.poc_attempt]
    assert any(e.payload.get("ok") is False and e.payload.get("will_retry") for e in attempts)
    first_attempt = types.index(EventType.poc_attempt)
    assert types.index(EventType.poc_started) < first_attempt < types.index(EventType.poc_finished)
    _assert_clean(data_dir, run.id)
    _assert_no_paths(repo, run.id, data_dir)


def test_execute_is_noop_for_non_queued(repo, data_dir):
    run = _queue(repo)
    runner.execute(repo, run.id)
    n = len(repo.list_events(run.evaluation_id))
    again = runner.execute(repo, run.id)
    assert again.state == RunState.closed
    assert len(repo.list_events(run.evaluation_id)) == n
    assert len(repo.list_results(run.id)) == 4


class SlowAdapter(SyncAdapter):
    def __init__(self, dest, delay=0.4):
        super().__init__(dest)
        self.delay = delay

    def deliver(self, record, idempotency_key, request_id):
        time.sleep(self.delay)
        super().deliver(record, idempotency_key, request_id)


def test_cancel_mid_run(repo, data_dir):
    run = _queue(repo)
    seen_running = threading.Event()

    def factory(dest):
        seen_running.set()
        return SlowAdapter(dest, delay=0.3)

    out = {}
    t = threading.Thread(target=lambda: out.setdefault("run", runner.execute(repo, run.id, adapter_factory=factory)))
    t.start()
    assert seen_running.wait(5)
    time.sleep(0.4)
    cancelled = runner.cancel(repo, run.id)
    t.join(10)
    assert not t.is_alive()
    final = repo.get_run(run.id)
    assert final.state == RunState.closed
    assert final.outcome == RunOutcome.cancelled
    assert cancelled.outcome in (RunOutcome.cancelled, None)
    types = _types(repo, run)
    _assert_order(types)
    statuses = {r.test_key: r.status for r in repo.list_results(run.id)}
    assert set(statuses) == set(runner.TEST_KEYS)
    assert TestStatus.blocked in statuses.values()
    # idempotent
    assert runner.cancel(repo, run.id).state == RunState.closed
    _assert_clean(data_dir, run.id)
    _assert_no_paths(repo, run.id, data_dir)
    time.sleep(0.5)                                # the fenced scenario thread must not write late
    assert _types(repo, run) == types


def test_cancel_queued_run(repo, data_dir):
    run = _queue(repo)
    final = runner.cancel(repo, run.id)
    assert final.state == RunState.closed and final.outcome == RunOutcome.cancelled
    assert runner.execute(repo, run.id).state == RunState.closed
    assert EventType.poc_started not in _types(repo, run)
    assert _types(repo, run)[-1] == EventType.poc_cleanup_finished


def test_deadline_timeout(repo, data_dir):
    run = _queue(repo)
    started = time.monotonic()
    final = runner.execute(repo, run.id, deadline_s=0.5, adapter_factory=lambda d: SlowAdapter(d, delay=5))
    assert time.monotonic() - started < 3
    assert final.state == RunState.closed
    assert final.outcome == RunOutcome.timed_out
    assert "deadline" in final.error
    types = _types(repo, run)
    _assert_order(types)
    cleanup = [e for e in repo.list_events(run.evaluation_id) if e.type == EventType.poc_cleanup_finished][0]
    assert cleanup.payload["leftover_temp_files"] is False
    assert all(r.status == TestStatus.blocked for r in repo.list_results(run.id))
    _assert_clean(data_dir, run.id)
    _assert_no_paths(repo, run.id, data_dir)


def test_adapter_that_never_fails_is_reported_as_failed_assertion(repo, data_dir):
    run = _queue(repo)
    final = runner.execute(repo, run.id, adapter_factory=lambda d: SyncAdapter(d, fail_first_attempt_for=()))
    assert final.outcome == RunOutcome.failed
    statuses = {r.test_key: r.status for r in repo.list_results(run.id)}
    assert statuses["transient_failure"] == TestStatus.fail
    assert statuses["insert_first"] == TestStatus.pass_
    _assert_clean(data_dir, run.id)


def test_recover_interrupted(repo, data_dir):
    run = _queue(repo)
    run.state = RunState.running
    repo.update_run(run)
    leftover = data_dir / "runs" / run.id
    leftover.mkdir(parents=True)
    (leftover / "destination.sqlite").write_bytes(b"x")
    queued = _queue(repo)

    recovered = runner.recover_interrupted(repo)
    assert recovered == [run.id]
    final = repo.get_run(run.id)
    assert final.state == RunState.closed
    assert final.outcome == RunOutcome.interrupted
    assert repo.get_run(queued.id).state == RunState.queued
    types = _types(repo, run)
    assert types[-2:] == [EventType.poc_finished, EventType.poc_cleanup_finished]
    _assert_clean(data_dir, run.id)
    assert runner.recover_interrupted(repo) == []


def test_stage_delay_does_not_change_outcome(repo, data_dir, monkeypatch):
    monkeypatch.setenv("PROOFPATH_DEMO_MODE", "stage")
    monkeypatch.setenv("PROOFPATH_POC_STEP_DELAY_MS", "20")
    run = _queue(repo)
    final = runner.execute(repo, run.id)
    assert final.outcome == RunOutcome.passed
    _assert_clean(data_dir, run.id)


def test_run_dir_rejects_non_uuid(data_dir):
    for bad in ("../etc", "abc", "/tmp/x"):
        with pytest.raises(ValueError):
            runner._run_dir(bad)


# ------------------------------------------------------------------ end to end through the app
def test_end_to_end_via_app(data_dir, monkeypatch):
    import importlib
    monkeypatch.delenv("PROOFPATH_DISABLE_WORKER", raising=False)
    from fastapi.testclient import TestClient

    from sv.proofpath import app as app_module
    app_module = importlib.reload(app_module)

    with TestClient(app_module.app) as client:
        client.cookies.set("dl_session", "ws2-session")
        ev = app_module.repo.create_evaluation(Evaluation(session_id="ws2-session", brief_text="ws2 e2e"))
        brief = app_module.repo.append_brief(BriefVersion(
            evaluation_id=ev.id, version=1, goal="Test sync", systems=[], requirements=[]))
        app_module.repo.confirm_brief(brief.id)
        key = str(uuid.uuid4())
        body = {"brief_version_id": brief.id, "idempotency_key": key}
        r = client.post(f"/api/v1/evaluations/{ev.id}/runs", json=body)
        assert r.status_code == 202, r.text
        run_id = r.json()["data"]["id"]

        # duplicate POST returns the same run; a different payload with the same key conflicts
        assert client.post(f"/api/v1/evaluations/{ev.id}/runs", json=body).json()["data"]["id"] == run_id
        conflict = client.post(f"/api/v1/evaluations/{ev.id}/runs",
                               json={"brief_version_id": "other", "idempotency_key": key})
        assert conflict.status_code == 409

        deadline = time.monotonic() + 20
        data = None
        while time.monotonic() < deadline:
            data = client.get(f"/api/v1/runs/{run_id}").json()["data"]
            if data["run"]["state"] == "closed":
                break
            time.sleep(0.1)
        assert data["run"]["state"] == "closed", data["run"]
        assert data["run"]["outcome"] == "passed"
        assert sorted(r["test_key"] for r in data["results"]) == sorted(runner.TEST_KEYS)
        assert all(r["status"] == "pass" for r in data["results"])
        assert [a["name"] for a in data["artifacts"]] == ["delivery_log.json"]

        art = client.get(f"/api/v1/artifacts/{data['artifacts'][0]['id']}").json()["data"]
        assert art["content"]["destination_count"]["opp-002"] == 1

        events = client.get(f"/api/v1/evaluations/{ev.id}/events").json()["data"]
        types = [e["type"] for e in events if e.get("run_id") == run_id]
        assert types[0] == "poc_queued" and types[1] == "poc_started"
        assert types[-2:] == ["poc_finished", "poc_cleanup_finished"]
        assert types.count("poc_test_result") == 4 and "poc_attempt" in types
        seqs = [e["sequence"] for e in events]
        assert seqs == sorted(seqs)
    assert not (data_dir / "runs" / run_id).exists()
