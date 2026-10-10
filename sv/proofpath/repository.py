"""Persistence for the Evaluation Workspace: one SQLite implementation of the frozen interface.

`Repository(":memory:")` is the in-memory version for unit tests; `Repository(path)` is the
durable one. Records are stored as validated Pydantic JSON, so every read returns domain objects.
All multi-record writes go through `transaction()`. Thread-safe for one app plus one worker.

Interface (frozen; README "Shared repository interface to freeze"):
  evaluations   create_evaluation, get_evaluation, set_current_brief
  briefs        append_brief, get_brief, list_briefs, confirm_brief
  sources       put_source_version, get_source_version, list_source_versions, set_source_review
  claims        put_claim, list_claims
  comparisons   put_comparison, get_comparison, latest_comparison
  runs          create_run, get_run, find_run_by_key, update_run (expected_state), list_runs
  results       put_result, list_results
  artifacts     put_artifact, get_artifact, list_artifacts
  reports       create_report, get_report, list_reports
  agent         put_agent_result, latest_agent_result
  events        append_event, list_events(after=)
  meta          get_meta, set_meta (e.g. fixtures_seeded)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, TypeVar

from pydantic import BaseModel

from sv.proofpath.contracts import (AgentResult, Artifact, BriefVersion, Claim, ComparisonSnapshot,
                                    Evaluation, Event, POCRun, ReportVersion, RunState,
                                    SourceVersion, TestResult, now)

M = TypeVar("M", bound=BaseModel)

TABLES = {
    # table: (model, indexed columns besides id)
    "evaluations": (Evaluation, ["session_id"]),
    "briefs": (BriefVersion, ["evaluation_id"]),
    "sources": (SourceVersion, ["product_id", "source_id"]),
    "claims": (Claim, ["source_version_id"]),
    "comparisons": (ComparisonSnapshot, ["evaluation_id"]),
    "runs": (POCRun, ["evaluation_id", "idempotency_key"]),
    "results": (TestResult, ["run_id"]),
    "artifacts": (Artifact, ["run_id"]),
    "reports": (ReportVersion, ["evaluation_id"]),
    "agent_results": (AgentResult, ["evaluation_id"]),
}


class ConflictError(Exception):
    """Version or state conflict (the API maps this to HTTP 409)."""


class NotFoundError(Exception):
    """Missing resource (HTTP 404)."""


class Repository:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._depth = 0
        self._migrate()

    # ------------------------------------------------------------ plumbing
    def _migrate(self) -> None:
        with self._lock:
            for table, (_, cols) in TABLES.items():
                extra = "".join(f", {c} TEXT" for c in cols)
                self._db.execute(f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, seq INTEGER{extra}, body TEXT NOT NULL)")
                for c in cols:
                    self._db.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_{c} ON {table}({c})")
            self._db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, evaluation_id TEXT, body TEXT NOT NULL)")
            self._db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._db.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield
                self._depth -= 1
                if outer:
                    self._db.execute("COMMIT")
            except Exception:
                self._depth -= 1
                if outer:
                    self._db.execute("ROLLBACK")
                raise

    def _put(self, table: str, obj: BaseModel) -> None:
        _, cols = TABLES[table]
        values = [getattr(obj, c) for c in cols]
        with self._lock:
            seq = self._db.execute(f"SELECT COALESCE(MAX(seq), 0) + 1 FROM {table}").fetchone()[0]
            existing = self._db.execute(f"SELECT seq FROM {table} WHERE id=?", (obj.id,)).fetchone()
            if existing:
                seq = existing[0]
            self._db.execute(
                f"INSERT OR REPLACE INTO {table} (id, seq, {', '.join(cols)}, body) VALUES (?, ?, {', '.join('?' * len(cols))}, ?)",
                [obj.id, seq, *values, obj.model_dump_json()])

    def _get(self, table: str, id_: str) -> BaseModel:
        model, _ = TABLES[table]
        with self._lock:
            row = self._db.execute(f"SELECT body FROM {table} WHERE id=?", (id_,)).fetchone()
        if not row:
            raise NotFoundError(f"{table}/{id_}")
        return model.model_validate_json(row[0])

    def _list(self, table: str, where: str = "", args: tuple = ()) -> list:
        model, _ = TABLES[table]
        with self._lock:
            rows = self._db.execute(f"SELECT body FROM {table} {('WHERE ' + where) if where else ''} ORDER BY seq", args).fetchall()
        return [model.model_validate_json(r[0]) for r in rows]

    # ------------------------------------------------------------ evaluations
    def create_evaluation(self, ev: Evaluation) -> Evaluation:
        self._put("evaluations", ev)
        return ev

    def get_evaluation(self, evaluation_id: str) -> Evaluation:
        return self._get("evaluations", evaluation_id)

    def set_current_brief(self, evaluation_id: str, brief_version_id: str) -> Evaluation:
        with self.transaction():
            ev = self.get_evaluation(evaluation_id)
            ev.current_brief_version_id = brief_version_id
            self._put("evaluations", ev)
        return ev

    # ------------------------------------------------------------ briefs
    def append_brief(self, brief: BriefVersion, expected_version: Optional[int] = None) -> BriefVersion:
        with self.transaction():
            existing = self.list_briefs(brief.evaluation_id)
            latest = existing[-1].version if existing else 0
            if expected_version is not None and expected_version != latest:
                raise ConflictError(f"brief version is {latest}, expected {expected_version}")
            brief.version = latest + 1
            self._put("briefs", brief)
            self.set_current_brief(brief.evaluation_id, brief.id)
        return brief

    def get_brief(self, brief_version_id: str) -> BriefVersion:
        return self._get("briefs", brief_version_id)

    def list_briefs(self, evaluation_id: str) -> list[BriefVersion]:
        return self._list("briefs", "evaluation_id=?", (evaluation_id,))

    def confirm_brief(self, brief_version_id: str) -> BriefVersion:
        with self.transaction():
            brief = self.get_brief(brief_version_id)
            ev = self.get_evaluation(brief.evaluation_id)
            if ev.current_brief_version_id != brief_version_id:
                raise ConflictError("only the current brief version can be confirmed")
            if brief.confirmed_at is None:
                brief.confirmed_at = now()
                self._put("briefs", brief)
        return brief

    # ------------------------------------------------------------ sources and claims
    def put_source_version(self, sv: SourceVersion) -> SourceVersion:
        self._put("sources", sv)
        return sv

    def get_source_version(self, version_id: str) -> SourceVersion:
        return self._get("sources", version_id)

    def list_source_versions(self, product_id: Optional[str] = None) -> list[SourceVersion]:
        return self._list("sources", "product_id=?", (product_id,)) if product_id else self._list("sources")

    def set_source_review(self, version_id: str, sv: SourceVersion) -> SourceVersion:
        if sv.id != version_id:
            raise ConflictError("id mismatch")
        self._put("sources", sv)
        return sv

    def put_claim(self, claim: Claim) -> Claim:
        self._put("claims", claim)
        return claim

    def list_claims(self, source_version_id: Optional[str] = None) -> list[Claim]:
        if source_version_id:
            return self._list("claims", "source_version_id=?", (source_version_id,))
        return self._list("claims")

    # ------------------------------------------------------------ comparisons
    def put_comparison(self, snap: ComparisonSnapshot) -> ComparisonSnapshot:
        self._put("comparisons", snap)
        return snap

    def get_comparison(self, snapshot_id: str) -> ComparisonSnapshot:
        return self._get("comparisons", snapshot_id)

    def latest_comparison(self, evaluation_id: str) -> Optional[ComparisonSnapshot]:
        snaps = self._list("comparisons", "evaluation_id=?", (evaluation_id,))
        return snaps[-1] if snaps else None

    # ------------------------------------------------------------ runs
    def create_run(self, run: POCRun) -> POCRun:
        self._put("runs", run)
        return run

    def get_run(self, run_id: str) -> POCRun:
        return self._get("runs", run_id)

    def find_run_by_key(self, evaluation_id: str, idempotency_key: str) -> Optional[POCRun]:
        runs = self._list("runs", "evaluation_id=? AND idempotency_key=?", (evaluation_id, idempotency_key))
        return runs[0] if runs else None

    def update_run(self, run: POCRun, expected_state: Optional[RunState] = None) -> POCRun:
        with self.transaction():
            current = self.get_run(run.id)
            if expected_state is not None and current.state != expected_state:
                raise ConflictError(f"run is {current.state.value}, expected {expected_state.value}")
            self._put("runs", run)
        return run

    def list_runs(self, evaluation_id: Optional[str] = None, state: Optional[RunState] = None) -> list[POCRun]:
        runs = self._list("runs", "evaluation_id=?", (evaluation_id,)) if evaluation_id else self._list("runs")
        return [r for r in runs if state is None or r.state == state]

    # ------------------------------------------------------------ results and artifacts
    def put_result(self, result: TestResult) -> TestResult:
        self._put("results", result)
        return result

    def list_results(self, run_id: str) -> list[TestResult]:
        return self._list("results", "run_id=?", (run_id,))

    def put_artifact(self, artifact: Artifact) -> Artifact:
        self._put("artifacts", artifact)
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact:
        return self._get("artifacts", artifact_id)

    def list_artifacts(self, run_id: str) -> list[Artifact]:
        return self._list("artifacts", "run_id=?", (run_id,))

    # ------------------------------------------------------------ reports and agent results
    def create_report(self, report: ReportVersion) -> ReportVersion:
        with self._lock:
            if self._db.execute("SELECT 1 FROM reports WHERE id=?", (report.id,)).fetchone():
                raise ConflictError("reports are immutable")
        self._put("reports", report)
        return report

    def get_report(self, report_id: str) -> ReportVersion:
        return self._get("reports", report_id)

    def list_reports(self, evaluation_id: str) -> list[ReportVersion]:
        return self._list("reports", "evaluation_id=?", (evaluation_id,))

    def put_agent_result(self, result: AgentResult) -> AgentResult:
        self._put("agent_results", result)
        return result

    def latest_agent_result(self, evaluation_id: str) -> Optional[AgentResult]:
        rs = self._list("agent_results", "evaluation_id=?", (evaluation_id,))
        return rs[-1] if rs else None

    # ------------------------------------------------------------ events
    def append_event(self, event: Event) -> Event:
        with self._lock:
            cur = self._db.execute("INSERT INTO events (evaluation_id, body) VALUES (?, ?)",
                                   (event.evaluation_id, "{}"))
            event.sequence = cur.lastrowid
            self._db.execute("UPDATE events SET body=? WHERE sequence=?", (event.model_dump_json(), event.sequence))
        return event

    def list_events(self, evaluation_id: str, after: int = 0) -> list[Event]:
        with self._lock:
            rows = self._db.execute("SELECT body FROM events WHERE evaluation_id=? AND sequence>? ORDER BY sequence",
                                    (evaluation_id, after)).fetchall()
        return [Event.model_validate_json(r[0]) for r in rows]

    # ------------------------------------------------------------ meta
    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def dumps(obj: BaseModel) -> dict:
    return json.loads(obj.model_dump_json())
