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
from phase2.event_store import EventStore


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


# -- CHUNK-045: --repo must be the actual git toplevel -----------------------


def test_run_loop_rejects_repo_not_in_a_git_repository(tmp_path):
    """A plain directory with no git repository at all must fail fast,
    not proceed and crash deeper inside git-dependent guard logic."""
    plain_dir = tmp_path / "not_a_repo"
    plain_dir.mkdir()
    exit_code = run_loop(
        repo=plain_dir, task_text="fix it", verify_cmd="true", max_iterations=1, log=lambda *a: None,
    )
    assert exit_code == 1


def test_run_loop_rejects_repo_that_is_a_git_subdirectory(tmp_path):
    """CHUNK-045's real finding: if --repo is a subdirectory of a larger
    git repository (not the toplevel), git reports paths relative to the
    outer toplevel, which silently breaks permitted_paths/tamper-guard
    matching. This must be rejected up front with a clear error, not
    proceed and misclassify legitimate changes as tampering."""
    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=outer, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=outer, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=outer, check=True)
    (outer / "README").write_text("init")
    subprocess.run(["git", "add", "-A"], cwd=outer, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=outer, check=True)

    inner = outer / "inner-project"
    inner.mkdir()
    (inner / "README").write_text("inner")

    exit_code = run_loop(
        repo=inner, task_text="fix it", verify_cmd="true", max_iterations=1, log=lambda *a: None,
    )
    assert exit_code == 1


def test_run_loop_accepts_repo_that_is_the_git_toplevel(real_repo, monkeypatch):
    """A proper repo (--repo IS the git toplevel) must proceed normally --
    this is implicitly covered by every other test in this file using the
    `real_repo` fixture, asserted explicitly here for clarity."""
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""),
    )
    monkeypatch.setattr(loop, "run_verification", lambda repo, cmd, timeout: (0, "ok"))
    exit_code = run_loop(
        repo=real_repo, task_text="fix it", verify_cmd="true", max_iterations=1, log=lambda *a: None,
    )
    assert exit_code == 0


# -- CHUNK-048: review-marker startup precondition ---------------------------


def test_run_loop_refuses_to_start_with_review_marker_present(real_repo):
    """A real, on-disk `REVIEW:` marker (per AGENTS.md's convention) must
    stop the run before iteration 1 -- no agent invocation, no commit."""
    (real_repo / "app.py").write_text(
        "def retry_call():\n"
        "    # REVIEW: this retry loop has no backoff, can hammer the API -- fix?\n"
        "    pass\n"
    )
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=real_repo, capture_output=True, text=True
    ).stdout.strip()

    exit_code = run_loop(
        repo=real_repo, task_text="fix it", verify_cmd="true", max_iterations=1, log=lambda *a: None,
    )
    assert exit_code == 1

    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=real_repo, capture_output=True, text=True
    ).stdout.strip()
    assert head_after == head_before  # nothing committed
    assert not (real_repo / ".agent-state" / "runs" / "log.jsonl").exists()


def test_run_loop_proceeds_when_review_marker_is_only_in_markdown(real_repo, monkeypatch):
    """A `REVIEW:` mention inside a markdown doc (prose/fenced example, per
    CHUNK-047's finding about this repo's own PLAN.md/AGENTS.md) must not
    block a run -- only source-code files are scanned."""
    (real_repo / "NOTES.md").write_text(
        "Leave feedback with a `REVIEW:` tag, e.g. `# REVIEW: fix this`.\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=real_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add notes"], cwd=real_repo, check=True)

    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""),
    )
    monkeypatch.setattr(loop, "run_verification", lambda repo, cmd, timeout: (0, "ok"))
    exit_code = run_loop(
        repo=real_repo, task_text="fix it", verify_cmd="true", max_iterations=1, log=lambda *a: None,
    )
    assert exit_code == 0


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


# -- CHUNK-031: opt-in second verification tier -----------------------------


def test_run_loop_without_tier2_arg_leaves_tier2_fields_empty(real_repo, monkeypatch):
    """CHUNK-031 backward compatibility: a chunk that never passes
    verify_tier2_cmd gets verify_tier2_exit_code=None and
    verify_tier2_output="" in the log, and run_verification is called only
    once per iteration (tier 1 only)."""
    calls = []

    def fake_verify(repo, cmd, timeout):
        calls.append(cmd)
        return 0, "ok"

    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""),
    )
    monkeypatch.setattr(loop, "run_verification", fake_verify)
    exit_code = run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="true",
        max_iterations=3,
        log=lambda *a: None,
    )
    assert exit_code == 0
    assert calls == ["true"]  # tier 2 never invoked
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert log[0]["verify_tier2_exit_code"] is None
    assert log[0]["verify_tier2_output"] == ""


