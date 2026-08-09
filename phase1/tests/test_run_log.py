"""Tests for CHUNK-011: run log (`.agent-state/runs/log.jsonl`) format and
`run_loop` integration logging. Subprocess calls to `devin` are mocked; git
operations run against a real throwaway `tmp_path` repo, same policy as
`test_loop.py`."""
import json
import os
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


def test_run_loop_stops_on_guard_abort(real_repo, monkeypatch):
    """A guard abort (exit 1 + sentinel stderr) stops the loop immediately
    with exit 4 and records failure_kind='guard'."""
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (1, False, "", loop.GUARD_SENTINEL),
    )
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (1, ""),
    )
    exit_code = run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="false",
        max_iterations=5,
        repeat_threshold=3,
        log=lambda *a: None,
    )
    assert exit_code == 4
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 1
    assert log[0]["failure_kind"] == "guard"
    assert log[0]["passed"] is False


def test_run_loop_stops_on_unauthorized_agent_commit(real_repo, monkeypatch):
    """If the agent creates its own git commit, the loop detects it, logs
    failure_kind='commit-integrity', and exits 4."""
    def agent_makes_commit(repo, text, timeout, run_dir):
        (repo / "agent_marker.txt").write_text("I was here")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "Agent",
            "GIT_AUTHOR_EMAIL": "agent@example.com",
        })
        subprocess.run(
            ["git", "commit", "-m", "agent commit"],
            cwd=repo,
            check=True,
            env=env,
        )
        return 0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""

    monkeypatch.setattr(loop, "run_devin", agent_makes_commit)
    exit_code = run_loop(
        repo=real_repo,
        task_text="commit something",
        verify_cmd="true",
        max_iterations=3,
        log=lambda *a: None,
    )
    assert exit_code == 4
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 1
    assert log[0]["failure_kind"] == "commit-integrity"
    assert log[0]["passed"] is False
    assert log[0]["head_before"] != log[0]["head_after"]


def test_run_loop_signature_repeat_detection_ignores_volatile_durations(real_repo, monkeypatch):
    """Two verify-fail outputs that differ only in duration still have the same
    FailureSignature, so the loop stops at repeat_threshold=2."""
    outputs = [
        "1 failed, 1 passed in 0.05s\nFAILED test_calc.py::test_add_one - assert 5 == 6",
        "1 failed, 1 passed in 0.07s\nFAILED test_calc.py::test_add_one - assert 5 == 6",
    ]
    output_iter = iter(outputs)
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "blocked"}', ""),
    )
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (1, next(output_iter)),
    )
    exit_code = run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="false",
        max_iterations=5,
        repeat_threshold=2,
        log=lambda *a: None,
    )
    assert exit_code == 3
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 2
    assert log[0]["failure_signature"] == log[1]["failure_signature"]
    assert log[0]["failure_kind"] == "verify-fail"


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
        "failure_kind",
        "failure_signature",
        "head_before",
        "head_after",
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
