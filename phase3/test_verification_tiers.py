#!/usr/bin/env python3
"""CHUNK-028 tests for the two-tier verification contract, per
phase3/notes/CHUNK-027.md."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from phase3.verification_tiers import run_tiered_verification


def _fake_completed(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    fake = MagicMock()
    fake.returncode = returncode
    fake.stdout = stdout
    fake.stderr = stderr
    return fake


def test_tier1_fail_skips_tier2(tmp_path):
    with patch("phase3.verification_tiers.subprocess.run", return_value=_fake_completed(1, stderr="boom")) as mock_run:
        result = run_tiered_verification(
            tmp_path, tier1_cmd="pytest", tier1_timeout=60,
            tier2_cmd="pytest test_prop.py", tier2_timeout=30,
        )
    assert mock_run.call_count == 1  # tier 2 never invoked
    assert result.passed is False
    assert result.failure_kind == "verify-fail"
    assert result.tier2 is None


def test_tier1_pass_no_tier2_configured_is_backward_compatible(tmp_path):
    with patch("phase3.verification_tiers.subprocess.run", return_value=_fake_completed(0)) as mock_run:
        result = run_tiered_verification(
            tmp_path, tier1_cmd="pytest", tier1_timeout=60,
        )
    assert mock_run.call_count == 1
    assert result.passed is True
    assert result.failure_kind == "verify-pass"
    assert result.tier2 is None


def test_tier1_pass_tier2_pass(tmp_path):
    with patch("phase3.verification_tiers.subprocess.run", return_value=_fake_completed(0)) as mock_run:
        result = run_tiered_verification(
            tmp_path, tier1_cmd="pytest", tier1_timeout=60,
            tier2_cmd="pytest test_prop.py", tier2_timeout=30,
        )
    assert mock_run.call_count == 2
    assert result.passed is True
    assert result.failure_kind == "verify-pass"
    assert result.tier2 is not None
    assert result.tier2.exit_code == 0


def test_tier1_pass_tier2_fail_is_a_distinct_failure_kind(tmp_path):
    responses = [_fake_completed(0), _fake_completed(1, stdout="1 failed")]
    with patch("phase3.verification_tiers.subprocess.run", side_effect=responses):
        result = run_tiered_verification(
            tmp_path, tier1_cmd="pytest", tier1_timeout=60,
            tier2_cmd="pytest test_prop.py", tier2_timeout=30,
        )
    assert result.passed is False
    assert result.failure_kind == "verify-tier2-fail"
    assert result.tier2.exit_code == 1
    assert "1 failed" in result.tier2.output


def test_tier1_timeout_is_treated_as_failure_and_skips_tier2(tmp_path):
    with patch(
        "phase3.verification_tiers.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=60),
    ) as mock_run:
        result = run_tiered_verification(
            tmp_path, tier1_cmd="pytest", tier1_timeout=60,
            tier2_cmd="pytest test_prop.py", tier2_timeout=30,
        )
    assert mock_run.call_count == 1
    assert result.passed is False
    assert result.failure_kind == "verify-fail"
    assert result.tier1.timed_out is True
    assert result.tier1.exit_code == -1


def test_tier2_timeout_is_a_distinct_failure_kind(tmp_path):
    responses = [_fake_completed(0), subprocess.TimeoutExpired(cmd="pytest test_prop.py", timeout=30)]
    with patch("phase3.verification_tiers.subprocess.run", side_effect=responses):
        result = run_tiered_verification(
            tmp_path, tier1_cmd="pytest", tier1_timeout=60,
            tier2_cmd="pytest test_prop.py", tier2_timeout=30,
        )
    assert result.passed is False
    assert result.failure_kind == "verify-tier2-fail"
    assert result.tier2.timed_out is True


def test_run_tier_uses_shell_true_and_cwd_like_tier1(tmp_path):
    """Confirm tier commands are run exactly like phase1/loop.py's existing
    run_verification -- shell=True, cwd=repo -- not through the agent's
    exec tool (CHUNK-027's contract point 1)."""
    with patch("phase3.verification_tiers.subprocess.run", return_value=_fake_completed(0)) as mock_run:
        run_tiered_verification(
            tmp_path, tier1_cmd="uv run pytest", tier1_timeout=60,
            tier2_cmd="uv run pytest test_prop.py", tier2_timeout=30,
        )
    first_call = mock_run.call_args_list[0]
    assert first_call.args[0] == "uv run pytest"
    assert first_call.kwargs["shell"] is True
    assert first_call.kwargs["cwd"] == tmp_path
    second_call = mock_run.call_args_list[1]
    assert second_call.args[0] == "uv run pytest test_prop.py"