def test_run_loop_tier1_fail_skips_tier2(real_repo, monkeypatch):
    """If tier 1 fails, tier 2 must never run (no budget spent on a
    stronger check when the basic gate already failed)."""
    calls = []

    def fake_verify(repo, cmd, timeout):
        calls.append(cmd)
        return (1, "tier1 failure") if cmd == "false" else (0, "tier2 should not run")

    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "blocked"}', ""),
    )
    monkeypatch.setattr(loop, "run_verification", fake_verify)
    run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="false",
        verify_tier2_cmd="pytest test_property.py",
        max_iterations=1,
        log=lambda *a: None,
    )
    assert calls == ["false"]  # tier 2 skipped entirely
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert log[0]["failure_kind"] == "verify-fail"
    assert log[0]["verify_tier2_exit_code"] is None


def test_run_loop_tier1_pass_tier2_pass(real_repo, monkeypatch):
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""),
    )
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (0, "tier1 ok") if cmd == "true" else (0, "tier2 ok"),
    )
    exit_code = run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="true",
        verify_tier2_cmd="pytest test_property.py",
        max_iterations=1,
        log=lambda *a: None,
    )
    assert exit_code == 0
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert log[0]["passed"] is True
    assert log[0]["failure_kind"] == "verify-pass"
    assert log[0]["verify_tier2_exit_code"] == 0
    assert log[0]["verify_tier2_output"] == "tier2 ok"


def test_run_loop_tier1_pass_tier2_fail_is_distinct_kind_and_retries(real_repo, monkeypatch):
    """A tier-2 failure produces the distinct verify-tier2-fail kind (not a
    misleading verify-pass, and not folded into ordinary verify-fail), and
    the loop retries rather than stopping immediately (it is not in
    STOP_KINDS)."""
    monkeypatch.setattr(
        loop, "run_devin",
        lambda repo, text, timeout, run_dir: (0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""),
    )
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (0, "tier1 ok") if cmd == "true" else (1, "assert 2 == 1"),
    )
    exit_code = run_loop(
        repo=real_repo,
        task_text="fix it",
        verify_cmd="true",
        verify_tier2_cmd="pytest test_property.py",
        max_iterations=2,
        repeat_threshold=5,  # don't trigger stop within this test
        log=lambda *a: None,
    )
    assert exit_code == 2  # max_iterations exhausted, never passed
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 2
    for entry in log:
        assert entry["passed"] is False
        assert entry["failure_kind"] == "verify-tier2-fail"
        assert entry["verify_tier2_exit_code"] == 1
        assert entry["verify_tier2_output"] == "assert 2 == 1"


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


def test_run_loop_stops_on_test_tamper(real_repo, monkeypatch):
    """If the agent edits a protected test file, the tamper guard triggers
    and the loop stops immediately with failure_kind='tamper'."""
    def agent_tampers(repo, text, timeout, run_dir):
        (repo / "test_calc.py").write_text("# tampered")
        return 0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""

    monkeypatch.setattr(loop, "run_devin", agent_tampers)
    exit_code = run_loop(
        repo=real_repo,
        task_text="add a new test",
        verify_cmd="true",
        max_iterations=3,
        log=lambda *a: None,
    )
    assert exit_code == 4
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 1
    assert log[0]["failure_kind"] == "tamper"
    assert log[0]["passed"] is False


def test_run_loop_allows_permitted_path(real_repo, monkeypatch):
    """When a protected path is explicitly permitted, the tamper guard does not
    stop the loop."""
    def agent_tampers(repo, text, timeout, run_dir):
        (repo / "test_calc.py").write_text("# allowed edit")
        return 0, False, 'SISYPHX_STATUS: {"outcome": "done"}', ""

    monkeypatch.setattr(loop, "run_devin", agent_tampers)
    monkeypatch.setattr(
        loop, "run_verification",
        lambda repo, cmd, timeout: (0, "ok"),
    )
    exit_code = run_loop(
        repo=real_repo,
        task_text="add a new test",
        verify_cmd="true",
        max_iterations=3,
        permitted_paths=("test_calc.py",),
        log=lambda *a: None,
    )
    assert exit_code == 0
    log = read_log(real_repo / ".agent-state" / "runs" / "log.jsonl")
    assert len(log) == 1
    assert log[0]["failure_kind"] == "verify-pass"


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
        "verify_output",
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


def test_run_loop_writes_queryable_event_trail(real_repo, monkeypatch):
    """Every run also persists a matching event trail in SQLite."""
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
        max_iterations=1,
        log=lambda *a: None,
    )
    assert exit_code == 0

    store = EventStore(real_repo / ".agent-state" / "events.db")
    events = store.get_events()
    types = [e.event_type for e in events]
    assert "run_started" in types
    assert "iteration_started" in types
    assert "agent_finished" in types
    assert "verify_result" in types
    assert "iteration_finished" in types
    assert "stop" in types

    stop = [e for e in events if e.event_type == "stop"][-1]
    assert stop.payload["reason"] == "verify-pass"
    assert stop.payload["exit_code"] == 0

    verify_event = [e for e in events if e.event_type == "verify_result"][0]
    assert verify_event.payload["passed"] is True
    assert verify_event.payload["failure_kind"] == "verify-pass"
    assert verify_event.run_id == [e for e in events if e.event_type == "run_started"][0].run_id

    store.close()
