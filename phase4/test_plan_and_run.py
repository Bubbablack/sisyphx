#!/usr/bin/env python3
"""CHUNK-040 tests for the pre-loop planning step (stubbed authoring,
meta-verification, and loop invocation -- real git init in the sandbox,
same policy as phase1/test_loop.py using real git in tmp_path)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from phase4.meta_verify import MetaVerifyResult
from phase4.plan_and_run import AUTHORING_OR_METAVERIFY_REJECTED_EXIT_CODE, plan_and_run
from phase4.test_author import AuthoringResult

PYPROJECT = '''\
[project]
name = "plan-and-run-test-fixture"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = ["pytest>=8.0.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
'''


def _make_repos(tmp_path):
    implementer_repo = tmp_path / "implementer"
    implementer_repo.mkdir()
    (implementer_repo / "pyproject.toml").write_text(PYPROJECT)
    (implementer_repo / "module.py").write_text("def add_one(x):\n    return x\n")
    task_path = implementer_repo / "task.txt"
    task_path.write_text("Fix the bug.")
    # A real implementer_repo is always already a git repo before
    # plan_and_run touches it (same assumption phase1/loop.py makes about
    # every repo it's pointed at).
    subprocess.run(["git", "init", "-q"], cwd=implementer_repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=implementer_repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=implementer_repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=implementer_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=implementer_repo, check=True)

    fixture_repo = tmp_path / "fixture"
    fixture_repo.mkdir()
    (fixture_repo / "pyproject.toml").write_text(PYPROJECT)

    acceptance_path = tmp_path / "acceptance_criteria.txt"
    acceptance_path.write_text("Write a property test for add_one.")

    return implementer_repo, task_path, fixture_repo, acceptance_path


def _no_test_written_authoring_result() -> AuthoringResult:
    return AuthoringResult(
        agent_exit_code=0, agent_timed_out=False, status='{"outcome": "blocked"}',
        test_written=False, test_path=Path("/nonexistent"), test_source="",
        agent_stdout="", agent_stderr="",
    )


def _test_written_authoring_result(tmp_path) -> AuthoringResult:
    return AuthoringResult(
        agent_exit_code=0, agent_timed_out=False, status='{"outcome": "done"}',
        test_written=True, test_path=tmp_path / "test_prop.py",
        test_source="def test_add_one(x=1):\n    from module import add_one\n    assert add_one(1) == 2\n",
        agent_stdout="", agent_stderr="",
    )


def test_authoring_failure_stops_before_loop(tmp_path):
    implementer_repo, task_path, fixture_repo, acceptance_path = _make_repos(tmp_path)

    with patch("phase4.plan_and_run.author_property_test", return_value=_no_test_written_authoring_result()), \
         patch("phase4.plan_and_run.meta_verify") as mock_meta_verify, \
         patch("phase4.plan_and_run._run_loop_subprocess") as mock_loop:
        result = plan_and_run(
            implementer_repo=implementer_repo, task_path=task_path, verify_cmd="pytest",
            verification_fixture_repo=fixture_repo, acceptance_criteria_path=acceptance_path,
            module_filename="module.py", test_filename="test_prop.py",
            known_good_source="def add_one(x): return x + 1\n",
            known_bad_source="def add_one(x): return x\n",
            authoring_sandbox=tmp_path / "sandbox", meta_verify_scratch=tmp_path / "mv_scratch",
        )

    assert result.stage == "authoring-failed"
    assert result.exit_code == AUTHORING_OR_METAVERIFY_REJECTED_EXIT_CODE
    mock_meta_verify.assert_not_called()
    mock_loop.assert_not_called()
    assert result.escalation_path is not None
    assert result.escalation_path.exists()
    assert "authoring-failed" in result.escalation_path.read_text()


def test_meta_verify_rejection_stops_before_loop(tmp_path):
    implementer_repo, task_path, fixture_repo, acceptance_path = _make_repos(tmp_path)
    unsound = MetaVerifyResult(
        sound=False, valid_checks=(), discarded_checks=("test_prop.py::test_add_one",),
        discriminating_checks=(), verify_tier2_command=None,
        reason="Every check failed against the known-good reference.",
    )

    with patch("phase4.plan_and_run.author_property_test", return_value=_test_written_authoring_result(tmp_path)), \
         patch("phase4.plan_and_run.meta_verify", return_value=unsound) as mock_meta_verify, \
         patch("phase4.plan_and_run._run_loop_subprocess") as mock_loop:
        result = plan_and_run(
            implementer_repo=implementer_repo, task_path=task_path, verify_cmd="pytest",
            verification_fixture_repo=fixture_repo, acceptance_criteria_path=acceptance_path,
            module_filename="module.py", test_filename="test_prop.py",
            known_good_source="def add_one(x): return x + 1\n",
            known_bad_source="def add_one(x): return x\n",
            authoring_sandbox=tmp_path / "sandbox", meta_verify_scratch=tmp_path / "mv_scratch",
        )

    assert result.stage == "meta-verify-rejected"
    assert result.exit_code == AUTHORING_OR_METAVERIFY_REJECTED_EXIT_CODE
    mock_meta_verify.assert_called_once()
    mock_loop.assert_not_called()
    assert result.escalation_path is not None
    assert "Every check failed" in result.escalation_path.read_text()
    # the implementer's real workspace must be untouched -- no test file written there
    assert not (implementer_repo / "test_prop.py").exists()


def test_sound_candidate_invokes_loop_with_verify_tier2(tmp_path):
    implementer_repo, task_path, fixture_repo, acceptance_path = _make_repos(tmp_path)
    sound = MetaVerifyResult(
        sound=True,
        valid_checks=("test_prop.py::test_add_one",),
        discarded_checks=(),
        discriminating_checks=("test_prop.py::test_add_one",),
        verify_tier2_command='uv run pytest test_prop.py test_literal_examples.py',
        reason="1 of 1 valid check(s) discriminate known-good from known-bad (0 discarded).",
    )
    fake_completed = MagicMock()
    fake_completed.returncode = 0

    with patch("phase4.plan_and_run.author_property_test", return_value=_test_written_authoring_result(tmp_path)), \
         patch("phase4.plan_and_run.meta_verify", return_value=sound), \
         patch("phase4.plan_and_run._run_loop_subprocess", return_value=fake_completed) as mock_loop:
        result = plan_and_run(
            implementer_repo=implementer_repo, task_path=task_path, verify_cmd="pytest module_test.py",
            verification_fixture_repo=fixture_repo, acceptance_criteria_path=acceptance_path,
            module_filename="module.py", test_filename="test_prop.py",
            known_good_source="def add_one(x): return x + 1\n",
            known_bad_source="def add_one(x): return x\n",
            authoring_sandbox=tmp_path / "sandbox", meta_verify_scratch=tmp_path / "mv_scratch",
            verify_tier2_timeout=15,
        )

    assert result.stage == "loop"
    assert result.exit_code == 0
    assert result.escalation_path is None
    mock_loop.assert_called_once()
    cmd = mock_loop.call_args.args[0]
    assert "--verify-tier2" in cmd
    assert 'uv run pytest test_prop.py test_literal_examples.py' in cmd
    assert "--verify-tier2-timeout" in cmd
    assert "15" in cmd
    # the meta-verified test file must have been written into the
    # implementer's actual workspace before the loop ran
    assert (implementer_repo / "test_prop.py").exists()


def test_authoring_sandbox_never_sees_implementer_repo_contents(tmp_path):
    """The authoring sandbox must be built fresh from only the
    acceptance-criteria file -- never a copy of the implementer's repo
    (which would leak the buggy implementation to the authoring agent)."""
    implementer_repo, task_path, fixture_repo, acceptance_path = _make_repos(tmp_path)
    unsound = MetaVerifyResult(
        sound=False, valid_checks=(), discarded_checks=(), discriminating_checks=(),
        verify_tier2_command=None, reason="rejected for this test",
    )

    with patch("phase4.plan_and_run.author_property_test", return_value=_test_written_authoring_result(tmp_path)) as mock_author, \
         patch("phase4.plan_and_run.meta_verify", return_value=unsound), \
         patch("phase4.plan_and_run._run_loop_subprocess"):
        plan_and_run(
            implementer_repo=implementer_repo, task_path=task_path, verify_cmd="pytest",
            verification_fixture_repo=fixture_repo, acceptance_criteria_path=acceptance_path,
            module_filename="module.py", test_filename="test_prop.py",
            known_good_source="def add_one(x): return x + 1\n",
            known_bad_source="def add_one(x): return x\n",
            authoring_sandbox=tmp_path / "sandbox", meta_verify_scratch=tmp_path / "mv_scratch",
        )

    sandbox = mock_author.call_args.kwargs["repo"]
    sandbox_contents = {p.name for p in sandbox.iterdir() if p.name != ".git"}
    assert sandbox_contents == {acceptance_path.name}
    assert "module.py" not in sandbox_contents
