"""Frozen event schema shared by the simulator, guard and dashboard.

Every component appends events to one JSONL file per experiment, and the dashboard only
reads events. Replaying a recorded file and watching a live run therefore look identical,
which is also the fallback demo if the network fails on stage.

Event types (change only by adding fields, never by renaming):
  run_started   {run_id, variant, brief_id, model, seed}
  step          {run_id, n, tool, arg, note}
  run_finished  {run_id, answer, truth, correct, shortlisted, steps, error}
  struggle      {run_id, category, detail}
  guard_claim   {variant, surface, claim, verdict, fact, reason}
  guard_verdict {variant, passed, blocked_claims, review_claims}
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"
_lock = threading.Lock()


class EventLog:
    def __init__(self, experiment: str):
        RUNS.mkdir(exist_ok=True)
        self.path = RUNS / f"{experiment}.jsonl"

    def emit(self, type_: str, **fields) -> None:
        line = json.dumps({"ts": time.time(), "type": type_, **fields}, default=str)
        with _lock, self.path.open("a") as f:
            f.write(line + "\n")


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
