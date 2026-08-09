#!/usr/bin/env python3
"""CHUNK-022 tests for the append-only SQLite EventStore."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from phase2.event_store import EventStore, StoredEvent


def test_append_and_round_trip(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    run_id = store.new_run_id()

    store.append(
        "iteration_started",
        {"head_before": "abc123"},
        run_id=run_id,
        iteration=1,
    )
    store.append(
        "verify_result",
        {"passed": True, "failure_kind": "verify-pass"},
        run_id=run_id,
        iteration=1,
    )

    events = store.get_events()
    assert len(events) == 2
    assert events[0].event_type == "iteration_started"
    assert events[0].payload == {"head_before": "abc123"}
    assert events[0].run_id == run_id
    assert events[0].iteration == 1
    assert events[1].payload == {"passed": True, "failure_kind": "verify-pass"}

    store.close()


def test_get_events_filter_by_run_and_type(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    run_a = store.new_run_id()
    run_b = store.new_run_id()

    store.append("iteration_started", {}, run_id=run_a, iteration=1)
    store.append("verify_result", {}, run_id=run_b, iteration=1)
    store.append("stop", {"reason": "pass"}, run_id=run_a, iteration=1)

    assert len(store.get_events(run_id=run_a)) == 2
    assert len(store.get_events(run_id=run_b)) == 1
    assert len(store.get_events(event_type="stop")) == 1
    assert len(store.get_events(event_type="verify_result", run_id=run_b)) == 1
    assert len(store.get_events(event_type="iteration_started", run_id=run_b)) == 0
    assert len(store.get_events(iteration=1)) == 3

    store.close()


def test_events_are_sorted_by_id(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    run_id = store.new_run_id()

    for i in range(5):
        store.append("event", {"n": i}, run_id=run_id, iteration=1)

    events = store.get_events(run_id=run_id)
    assert [e.payload["n"] for e in events] == list(range(5))
    assert all(e.id > 0 for e in events)

    store.close()


def test_stored_event_type_is_frozen_dataclass(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    run_id = store.new_run_id()
    store.append("stop", {"reason": "max-iterations"}, run_id=run_id)

    event = store.get_events()[0]
    assert isinstance(event, StoredEvent)
    assert event.event_type == "stop"
    assert event.payload["reason"] == "max-iterations"

    store.close()


def test_public_api_has_no_update_or_delete(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    public = {m for m in dir(store) if not m.startswith("_")}
    assert "update" not in public
    assert "delete" not in public
    store.close()


def test_db_rejects_direct_update_and_delete(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    run_id = store.new_run_id()
    store.append("iteration_started", {}, run_id=run_id)

    # Bypass the Python API and hit SQLite directly.
    conn = sqlite3.connect(str(store.db_path))
    with pytest.raises(sqlite3.Error):
        conn.execute("UPDATE events SET event_type = 'tampered'")
    with pytest.raises(sqlite3.Error):
        conn.execute("DELETE FROM events")
    conn.close()
    store.close()


def test_get_event_types(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    run_a = store.new_run_id()
    run_b = store.new_run_id()

    store.append("iteration_started", {}, run_id=run_a)
    store.append("verify_result", {}, run_id=run_a)
    store.append("iteration_started", {}, run_id=run_b)

    assert set(store.get_event_types()) == {"iteration_started", "verify_result"}
    assert store.get_event_types(run_id=run_b) == ["iteration_started"]

    store.close()
