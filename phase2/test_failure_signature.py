#!/usr/bin/env python3
"""CHUNK-017 tests for FailureSignature hashing.

Uses the real captured verify_output files from CHUNK-015 and CHUNK-014 logs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from phase2.failure_signature import (
    GUARD_SENTINEL,
    FailureSignature,
    classify_failure,
    failure_signature,
    normalize_verify_output,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTES = REPO_ROOT / "phase2" / "notes"


SCENARIOS: dict[str, dict] = {
    "pytest_a": {
        "file": "chunk015_pytest_a.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk015" / "pytest_a",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 1,
        "kind": "verify-fail",
    },
    "pytest_b": {
        "file": "chunk015_pytest_b.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk015" / "pytest_b",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 1,
        "kind": "verify-fail",
    },
    "import_a": {
        "file": "chunk015_import_a.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk015" / "import_a",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 1,
        "kind": "verify-fail",
    },
    "import_b": {
        "file": "chunk015_import_b.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk015" / "import_b",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 1,
        "kind": "verify-fail",
    },
    "timeout_a": {
        "file": "chunk015_timeout_a.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk015" / "timeout_a",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": -1,
        "kind": "verify-timeout",
    },
    "timeout_b": {
        "file": "chunk015_timeout_b.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk015" / "timeout_b",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": -1,
        "kind": "verify-timeout",
    },
    "guard_a": {
        "file": "chunk015_guard_a.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk014" / "guard_a",
        "agent_exit_code": 1,
        "agent_timed_out": False,
        "agent_stderr": GUARD_SENTINEL,
        "verify_exit_code": 1,
        "kind": "guard",
    },
    "guard_b": {
        "file": "chunk015_guard_b.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk014" / "guard_b",
        "agent_exit_code": 1,
        "agent_timed_out": False,
        "agent_stderr": GUARD_SENTINEL,
        "verify_exit_code": 1,
        "kind": "guard",
    },
    "sisyphx_selftest": {
        "file": "chunk015_sisyphx_selftest.txt",
        "repo": REPO_ROOT,
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 0,
        "kind": "verify-pass",
    },
    "chunk014_normal_a": {
        "file": "chunk015_chunk014_normal_a.txt",
        "repo": REPO_ROOT / "phase2" / "scratch" / "chunk014" / "normal_a",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 1,
        "kind": "verify-fail",
    },
}


def build_signature(name: str) -> FailureSignature:
    s = SCENARIOS[name]
    text = (NOTES / s["file"]).read_text()
    return failure_signature(
        verify_output=text,
        agent_exit_code=s["agent_exit_code"],
        agent_timed_out=s["agent_timed_out"],
        agent_stderr=s["agent_stderr"],
        verify_exit_code=s["verify_exit_code"],
        repo_path=s["repo"],
    )


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_classify_matches_expected_kind(name: str) -> None:
    s = SCENARIOS[name]
    assert (
        classify_failure(
            s["agent_exit_code"],
            s["agent_timed_out"],
            s["agent_stderr"],
            s["verify_exit_code"],
        )
        == s["kind"]
    )


def test_same_failure_same_signature() -> None:
    """Two repetitions of the same failure produce identical signatures."""
    pairs = [
        ("pytest_a", "pytest_b"),
        ("import_a", "import_b"),
        ("timeout_a", "timeout_b"),
        ("guard_a", "guard_b"),
    ]
    for a, b in pairs:
        sa = build_signature(a)
        sb = build_signature(b)
        assert sa.hash == sb.hash, f"{a} and {b} should have the same signature"
        assert sa.kind == sb.kind == SCENARIOS[a]["kind"]


def test_different_failures_different_signatures() -> None:
    """Different failure classes produce distinct signatures."""
    reps = ["pytest_a", "import_a", "timeout_a", "guard_a", "sisyphx_selftest", "chunk014_normal_a"]
    hashes = {name: build_signature(name).hash for name in reps}
    for i, a in enumerate(reps):
        for b in reps[i + 1 :]:
            assert hashes[a] != hashes[b], f"{a} and {b} should differ"


def test_normalize_is_stable_across_repeated_runs() -> None:
    """The same raw output normalizes to the same string."""
    for a, b in [("pytest_a", "pytest_b"), ("import_a", "import_b")]:
        text_a = (NOTES / SCENARIOS[a]["file"]).read_text()
        text_b = (NOTES / SCENARIOS[b]["file"]).read_text()
        norm_a = normalize_verify_output(text_a, repo_path=SCENARIOS[a]["repo"])
        norm_b = normalize_verify_output(text_b, repo_path=SCENARIOS[b]["repo"])
        assert norm_a == norm_b, f"{a} and {b} normalized text should match"


def test_classify_guard_from_chunk014_log() -> None:
    """A real guard-abort log entry from CHUNK-014 is classified correctly."""
    log_path = REPO_ROOT / "phase2" / "notes" / "chunk014_guard_a_log.jsonl"
    entry = json.loads(log_path.read_text().strip().splitlines()[-1])
    kind = classify_failure(
        entry["agent_exit_code"],
        entry["agent_timed_out"],
        (NOTES / "chunk014_guard_a_agent_stderr.txt").read_text(),
        entry["verify_exit_code"],
    )
    assert kind == "guard"


def test_classify_timeout_from_chunk014_log() -> None:
    """A real timeout log entry from CHUNK-014 is classified correctly."""
    log_path = REPO_ROOT / "phase2" / "notes" / "chunk014_timeout_a_log.jsonl"
    entry = json.loads(log_path.read_text().strip().splitlines()[-1])
    kind = classify_failure(
        entry["agent_exit_code"],
        entry["agent_timed_out"],
        (NOTES / "chunk014_timeout_a_agent_stderr.txt").read_text(),
        entry["verify_exit_code"],
    )
    assert kind == "agent-timeout"
