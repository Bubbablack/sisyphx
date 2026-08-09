"""Unit tests for loop.py -- subprocess calls to `devin` are stubbed (per
CHUNK-009's acceptance criteria); git operations run against a real
throwaway tmp_path repo since git itself is cheap and mocking it would just
test the mock. The one real, unstubbed `devin` invocation is a separate
manual run (see phase1/notes/CHUNK-009.md), not part of this file."""
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loop import (
    build_prompt,
    ensure_gitignored,
    git_commit_iteration,
    parse_status,
    run_devin,
)


# -- parse_status ------------------------------------------------------------

def test_parse_status_basic_json():
    assert parse_status('SISYPHX_STATUS: {"outcome": "done"}') == {"outcome": "done"}


def test_parse_status_none_when_absent():
    assert parse_status("nothing relevant here") is None


def test_parse_status_bare_word():
    assert parse_status("SISYPHX_STATUS: blocked") == {"outcome": "blocked"}


def test_parse_status_last_match_wins():
    stdout = 'echoing instruction SISYPHX_STATUS: {"outcome": "done"}\nSISYPHX_STATUS: {"outcome": "partial"}'
    assert parse_status(stdout) == {"outcome": "partial"}


# -- build_prompt -------------------------------------------------------------

def test_build_prompt_first_iteration_has_no_failure_evidence():
    prompt = build_prompt("Fix the bug.", previous_failure=None)
    assert "Fix the bug." in prompt
    assert "previous attempt" not in prompt
    assert "SISYPHX_STATUS" in prompt


def test_build_prompt_includes_previous_failure_verbatim():
    prompt = build_prompt("Fix the bug.", previous_failure="AssertionError: 5 != 6")
    assert "AssertionError: 5 != 6" in prompt
    assert "previous attempt" in prompt


def test_build_prompt_truncates_very_long_failure_output():
    huge = "x" * 10_000
    prompt = build_prompt("Fix it.", previous_failure=huge)
    # shouldn't blow up the prompt unboundedly
    assert len(prompt) < 6000


# -- run_devin: stubbed subprocess -------------------------------------------

def test_run_devin_normal_completion(tmp_path):
    fake_proc = MagicMock()
    fake_proc.communicate.return_value = ("SISYPHX_STATUS: {\"outcome\": \"done\"}", "")
    fake_proc.returncode = 0

    with patch("loop.subprocess.Popen", return_value=fake_proc) as mock_popen:
        exit_code, timed_out, stdout, stderr = run_devin(
            tmp_path, "do the task", timeout=30, run_dir=tmp_path
        )

    assert exit_code == 0
    assert timed_out is False
    assert "done" in stdout
    # confirm the contract from phase0/DEVIN_CLI_CONTRACT.md: bypass mode,
    # -p --prompt-file, no -c/-r
    cmd = mock_popen.call_args.args[0]
    assert cmd[:3] == ["devin", "--permission-mode", "bypass"]
    assert "-p" in cmd
    assert "--prompt-file" in cmd
    assert "-c" not in cmd and "-r" not in cmd


def test_run_devin_timeout_sends_sigterm_then_waits(tmp_path):
    fake_proc = MagicMock()
    # first communicate() call times out, second (after terminate) succeeds
    fake_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd="devin", timeout=30),
        ("partial output", ""),
    ]

    with patch("loop.subprocess.Popen", return_value=fake_proc):
        exit_code, timed_out, stdout, stderr = run_devin(
            tmp_path, "do the task", timeout=30, run_dir=tmp_path
        )

    assert timed_out is True
    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_not_called()  # graceful SIGTERM was enough
    assert stdout == "partial output"


def test_run_devin_timeout_escalates_to_sigkill_if_still_alive(tmp_path):
    fake_proc = MagicMock()
    fake_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd="devin", timeout=30),
        subprocess.TimeoutExpired(cmd="devin", timeout=5),  # still alive after SIGTERM
        ("killed output", ""),
    ]

    with patch("loop.subprocess.Popen", return_value=fake_proc):
        exit_code, timed_out, stdout, stderr = run_devin(
            tmp_path, "do the task", timeout=30, run_dir=tmp_path
        )

    assert timed_out is True
    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_called_once()


def test_run_devin_writes_prompt_file(tmp_path):
    fake_proc = MagicMock()
    fake_proc.communicate.return_value = ("ok", "")
    fake_proc.returncode = 0

    with patch("loop.subprocess.Popen", return_value=fake_proc):
        run_devin(tmp_path, "the actual task text", timeout=30, run_dir=tmp_path)

    assert (tmp_path / "prompt.txt").read_text() == "the actual task text"


# -- git_commit_iteration: real throwaway repo -------------------------------

@pytest.fixture
def real_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "file.txt").write_text("v1")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_git_commit_iteration_commits_when_there_are_changes(real_repo):
    (real_repo / "file.txt").write_text("v2")
    sha, committed = git_commit_iteration(real_repo, iteration=1, passed=False)
    assert committed is True
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=real_repo, capture_output=True, text=True
    ).stdout
    assert "iteration 1" in log
    assert "[fail]" in log


def test_git_commit_iteration_no_op_when_nothing_changed(real_repo):
    before_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=real_repo, capture_output=True, text=True
    ).stdout.strip()
    sha, committed = git_commit_iteration(real_repo, iteration=2, passed=True)
    assert committed is False
    assert sha == before_sha


# -- ensure_gitignored --------------------------------------------------------

def test_ensure_gitignored_creates_file(tmp_path):
    ensure_gitignored(tmp_path)
    assert ".agent-state/" in (tmp_path / ".gitignore").read_text()


def test_ensure_gitignored_is_idempotent(tmp_path):
    (tmp_path / ".gitignore").write_text("*.pyc\n")
    ensure_gitignored(tmp_path)
    ensure_gitignored(tmp_path)
    content = (tmp_path / ".gitignore").read_text()
    assert content.count(".agent-state/") == 1
    assert "*.pyc" in content
