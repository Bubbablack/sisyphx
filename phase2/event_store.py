#!/usr/bin/env python3
"""CHUNK-022 — Append-only SQLite event store.

Every state change in the loop is recorded as an immutable event. There is no
public update or delete API, and the database has triggers that reject direct
UPDATE/DELETE attempts.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    run_id TEXT NOT NULL,
    iteration INTEGER,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_run_iter ON events(run_id, iteration);

CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ROLLBACK, 'events table is append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ROLLBACK, 'events table is append-only');
END;
"""


@dataclass(frozen=True)
class StoredEvent:
    id: int
    event_type: str
    run_id: str
    iteration: int | None
    timestamp: str
    payload: dict[str, Any]


class EventStore:
    """Append-only event store backed by SQLite.

    The store exposes only ``append`` and read methods. The table has triggers
    that raise if any row is updated or deleted, so even direct SQL cannot
    mutate history.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def new_run_id(self) -> str:
        """Generate a fresh run identifier."""
        return str(uuid.uuid4())

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def append(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        run_id: str,
        iteration: int | None = None,
        timestamp: str | None = None,
    ) -> int:
        """Append an event. Returns the generated row id."""
        if payload is None:
            payload = {}
        row = (
            event_type,
            run_id,
            iteration,
            timestamp or self._now(),
            json.dumps(payload, sort_keys=True),
        )
        cur = self._conn.execute(
            "INSERT INTO events (event_type, run_id, iteration, timestamp, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            row,
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def append_verify_result(
        self,
        *,
        run_id: str,
        iteration: int | None,
        verify_exit_code: int,
        verify_output: str,
        passed: bool,
        failure_kind: str,
        failure_signature: str,
        verify_tier2_ran: bool = False,
        verify_tier2_exit_code: int | None = None,
        verify_tier2_output: str = "",
        timestamp: str | None = None,
    ) -> int:
        """CHUNK-030: append a 'verify_result' event, including the
        CHUNK-029 second-verification-tier fields.

        The `events` table schema itself needs no change for this --
        `payload` was already an opaque JSON blob (see module docstring),
        so any event can carry any fields. This method exists only to
        define the tier-2 field names in exactly one place, so `loop.py`'s
        CHUNK-031 integration (and anything reading these events back) does
        not have to remember or guess them. Callers that never configure a
        second tier get `verify_tier2_ran=False` and empty/`None` for the
        rest -- a harmless, additive default, not the absence of the keys.
        This method is additive, not a replacement API: existing
        `append("verify_result", {...})` calls from Phase 1/2 keep working
        exactly as before (see `test_append_verify_result_without_tier2_is_backward_compatible`).
        """
        payload: dict[str, Any] = {
            "verify_exit_code": verify_exit_code,
            "verify_output": verify_output,
            "passed": passed,
            "failure_kind": failure_kind,
            "failure_signature": failure_signature,
            "verify_tier2_ran": verify_tier2_ran,
            "verify_tier2_exit_code": verify_tier2_exit_code,
            "verify_tier2_output": verify_tier2_output,
        }
        return self.append(
            "verify_result", payload, run_id=run_id, iteration=iteration, timestamp=timestamp
        )

    def get_events(
        self,
        event_type: str | None = None,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[StoredEvent]:
        """Read events, optionally filtered. Results are ordered by id."""
        query = (
            "SELECT id, event_type, run_id, iteration, timestamp, payload "
            "FROM events WHERE 1=1"
        )
        params: list[Any] = []
        if event_type is not None:
            query += " AND event_type = ?"
            params.append(event_type)
        if run_id is not None:
            query += " AND run_id = ?"
            params.append(run_id)
        if iteration is not None:
            query += " AND iteration = ?"
            params.append(iteration)
        query += " ORDER BY id"
        cur = self._conn.execute(query, params)
        rows = cur.fetchall()
        return [
            StoredEvent(
                id=row[0],
                event_type=row[1],
                run_id=row[2],
                iteration=row[3],
                timestamp=row[4],
                payload=json.loads(row[5]),
            )
            for row in rows
        ]

    def get_event_types(self, run_id: str | None = None) -> list[str]:
        """Return all distinct event types, optionally filtered to a run."""
        query = "SELECT DISTINCT event_type FROM events"
        params: list[Any] = []
        if run_id is not None:
            query += " WHERE run_id = ?"
            params.append(run_id)
        query += " ORDER BY event_type"
        return [row[0] for row in self._conn.execute(query, params).fetchall()]

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
