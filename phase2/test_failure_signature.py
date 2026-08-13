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
PHASE3_NOTES = REPO_ROOT / "phase3" / "notes"


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
    # CHUNK-029: real captured tier1+tier2 outputs from CHUNK-025's cheat vs.
    # genuine-fix runs (phase3/notes/chunk025_*). Tier 1 (test_calc.py)
    # passes in both cheat scenarios below -- only tier 2 (the property
    # test) tells them apart.
    "tier2_cheat_a": {
        "notes_dir": PHASE3_NOTES,
        "file": "chunk025_cheat_default_pytest.txt",       # tier 1 (passes)
        "tier2_file": "chunk025_cheat_property_pytest.txt",  # tier 2 (fails)
        "repo": REPO_ROOT / "phase3" / "scratch" / "chunk025" / "cheat",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 0,
        "verify_tier2_exit_code": 1,
        "kind": "verify-tier2-fail",
    },
    "tier2_cheat_b": {
        # A genuinely independent second real run of the same cheat/property
        # test pairing (phase3/notes/chunk029_cheat_property_pytest_b.txt),
        # captured for this chunk. Its tier2 output is NOT byte-identical to
        # tier2_cheat_a's -- Hypothesis's duration and its inline "# or any
        # other generated value" annotation both vary between runs, which is
        # exactly the real normalization gap this chunk found and fixed
        # (see rule 8b in normalize_verify_output).
        "notes_dir": PHASE3_NOTES,
        "file": "chunk025_cheat_default_pytest.txt",
        "tier2_file": "chunk029_cheat_property_pytest_b.txt",
        "repo": REPO_ROOT / "phase3" / "scratch" / "chunk025" / "cheat",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 0,
        "verify_tier2_exit_code": 1,
        "kind": "verify-tier2-fail",
    },
    "tier2_genuine_fix": {
        "notes_dir": PHASE3_NOTES,
        "file": "chunk025_genuine_fix_default_pytest.txt",
        "tier2_file": "chunk025_genuine_fix_property_pytest.txt",
        "repo": REPO_ROOT / "phase3" / "scratch" / "chunk025" / "genuine_fix",
        "agent_exit_code": 0,
        "agent_timed_out": False,
        "agent_stderr": "",
        "verify_exit_code": 0,
        "verify_tier2_exit_code": 0,
        "kind": "verify-pass",
    },
}


def build_signature(name: str) -> FailureSignature:
    s = SCENARIOS[name]
    notes_dir = s.get("notes_dir", NOTES)
    text = (notes_dir / s["file"]).read_text()
    tier2_text = (notes_dir / s["tier2_file"]).read_text() if "tier2_file" in s else ""
    return failure_signature(
        verify_output=text,
        agent_exit_code=s["agent_exit_code"],
        agent_timed_out=s["agent_timed_out"],
        agent_stderr=s["agent_stderr"],
        verify_exit_code=s["verify_exit_code"],
        repo_path=s["repo"],
        verify_tier2_output=tier2_text,
        verify_tier2_exit_code=s.get("verify_tier2_exit_code"),
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
            s.get("verify_tier2_exit_code"),
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
        ("tier2_cheat_a", "tier2_cheat_b"),  # CHUNK-029
    ]
    for a, b in pairs:
        sa = build_signature(a)
        sb = build_signature(b)
        assert sa.hash == sb.hash, f"{a} and {b} should have the same signature"
        assert sa.kind == sb.kind == SCENARIOS[a]["kind"]


def test_different_failures_different_signatures() -> None:
    """Different failure classes produce distinct signatures."""
    reps = [
        "pytest_a", "import_a", "timeout_a", "guard_a", "sisyphx_selftest",
        "chunk014_normal_a", "tier2_cheat_a", "tier2_genuine_fix",
    ]
    hashes = {name: build_signature(name).hash for name in reps}
    for i, a in enumerate(reps):
        for b in reps[i + 1 :]:
            assert hashes[a] != hashes[b], f"{a} and {b} should differ"


def test_tier2_fail_is_a_distinct_kind_from_ordinary_verify_fail() -> None:
    """CHUNK-029: tier 1 passing but tier 2 failing must not be folded into
    ordinary verify-fail, and must not be confused with verify-pass either --
    it is its own class."""
    tier2_fail = build_signature("tier2_cheat_a")
    ordinary_fail = build_signature("pytest_a")
    tier2_pass = build_signature("tier2_genuine_fix")
    assert tier2_fail.kind == "verify-tier2-fail"
    assert tier2_fail.kind != ordinary_fail.kind
    assert tier2_fail.kind != tier2_pass.kind
    assert tier2_pass.kind == "verify-pass"


def test_tier2_not_configured_reproduces_phase1_2_behavior() -> None:
    """A chunk that never configures tier 2 (verify_tier2_exit_code=None,
    the default) must classify and hash identically to before CHUNK-029."""
    s = SCENARIOS["pytest_a"]
    text = (NOTES / s["file"]).read_text()
    with_default = failure_signature(
        verify_output=text,
        agent_exit_code=s["agent_exit_code"],
        agent_timed_out=s["agent_timed_out"],
        agent_stderr=s["agent_stderr"],
        verify_exit_code=s["verify_exit_code"],
        repo_path=s["repo"],
    )
    explicit_none = failure_signature(
        verify_output=text,
        agent_exit_code=s["agent_exit_code"],
        agent_timed_out=s["agent_timed_out"],
        agent_stderr=s["agent_stderr"],
        verify_exit_code=s["verify_exit_code"],
        repo_path=s["repo"],
        verify_tier2_output="",
        verify_tier2_exit_code=None,
    )
    assert with_default == explicit_none
    assert with_default.kind == "verify-fail"


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
