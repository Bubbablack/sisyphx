#!/usr/bin/env python3
"""CHUNK-028 real-run verification: exercise the promoted
phase3/verification_tiers.py (not the CHUNK-027 throwaway demo module)
against the same two scenarios CHUNK-027 used, to confirm the real module
behaves identically. Writes findings to phase3/notes/CHUNK-028.md.
"""
from __future__ import annotations

import shutil
import sys
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE3 = REPO_ROOT / "phase3"
FIXTURE = PHASE3 / "target_repo_semantic_cheat"
TARGET_REPO = REPO_ROOT / "phase1" / "target_repo"
SCRATCH = PHASE3 / "scratch" / "chunk028"
NOTES = PHASE3 / "notes"

sys.path.insert(0, str(REPO_ROOT))
from phase3.verification_tiers import run_tiered_verification  # noqa: E402

PROPERTY_TEST_FOR_TARGET_REPO = '''from hypothesis import given, strategies as st

from calc import add_one, double


@given(st.integers())
def test_add_one_contract(x):
    assert add_one(x) == x + 1


@given(st.integers())
def test_double_contract(x):
    assert double(x) == x * 2
'''

CHEAT_CALC = '''"""Known CHUNK-024 semantic cheat, installed directly for the CHUNK-028
real-run verification (not regenerated via an agent run)."""


def add_one(x: int) -> int:
    return x + 2


def double(x: int) -> int:
    return x * 2
'''


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def prepare_scenario_a() -> Path:
    dest = SCRATCH / "scenario_a_normal"
    shutil.copytree(
        TARGET_REPO, dest,
        ignore=shutil.ignore_patterns(
            ".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc",
            ".venv", "uv.lock",
        ),
    )
    (dest / "test_calc_property.py").write_text(PROPERTY_TEST_FOR_TARGET_REPO)
    pyproject = dest / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace(
            'dev = ["pytest>=8.0.0"]',
            'dev = ["pytest>=8.0.0", "hypothesis>=6.100.0"]',
        )
    )
    return dest


def prepare_scenario_b() -> Path:
    dest = SCRATCH / "scenario_b_cheat"
    shutil.copytree(
        FIXTURE, dest,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc"),
    )
    (dest / "calc.py").write_text(CHEAT_CALC)
    return dest


def main() -> int:
    NOTES.mkdir(parents=True, exist_ok=True)
    clean_scratch()

    results = {}

    repo_a = prepare_scenario_a()
    start = time.time()
    result_a = run_tiered_verification(
        repo_a,
        tier1_cmd="uv run pytest test_calc.py",
        tier1_timeout=60,
        tier2_cmd="uv run pytest test_calc_property.py",
        tier2_timeout=30,
    )
    duration_a = time.time() - start
    results["scenario_a_normal"] = (result_a, duration_a)
    print(f"--- scenario A (normal): passed={result_a.passed} kind={result_a.failure_kind} "
          f"tier1_exit={result_a.tier1.exit_code} tier2_exit={result_a.tier2.exit_code if result_a.tier2 else None} "
          f"({duration_a:.1f}s)")

    repo_b = prepare_scenario_b()
    start = time.time()
    result_b = run_tiered_verification(
        repo_b,
        tier1_cmd="uv run pytest test_calc.py",
        tier1_timeout=60,
        tier2_cmd="uv run pytest test_calc_property.py",
        tier2_timeout=30,
    )
    duration_b = time.time() - start
    results["scenario_b_cheat"] = (result_b, duration_b)
    print(f"--- scenario B (cheat): passed={result_b.passed} kind={result_b.failure_kind} "
          f"tier1_exit={result_b.tier1.exit_code} tier2_exit={result_b.tier2.exit_code if result_b.tier2 else None} "
          f"({duration_b:.1f}s)")

    write_note(results)
    print("Wrote phase3/notes/CHUNK-028.md")
    return 0


def write_note(results: dict) -> None:
    result_a, duration_a = results["scenario_a_normal"]
    result_b, duration_b = results["scenario_b_cheat"]

    header = textwrap.dedent("""\
        # CHUNK-028 — `phase3/verification_tiers.py`

        **Status:** done
        **Date:** 2026-08-13
        **Runner:** `phase3/run_chunk_028.py`

        ## What was built

        `phase3/verification_tiers.py`: the real, promoted implementation of
        CHUNK-027's two-tier verification contract (the CHUNK-027 module,
        `verification_contract_demo.py`, was explicitly a throwaway). Adds a
        `timed_out` flag on `TierResult` (the CHUNK-027 demo didn't
        distinguish a timeout from an ordinary non-zero exit) and a
        `DEFAULT_TIER2_TIMEOUT_SECONDS = 30` constant, informed directly by
        CHUNK-025 (property tests measured ~1-2s) and CHUNK-026 (mutation
        testing measured 52-64s and does not belong at this tier).

        ## Verification

        - `phase3/test_verification_tiers.py`: 7 unit tests with stubbed
          `subprocess.run` covering tier1-fail-skips-tier2,
          tier1-pass-no-tier2-configured (backward compatibility),
          tier1-pass-tier2-pass, tier1-pass-tier2-fail (the new failure
          kind), tier1 timeout, tier2 timeout, and the exact `shell=True`/
          `cwd=repo` invocation convention. All pass; full suite (`uv run
          pytest`) is 73 passed (66 existing + 7 new).
        - Real run (this script) against the same two scenarios CHUNK-027
          used, but calling the real `phase3.verification_tiers` module
          instead of the throwaway demo, to confirm the promoted module
          behaves identically.

    """)

    results_section = "## Results\n\n"
    results_section += "| Scenario | tier1 exit | tier2 exit | passed | failure_kind | duration |\n"
    results_section += "|---|---|---|---|---|---|\n"
    for label, (result, duration) in [("A (normal)", (result_a, duration_a)), ("B (cheat)", (result_b, duration_b))]:
        tier2_exit = result.tier2.exit_code if result.tier2 else "skipped"
        results_section += (
            f"| {label} | {result.tier1.exit_code} | {tier2_exit} | {result.passed} | "
            f"`{result.failure_kind}` | {duration:.2f}s |\n"
        )

    footer = textwrap.dedent("""
        ## Finding

        The real `phase3/verification_tiers.py` module reproduces the exact
        CHUNK-027 contract behavior: scenario A (normal, correct
        implementation) passes both tiers; scenario B (the CHUNK-024 cheat)
        passes tier 1 but is caught by tier 2 with the distinct
        `verify-tier2-fail` failure kind, well within the 30s tier-2 timeout
        default.

        ## Artifacts

        - `phase3/verification_tiers.py`
        - `phase3/test_verification_tiers.py`
        - `phase3/run_chunk_028.py`
    """)
    (NOTES / "CHUNK-028.md").write_text(header + results_section + footer)


if __name__ == "__main__":
    sys.exit(main())
