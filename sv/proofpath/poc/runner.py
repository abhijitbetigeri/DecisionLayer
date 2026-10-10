"""POC runner for scenario `crm_warehouse_sync/v1` (the "Prove it" button).

Lifecycle: queued -> provisioning -> running -> completed|failed|cancelled -> cleaning_up -> closed.
The outcome (`POCRun.outcome`) is kept separate from the cleanup state, so a closed run still says
whether it passed, failed, timed out, was cancelled or was interrupted.

Entry points (frozen): execute(repo, run_id), cancel(repo, run_id), recover_interrupted(repo).

Guarantees:
- 30-second deadline, at most 3 delivery attempts per record, bounded artifact size.
- The scenario runs in a helper thread; the runner thread enforces the deadline and cancellation
  even if the adapter blocks, then fences off any late writes from the helper.
- Cleanup (close and delete the run-specific destination and its run directory) on success,
  failure, timeout, cancellation and startup recovery. Artifacts and results stay in the
  repository and contain no filesystem paths.
- No network, no shell, no model calls. Paths come only from PROOFPATH_DATA_DIR and the run's UUID.
- PROOFPATH_DEMO_MODE=stage + PROOFPATH_POC_STEP_DELAY_MS adds a presentation pause between steps
  (capped, interruptible); it never changes an outcome.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from sv.proofpath.contracts import (SCENARIO_VERSION, Artifact, Event, EventType, POCRun, RunOutcome,
                                    RunState, TestResult, TestStatus, now)
from sv.proofpath.poc.adapter import (DESTINATION_LABEL, FIELDS, SOURCE_LABEL, MockCRM, SyncAdapter,
                                      TransientDeliveryError, WarehouseDestination)
from sv.proofpath.repository import ConflictError, NotFoundError

log = logging.getLogger("decision_layer.poc")

DEADLINE_SECONDS = 30.0
MAX_ATTEMPTS = 3
MAX_ARTIFACT_BYTES = 16_000
MAX_STEP_DELAY_MS = 1500
POLL_SECONDS = 0.05
TEST_KEYS = ("insert_first", "transient_failure", "bounded_retry", "single_record")
SANDBOX_LABEL = "Demo sandbox: mock CRM and warehouse stand-ins, no real Salesforce or Snowflake."
LIMITATIONS = ("Local mock integrations only; demonstrates the tested transient-failure mode, "
               "not durability against every crash scenario or production connector correctness.")
ACTIVE_STATES = (RunState.provisioning, RunState.running)
OUTCOME_STATES = (RunState.completed, RunState.failed, RunState.cancelled)

_cancel_flags: dict[str, threading.Event] = {}
_flags_lock = threading.Lock()


# ------------------------------------------------------------------ paths and config
def _runs_root() -> Path:
    return Path(os.environ.get("PROOFPATH_DATA_DIR", ".proofpath-data")) / "runs"


def _run_dir(run_id: str) -> Path:
    """Run directory derived only from a validated UUID run id, never from user input."""
    canonical = str(uuid.UUID(run_id))
    if canonical != run_id:
        raise ValueError("run id is not a canonical UUID")
    root = _runs_root().resolve()
    path = (root / canonical).resolve()
    if path.parent != root:
        raise ValueError("run directory escapes the runs root")
    return path


def _step_delay_seconds() -> float:
    if os.environ.get("PROOFPATH_DEMO_MODE", "local") != "stage":
        return 0.0
    try:
        ms = int(os.environ.get("PROOFPATH_POC_STEP_DELAY_MS", "0"))
    except ValueError:
        return 0.0
    return max(0, min(ms, MAX_STEP_DELAY_MS)) / 1000.0


def _flag(run_id: str) -> threading.Event:
    with _flags_lock:
        return _cancel_flags.setdefault(run_id, threading.Event())


def _cancel_requested(repo, run_id: str) -> bool:
    if _flag(run_id).is_set():
        return True
    return repo.get_meta(f"poc_cancel:{run_id}") == "1"


def _bounded(content: Any) -> Any:
    text = json.dumps(content, default=str)
    if len(text.encode()) <= MAX_ARTIFACT_BYTES:
        return content
    return {"truncated": True, "max_bytes": MAX_ARTIFACT_BYTES, "preview": text[: MAX_ARTIFACT_BYTES // 2]}


def _emit(repo, run: POCRun, type_: EventType, **payload) -> None:
    repo.append_event(Event(evaluation_id=run.evaluation_id, run_id=run.id, type=type_, payload=payload))


def _set_state(repo, run_id: str, state: RunState, expected: Optional[RunState] = None, **fields) -> POCRun:
    run = repo.get_run(run_id)
    if expected is not None and run.state != expected:
        raise ConflictError(f"run is {run.state.value}, expected {expected.value}")
    run.state = state
    for k, v in fields.items():
        setattr(run, k, v)
    return repo.update_run(run, expected_state=expected)


# ------------------------------------------------------------------ scenario
class _Stop(Exception):
    """Raised inside the scenario thread when the runner has fenced it off."""


class _Context:
    """Shared between the runner thread and the scenario thread. All repository writes from the
    scenario go through `write()`, which refuses once the runner has fenced the run."""

    def __init__(self, repo, run: POCRun, delay: float):
        self.repo = repo
        self.run = run
        self.delay = delay
        self.lock = threading.Lock()
        self.fenced = False
        self.stop = threading.Event()
        self.done = threading.Event()
        self.error: Optional[BaseException] = None
        self.results: dict[str, TestResult] = {}
        self.log: list[dict] = []
        self.request_ids: list[str] = []
        self.attempts_by_record: dict[str, int] = {}
        self.total_attempts = 0
        self.final_counts: dict[str, int] = {}
        self.artifact_id: Optional[str] = None

    def check(self) -> None:
        if self.stop.is_set():
            raise _Stop()

    def pause(self) -> None:
        if self.delay:
            self.stop.wait(self.delay)
        self.check()

    def write(self, fn: Callable[[], Any]) -> Any:
        with self.lock:
            if self.fenced:
                raise _Stop()
            return fn()

    def emit(self, type_: EventType, **payload) -> None:
        self.write(lambda: _emit(self.repo, self.run, type_, **payload))

    def record(self, test_key: str, ok: bool, expected: Any, observed: Any) -> None:
        result = TestResult(run_id=self.run.id, test_key=test_key,
                            status=TestStatus.pass_ if ok else TestStatus.fail,
                            expected=expected, observed=observed,
                            artifact_ids=[self.artifact_id] if self.artifact_id else [],
                            limitations=LIMITATIONS)

        def _do():
            self.repo.put_result(result)
            self.results[test_key] = result
            _emit(self.repo, self.run, EventType.poc_test_result, test_key=test_key,
                  status=result.status.value, result_id=result.id)
        self.write(_do)
        self.pause()


def _key(record_id: str) -> str:
    return f"{SCENARIO_VERSION}:{record_id}"


def _attempt(ctx: _Context, adapter: SyncAdapter, record: dict, attempt: int, kind: str = "delivery") -> Optional[str]:
    """One delivery attempt. Returns an error string for a transient failure, None on success."""
    ctx.check()
    key = _key(record["id"])
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    error = None
    try:
        adapter.deliver(record, key, request_id)
    except TransientDeliveryError as exc:
        error = str(exc)
    ctx.check()
    entry = {"record": record["id"], "idempotency_key": key, "request_id": request_id,
             "attempt": attempt, "kind": kind, "ok": error is None}
    if error:
        entry["error"] = error
        entry["will_retry"] = attempt < MAX_ATTEMPTS
    ctx.log.append(entry)
    ctx.request_ids.append(request_id)
    if kind == "delivery":
        ctx.total_attempts += 1
        ctx.attempts_by_record[record["id"]] = attempt
    ctx.emit(EventType.poc_attempt, **entry)
    ctx.pause()
    return error


def _deliver_with_retry(ctx: _Context, adapter: SyncAdapter, record: dict) -> tuple[bool, list[Optional[str]]]:
    errors: list[Optional[str]] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        err = _attempt(ctx, adapter, record, attempt)
        errors.append(err)
        if err is None:
            return True, errors
    return False, errors


def _scenario(ctx: _Context, adapter: SyncAdapter, dest: WarehouseDestination, crm: MockCRM) -> None:
    first, second = crm.opportunities()[:2]

    # 1. insert_first
    ok1, _ = _deliver_with_retry(ctx, adapter, first)
    row = dest.get(_key(first["id"]))
    observed = {f: row[f] for f in FIELDS} if row else None
    ctx.record("insert_first", ok1 and observed == first, expected=first, observed=observed)

    # 2. transient_failure (first attempt of the second record fails before commit)
    key2 = _key(second["id"])
    err = _attempt(ctx, adapter, second, attempt=1)
    committed_after_failure = dest.count(key2)
    retry_event = err is not None and ctx.log[-1].get("will_retry") is True
    ctx.record("transient_failure", err is not None and committed_after_failure == 0 and retry_event,
               expected={"attempt_1": "transient error before commit", "rows_committed": 0,
                         "poc_attempt_retry_event": True},
               observed={"attempt_1": err or "succeeded (no failure injected)",
                         "rows_committed": committed_after_failure, "poc_attempt_retry_event": retry_event})

    # 3. bounded_retry with the same idempotency key
    ok3 = err is None
    attempt = 1
    while not ok3 and attempt < MAX_ATTEMPTS:
        attempt += 1
        ok3 = _attempt(ctx, adapter, second, attempt=attempt) is None
    keys_used = {e["idempotency_key"] for e in ctx.log if e["record"] == second["id"]}
    ctx.record("bounded_retry", ok3 and attempt <= MAX_ATTEMPTS and keys_used == {key2} and dest.count(key2) == 1,
               expected={"succeeded": True, "max_attempts": MAX_ATTEMPTS, "same_idempotency_key": True},
               observed={"succeeded": ok3, "attempts": attempt, "same_idempotency_key": keys_used == {key2},
                         "idempotency_key": key2})

    # 4. single_record after a repeated delivery of the same record and key
    _attempt(ctx, adapter, second, attempt=1, kind="redelivery")
    count2 = dest.count(key2)
    ctx.final_counts = {first["id"]: dest.count(_key(first["id"])), second["id"]: count2}
    ctx.record("single_record", count2 == 1, expected={"destination_rows_for_key": 1},
               observed={"destination_rows_for_key": count2, "idempotency_key": key2,
                         "deliveries_of_key": sum(1 for e in ctx.log if e["record"] == second["id"] and e["ok"])})


def _scenario_thread(ctx: _Context, adapter: SyncAdapter, dest: WarehouseDestination, crm: MockCRM) -> None:
    try:
        _scenario(ctx, adapter, dest, crm)
    except _Stop:
        pass
    except BaseException as exc:                    # surfaced to the runner as a failure
        if not ctx.stop.is_set():
            ctx.error = exc
    finally:
        ctx.done.set()


# ------------------------------------------------------------------ cleanup
def _cleanup_files(run_id: str) -> list[str]:
    """Remove the run directory. Returns removed relative names (never absolute paths)."""
    try:
        path = _run_dir(run_id)
    except ValueError:
        return []
    if not path.exists():
        return []
    removed = sorted(p.name for p in path.iterdir())
    shutil.rmtree(path, ignore_errors=True)
    return removed


def _close_out(repo, run_id: str, cleanup: Callable[[], list[str]]) -> POCRun:
    """outcome state -> cleaning_up -> closed, with poc_cleanup_finished."""
    run = repo.get_run(run_id)
    if run.state in OUTCOME_STATES:
        run = _set_state(repo, run_id, RunState.cleaning_up, expected=run.state)
    removed: list[str] = []
    cleanup_error = None
    try:
        removed = cleanup()
    except Exception as exc:                        # cleanup must never leave the run open
        cleanup_error = type(exc).__name__
    leftover = _run_dir_exists(run_id)
    run = _set_state(repo, run_id, RunState.closed)
    _emit(repo, run, EventType.poc_cleanup_finished, removed=removed, leftover_temp_files=leftover,
          outcome=run.outcome.value if run.outcome else None,
          **({"error": cleanup_error} if cleanup_error else {}))
    with _flags_lock:
        _cancel_flags.pop(run_id, None)
    try:
        repo.set_meta(f"poc_cancel:{run_id}", "")
    except Exception:
        pass
    return run


def _run_dir_exists(run_id: str) -> bool:
    try:
        return _run_dir(run_id).exists()
    except ValueError:
        return False


# ------------------------------------------------------------------ entry points
def execute(repo, run_id: str, *, deadline_s: Optional[float] = None,
            adapter_factory: Optional[Callable[[WarehouseDestination], SyncAdapter]] = None) -> POCRun:
    """Run one queued POC to `closed`. Keyword arguments exist for tests (slow adapter, short deadline)."""
    deadline_s = DEADLINE_SECONDS if deadline_s is None else deadline_s
    run = repo.get_run(run_id)
    if run.state != RunState.queued:
        return run
    if run.scenario_version != SCENARIO_VERSION:
        run = _set_state(repo, run_id, RunState.failed, expected=RunState.queued,
                         outcome=RunOutcome.failed, error=f"unsupported scenario {run.scenario_version}")
        _emit(repo, run, EventType.poc_finished, state=run.state.value, outcome=run.outcome.value, error=run.error)
        return _close_out(repo, run_id, lambda: [])
    started = time.monotonic()
    try:
        run = _set_state(repo, run_id, RunState.provisioning, expected=RunState.queued,
                         expires_at=now() + timedelta(seconds=deadline_s), error=None)
    except ConflictError:                           # cancelled or picked up elsewhere
        return repo.get_run(run_id)

    _emit(repo, run, EventType.poc_started, scenario_version=SCENARIO_VERSION, source=SOURCE_LABEL,
          destination=DESTINATION_LABEL, sandbox_label=SANDBOX_LABEL, deadline_seconds=deadline_s,
          max_attempts=MAX_ATTEMPTS)

    dest: Optional[WarehouseDestination] = None
    ctx = _Context(repo, run, _step_delay_seconds())
    outcome, state, error = RunOutcome.failed, RunState.failed, None
    try:
        path = _run_dir(run_id)
        path.mkdir(parents=True, exist_ok=True)
        dest = WarehouseDestination(path / "destination.sqlite")
        adapter = (adapter_factory or SyncAdapter)(dest)
        crm = MockCRM()
        # Pre-create the artifact id so results can reference it; content is written at the end.
        ctx.artifact_id = str(uuid.uuid4())
        run = _set_state(repo, run_id, RunState.running, expected=RunState.provisioning)
        ctx.run = run

        worker = threading.Thread(target=_scenario_thread, args=(ctx, adapter, dest, crm),
                                  name=f"poc-scenario-{run_id[:8]}", daemon=True)
        worker.start()
        reason = None
        while not ctx.done.wait(POLL_SECONDS):
            if _cancel_requested(repo, run_id):
                reason = "cancelled"
                break
            if time.monotonic() - started > deadline_s:
                reason = "timeout"
                break
        if reason is None and ctx.done.is_set() and _cancel_requested(repo, run_id) and len(ctx.results) < 4:
            reason = "cancelled"
        with ctx.lock:                              # fence: no late writes from the scenario thread
            ctx.fenced = True
            ctx.stop.set()

        if reason == "cancelled":
            outcome, state, error = RunOutcome.cancelled, RunState.cancelled, "cancelled by user"
        elif reason == "timeout":
            outcome, state, error = RunOutcome.timed_out, RunState.failed, f"deadline exceeded ({deadline_s:g}s)"
        elif ctx.error is not None:
            outcome, state, error = RunOutcome.failed, RunState.failed, f"execution error: {type(ctx.error).__name__}"
        elif len(ctx.results) == 4 and all(r.status == TestStatus.pass_ for r in ctx.results.values()):
            outcome, state = RunOutcome.passed, RunState.completed
        else:
            failed = [k for k in TEST_KEYS if k in ctx.results and ctx.results[k].status != TestStatus.pass_]
            outcome, state, error = RunOutcome.failed, RunState.failed, f"assertions failed: {', '.join(failed) or 'incomplete'}"
    except Exception as exc:
        log.exception("POC run %s crashed", run_id)
        with ctx.lock:
            ctx.fenced = True
            ctx.stop.set()
        outcome, state, error = RunOutcome.failed, RunState.failed, f"execution error: {type(exc).__name__}"

    # Results for assertions never reached are recorded as blocked, not silently missing.
    for key in TEST_KEYS:
        if key not in ctx.results:
            repo.put_result(TestResult(run_id=run_id, test_key=key, status=TestStatus.blocked,
                                       expected="assertion executed", observed=f"not reached: {error or outcome.value}",
                                       limitations=LIMITATIONS))

    if ctx.final_counts == {} and dest is not None:
        try:
            ctx.final_counts = {r["id"]: dest.count(_key(r["id"])) for r in MockCRM().opportunities()}
        except Exception:
            pass
    content = _bounded({
        "scenario_version": SCENARIO_VERSION,
        "sandbox_label": SANDBOX_LABEL,
        "source": SOURCE_LABEL,
        "destination": DESTINATION_LABEL,
        "outcome": outcome.value,
        "error": error,
        "max_attempts": MAX_ATTEMPTS,
        "deadline_seconds": deadline_s,
        "attempts": ctx.log,
        "request_ids": ctx.request_ids,
        "attempts_by_record": ctx.attempts_by_record,
        "destination_count": ctx.final_counts,
        "assertions": [{"test_key": r.test_key, "status": r.status.value, "expected": r.expected,
                        "observed": r.observed} for r in (ctx.results.get(k) for k in TEST_KEYS) if r],
        "limitations": LIMITATIONS,
    })
    repo.put_artifact(Artifact(id=ctx.artifact_id or str(uuid.uuid4()), run_id=run_id,
                               name="delivery_log.json", content=content))

    run = repo.get_run(run_id)
    run.state, run.outcome, run.error, run.attempts = state, outcome, error, ctx.total_attempts
    run = repo.update_run(run)
    _emit(repo, run, EventType.poc_finished, state=state.value, outcome=outcome.value, error=error,
          attempts=ctx.total_attempts, attempts_by_record=ctx.attempts_by_record,
          destination_count=ctx.final_counts, elapsed_ms=int((time.monotonic() - started) * 1000))

    def _cleanup() -> list[str]:
        if dest is not None:
            dest.close()
        return _cleanup_files(run_id)
    return _close_out(repo, run_id, _cleanup)


def cancel(repo, run_id: str) -> POCRun:
    """Idempotent. A queued run closes immediately; an executing run is stopped by its runner."""
    run = repo.get_run(run_id)
    if run.state in (RunState.closed, RunState.cleaning_up) or run.state in OUTCOME_STATES:
        return run
    _flag(run_id).set()
    repo.set_meta(f"poc_cancel:{run_id}", "1")
    if run.state == RunState.queued:
        try:
            run = _set_state(repo, run_id, RunState.cancelled, expected=RunState.queued,
                             outcome=RunOutcome.cancelled, error="cancelled before start")
        except ConflictError:
            pass                                    # the worker just picked it up; flag stops it
        else:
            _emit(repo, run, EventType.poc_finished, state=run.state.value, outcome=run.outcome.value, error=run.error)
            return _close_out(repo, run_id, lambda: _cleanup_files(run_id))
    # Give the runner a moment to acknowledge so the response is informative; the UI polls anyway.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        run = repo.get_run(run_id)
        if run.state not in (RunState.queued, *ACTIVE_STATES):
            break
        time.sleep(POLL_SECONDS)
    return repo.get_run(run_id)


def recover_interrupted(repo) -> list[str]:
    """Startup: runs left provisioning/running become failed/interrupted; anything left mid-cleanup
    is closed. Temporary destinations are removed. Nothing pretends to resume."""
    recovered: list[str] = []
    for run in repo.list_runs():
        try:
            if run.state in ACTIVE_STATES:
                run = _set_state(repo, run.id, RunState.failed, outcome=RunOutcome.interrupted,
                                 error="interrupted by restart; not resumed")
                _emit(repo, run, EventType.poc_finished, state=run.state.value, outcome=run.outcome.value,
                      error=run.error)
            elif run.state not in OUTCOME_STATES and run.state != RunState.cleaning_up:
                continue
            if run.outcome is None:
                run.outcome = RunOutcome.interrupted
                repo.update_run(run)
            _close_out(repo, run.id, lambda rid=run.id: _cleanup_files(rid))
            recovered.append(run.id)
        except (ConflictError, NotFoundError):
            log.warning("could not recover run %s", run.id)
    return recovered
