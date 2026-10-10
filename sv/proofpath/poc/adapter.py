"""Local mock integrations for scenario `crm_warehouse_sync/v1`.

- `MockCRM`: a Python source of synthetic opportunities ("Salesforce stand-in"). No network.
- `WarehouseDestination`: a run-specific SQLite file ("Snowflake stand-in") with an upsert keyed by
  idempotency key.
- `SyncAdapter`: delivers CRM records to the destination. It raises a controlled
  `TransientDeliveryError` on the first delivery attempt of a configured record, *inside* the
  destination transaction and before commit, so the failure is real behaviour that is rolled back.

These are demo-sandbox mocks. Nothing here says anything about a production connector.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

SOURCE_LABEL = "Salesforce stand-in (mock CRM, local Python source)"
DESTINATION_LABEL = "Snowflake stand-in (run-specific local SQLite table)"

# Synthetic, fictional records.
OPPORTUNITIES: tuple[dict, ...] = (
    {"id": "opp-001", "account": "Northwind Analytics (fictional)", "amount": 48200,
     "stage": "Closed Won", "close_date": "2026-09-30", "currency": "USD"},
    {"id": "opp-002", "account": "Contoso Freight (fictional)", "amount": 12750,
     "stage": "Negotiation", "close_date": "2026-11-15", "currency": "USD"},
)

FIELDS = ("id", "account", "amount", "stage", "close_date", "currency")


class TransientDeliveryError(Exception):
    """Controlled, retryable failure injected by the adapter (not a UI animation)."""


class MockCRM:
    label = SOURCE_LABEL

    def opportunities(self) -> list[dict]:
        return [dict(r) for r in OPPORTUNITIES]


class WarehouseDestination:
    """Run-specific SQLite destination. `path` is chosen by the runner, never by user input."""

    label = DESTINATION_LABEL

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._db: Optional[sqlite3.Connection] = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS opportunities ("
            " idempotency_key TEXT PRIMARY KEY, id TEXT NOT NULL, account TEXT, amount INTEGER,"
            " stage TEXT, close_date TEXT, currency TEXT, request_id TEXT NOT NULL,"
            " delivery_count INTEGER NOT NULL DEFAULT 1)")

    def _conn(self) -> sqlite3.Connection:
        if self._db is None:
            raise RuntimeError("destination closed")
        return self._db

    def upsert(self, idempotency_key: str, record: dict, request_id: str, fail_before_commit: bool = False) -> None:
        """Insert or update one record keyed by idempotency key, atomically.

        With `fail_before_commit`, the row is written inside the transaction and then the controlled
        transient error is raised, so the transaction rolls back and nothing is committed.
        """
        with self._lock:
            db = self._conn()
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "INSERT INTO opportunities (idempotency_key, id, account, amount, stage, close_date,"
                    " currency, request_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(idempotency_key) DO UPDATE SET account=excluded.account,"
                    " amount=excluded.amount, stage=excluded.stage, close_date=excluded.close_date,"
                    " currency=excluded.currency, request_id=excluded.request_id,"
                    " delivery_count=opportunities.delivery_count + 1",
                    (idempotency_key, record["id"], record["account"], record["amount"], record["stage"],
                     record["close_date"], record["currency"], request_id))
                if fail_before_commit:
                    raise TransientDeliveryError("transient: warehouse write timeout (injected before commit)")
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def count(self, idempotency_key: Optional[str] = None) -> int:
        with self._lock:
            db = self._conn()
            if idempotency_key is None:
                return db.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
            return db.execute("SELECT COUNT(*) FROM opportunities WHERE idempotency_key=?",
                              (idempotency_key,)).fetchone()[0]

    def get(self, idempotency_key: str) -> Optional[dict]:
        with self._lock:
            row = self._conn().execute(
                f"SELECT {', '.join(FIELDS)}, request_id, delivery_count FROM opportunities"
                " WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if not row:
            return None
        return dict(zip((*FIELDS, "request_id", "delivery_count"), row))

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                finally:
                    self._db = None


class SyncAdapter:
    """Delivers records with a caller-supplied idempotency key.

    `fail_first_attempt_for`: record ids whose *first* delivery attempt raises the controlled
    transient error before commit.
    """

    def __init__(self, destination: WarehouseDestination, fail_first_attempt_for: tuple[str, ...] = ("opp-002",)):
        self.destination = destination
        self.fail_first_attempt_for = set(fail_first_attempt_for)
        self.attempts: dict[str, int] = {}

    def deliver(self, record: dict, idempotency_key: str, request_id: str) -> None:
        n = self.attempts.get(idempotency_key, 0) + 1
        self.attempts[idempotency_key] = n
        inject = n == 1 and record["id"] in self.fail_first_attempt_for
        self.destination.upsert(idempotency_key, record, request_id, fail_before_commit=inject)
