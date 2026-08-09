"""Tests for CHUNK-011: run log (`.agent-state/runs/log.jsonl`) format and
`run_loop` integration logging. Subprocess calls to `devin` are mocked; git
operations run against a real throwaway `tmp_path` repo, same policy as
`test_loop.py`."""
import json
import subprocess
from pathlib import Path

import pytest

import loop
from loop import read_log, run_loop


@pytest.fixture
def real_repo(tmp_path):
    """A minimal git repo that the loop can commit into."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "sisyphx-test@local"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "SisyphX Test"], cwd=tmp_path, check=True)
    (tmp_path / "README").write_text("init")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


# -- read_log schema tests ---------------------------------------------------


def test_read_log_returns_empty_list_for_missing_file(tmp_path):
    assert read_log(tmp_path / "does_not_exist.jsonl") == []


def test_read_log_parses_jsonl(tmp_path):
    log_path = tmp_path / "log.jsonl"
    log_path.write_text(
        json.dumps({"iteration": 1, "passed": True}) + "\n"
        + json.dumps({"iteration": 2, "passed": False}) + "\n"
    )
    entries = read_log(log_path)
    assert len(entries) == 2
    assert entries[0]["iteration"] == 1
    assert entries[0]["passed"] is True
    assert entries[1]["iteration"] == 2
    assert entries[1]["passed"] is False


def test_read_log_ignores_blank_and_malformed_lines(tmp_path):
    log_path = tmp_path / "log.jsonl"
    log_path.write_text(
        json.dumps({"iteration": 1}) + "\n\n\n"
        "this is not json\n"
        + json.dumps({"iteration": 2}) + "\n"
    )
    entries = read_log(log_path)
    assert len(entries) == 2
    assert [e["iteration"] for e in entries] == [1, 2]


def test_read_log_skips_non_dict_lines(tmp_path):
    log_path = tmp_path / "log.jsonl"
    log_path.write_text(
        json.dumps(["not", "a", "dict"]) + "\n"
        + json.dumps({"iteration": 1}) + "\n"
    )
    entries = read_log(log_path)
    assert len(entries) == 1
    assert entries[0]["iteration"] == 1


# -- run_loop log integration tests ------------------------------------------


def test_run_loop_logs_pass_and_stops(real_repo, monkeypatch):
    """If verification passes on iteration 1, the log has one entry and
    `run_loop` returns 0."""
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""),
    )
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (0, "ok"),
    )
    exit_code = run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="true",
        max_iterations=3,
        log=lambda *a: None,
    )
    assert exit_code == 0
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 1
    assert log[0]["iteration"] == 1
    assert log[0]["passed"] is True
    assert log[0]["verify_exit_code"] == 0
    assert log[0]["committed"] is True
    assert log[0]["run_dir"] == ".agent-state/runs/001"


def test_run_loop_logs_max_iterations(real_repo, monkeypatch):
    """If verification never passes and max_iterations is reached, the log
    contains one entry per iteration and `run_loop` returns 2."""
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "blocked"}', ""),
    )
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (1, "same failure"),
    )
    exit_code = run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="false",
        max_iterations=2,
        repeat_threshold=3,  # don't trigger before max_iterations
        log=lambda *a: None,
    )
    assert exit_code == 2
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 2
    assert all(not e["passed"] for e in log)
    assert [e["iteration"] for e in log] == [1, 2]


def test_run_loop_logs_repeat_threshold_stop(real_repo, monkeypatch):
    """If verification produces the same failure `repeat_threshold` times in a
    row, the loop stops early (exit 3) and the log has exactly
    `repeat_threshold` entries."""
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "blocked"}', ""),
    )
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (1, "identical failure"),
    )
    exit_code = run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="false",
        max_iterations=5,
        repeat_threshold=3,
        log=lambda *a: None,
    )
    assert exit_code == 3
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 3
    assert all(not e["passed"] for e in log)
    assert [e["verify_exit_code"] for e in log] == [1, 1, 1]


def test_run_loop_log_entry_contains_all_canonical_fields(real_repo, monkeypatch):
    """Every log entry contains the canonical CHUNK-011 fields, plus sensible
    values for agent/verify outcomes."""
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""),
    )
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (0, "ok"),
    )
    run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="true",
        max_iterations=1,
        log=lambda *a: None,
    )
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 1
    entry = log[0]
    canonical = (
        "iteration",
        "timestamp",
        "agent_exit_code",
        "agent_timed_out",
        "status",
        "verify_exit_code",
        "passed",
        "git_sha",
        "committed",
        "duration_seconds",
        "run_dir",
    )
    for field in canonical:
        assert field in entry, f"missing canonical field: {field}"
    assert entry["agent_exit_code"] == 0
    assert entry["agent_timed_out"] is False
    assert entry["status"] == {"outcome": "done"}
    assert entry["verify_exit_code"] == 0
    assert entry["passed"] is True
    assert entry["duration_seconds"] >= 0
