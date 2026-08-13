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


def _tier2_entry(signature: str, verify_output: str = "tier1 output", verify_tier2_output: str = "tier2 output") -> dict:
    """CHUNK-029: a verify-tier2-fail entry, where the loop also recorded
    tier 1's (passing) output alongside tier 2's (failing) output."""
    return {
        "failure_kind": "verify-tier2-fail",
        "failure_signature": signature,
        "verify_output": verify_output,
        "verify_tier2_output": verify_tier2_output,
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


def test_tier2_fail_feeds_tier2_output_not_tier1_output() -> None:
    """CHUNK-029: tier 1 passed (its output isn't the problem), so the
    retry evidence must be tier 2's output, not tier 1's."""
    history = [_tier2_entry("tier2sig1", verify_output="1 passed", verify_tier2_output="assert 2 == 1")]
    action = decide_action(history, repeat_threshold=3)
    assert action.kind == "retry"
    assert action.prompt_text == "assert 2 == 1"
    assert action.stop is False


def test_tier2_fail_is_not_in_stop_kinds() -> None:
    """A single verify-tier2-fail must NOT stop immediately -- unlike
    guard/tamper/commit-integrity, it goes through the normal retry ladder
    (CHUNK-029's acceptance: "treats them as their own class rather than
    folding into ordinary verify-fail", not "treats them like a guard
    abort")."""
    action = decide_action([_tier2_entry("tier2sig1")], repeat_threshold=3)
    assert action.kind == "retry"
    assert action.stop is False


def test_tier2_fail_repeats_escalate_and_stop_like_verify_fail() -> None:
    history = [_tier2_entry("tier2sig1") for _ in range(3)]
    assert decide_action(history[:2], repeat_threshold=3).kind == "escalate"
    assert decide_action(history, repeat_threshold=3).kind == "stop"


def test_tier2_fail_and_verify_fail_with_same_signature_string_stay_distinct_via_kind() -> None:
    """Even if two entries happened to share a signature hash (shouldn't
    normally happen, since the kind is baked into the hash identity per
    CHUNK-017/029), decide_action still keys retry evidence off the
    *current* entry's own kind -- not a stale assumption from history."""
    history = [_tier2_entry("shared", verify_output="ignored", verify_tier2_output="tier2 evidence")]
    action = decide_action(history, repeat_threshold=3)
    assert action.prompt_text == "tier2 evidence"
