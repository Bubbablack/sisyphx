#!/usr/bin/env python3
"""CHUNK-021 tests for the minimal recovery ladder."""
from __future__ import annotations

import pytest

from phase2.recovery_ladder import RecoveryAction, decide_action


def _entry(kind: str, signature: str, verify_output: str = "fail") -> dict:
    return {
        "failure_kind": kind,
        "failure_signature": signature,
        "verify_output": verify_output,
    }


def test_decide_empty_history() -> None:
    assert decide_action([]) == RecoveryAction("retry", "", False)


def test_new_failure_gets_exact_evidence() -> None:
    history = [_entry("verify-fail", "abc123", "assert 5 == 6")]
    action = decide_action(history)
    assert action.kind == "retry"
    assert action.prompt_text == "assert 5 == 6"
    assert action.stop is False


def test_second_identical_signature_escalates() -> None:
    history = [
        _entry("verify-fail", "abc123", "assert 5 == 6"),
        _entry("verify-fail", "abc123", "assert 5 == 6"),
    ]
    action = decide_action(history, repeat_threshold=3)
    assert action.kind == "escalate"
    assert "Investigate the root cause" in action.prompt_text
    assert action.stop is False


def test_third_identical_signature_stops() -> None:
    history = [
        _entry("verify-fail", "abc123", "assert 5 == 6"),
        _entry("verify-fail", "abc123", "assert 5 == 6"),
        _entry("verify-fail", "abc123", "assert 5 == 6"),
    ]
    action = decide_action(history, repeat_threshold=3)
    assert action.kind == "stop"
    assert action.stop is True


def test_different_signature_resets_run() -> None:
    history = [
        _entry("verify-fail", "abc123", "assert 5 == 6"),
        _entry("verify-fail", "def456", "assert 9 == 10"),
    ]
    action = decide_action(history, repeat_threshold=3)
    assert action.kind == "retry"
    assert action.prompt_text == "assert 9 == 10"


def test_guard_aborts_stop_immediately() -> None:
    action = decide_action([_entry("guard", "g1")], repeat_threshold=3)
    assert action.kind == "stop"
    assert action.stop is True


def test_tamper_stops_immediately() -> None:
    action = decide_action([_entry("tamper", "t1")], repeat_threshold=3)
    assert action.kind == "stop"
    assert action.stop is True


def test_timeout_repeats_escalate_and_stop() -> None:
    history = [
        _entry("verify-timeout", "to1"),
        _entry("verify-timeout", "to1"),
        _entry("verify-timeout", "to1"),
    ]
    assert decide_action(history[:2], repeat_threshold=3).kind == "escalate"
    assert decide_action(history, repeat_threshold=3).kind == "stop"


def test_threshold_one_stops_immediately() -> None:
    history = [_entry("verify-fail", "x")]
    assert decide_action(history, repeat_threshold=1).stop is True
