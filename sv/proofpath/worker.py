"""One bounded in-process worker that executes queued POC runs (README: hackathon runtime).

On startup the POC runner's recover_interrupted() marks runs left `running` as failed/interrupted and
cleans them up; nothing pretends to resume. Production replaces this with a durable external queue.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from sv.proofpath.contracts import RunState
from sv.proofpath.repository import Repository

log = logging.getLogger("decision_layer.worker")


class Worker:
    def __init__(self, repo: Repository, poll_seconds: float = 0.3):
        self.repo = repo
        self.poll = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if os.environ.get("PROOFPATH_DISABLE_WORKER"):
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        try:
            from sv.proofpath.poc import runner
            runner.recover_interrupted(self.repo)
        except ImportError:
            log.warning("POC runner not available yet; worker idle")
        self._thread = threading.Thread(target=self._loop, name="poc-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=35)

    def _after_run(self, run_id: str) -> None:
        """Telemetry for completed runs (WS5); failures here never affect the run."""
        try:
            from sv.proofpath.contracts import RunOutcome
            run = self.repo.get_run(run_id)
            if run.outcome == RunOutcome.passed:
                from sv.proofpath import telemetry
                telemetry.record(self.repo, run.evaluation_id, "poc_completed", "live")
                if telemetry.qualified_evaluation_completed(self.repo, run.evaluation_id):
                    telemetry.record(self.repo, run.evaluation_id, "qualified_evaluation_completed", "live")
        except Exception:
            log.debug("telemetry after run failed", exc_info=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                queued = self.repo.list_runs(state=RunState.queued)
                if queued:
                    from sv.proofpath.poc import runner
                    runner.execute(self.repo, queued[0].id)
                    self._after_run(queued[0].id)
                    continue
            except ImportError:
                pass
            except Exception:                          # a crashed run must not kill the worker
                log.exception("POC execution crashed")
            self._stop.wait(self.poll)
