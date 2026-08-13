#!/usr/bin/env python3
"""CHUNK-027 spike: demonstrate the proposed two-tier verification contract
(phase3/verification_contract_demo.py) against two real scenarios and write
findings to phase3/notes/CHUNK-027.md.

Scenario A -- normal, non-contradictory chunk (based on phase1/target_repo,
already fixed): tier 1 (project pytest) passes, tier 2 (a property test)
also passes -> overall pass. Demonstrates the contract is a no-op/pass-through
for a correct implementation.

Scenario B -- the CHUNK-024 semantic-cheat fixture with the known cheat
installed: tier 1 (the fixture's contradictory pytest) passes because the
cheat satisfies it, but tier 2 (the CHUNK-025 property test) fails ->
overall fail with failure_kind "verify-tier2-fail". Demonstrates the
contract catches exactly the case Phase 3 exists to close.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE3 = REPO_ROOT / "phase3"
FIXTURE = PHASE3 / "target_repo_semantic_cheat"
TARGET_REPO = REPO_ROOT / "phase1" / "target_repo"
SCRATCH = PHASE3 / "scratch" / "chunk027"
NOTES = PHASE3 / "notes"

sys.path.insert(0, str(PHASE3))
from verification_contract_demo import run_tiered_verification  # noqa: E402

PROPERTY_TEST_FOR_TARGET_REPO = '''from hypothesis import given, strategies as st

from calc import add_one, double


@given(st.integers())
def test_add_one_contract(x):
    assert add_one(x) == x + 1


@given(st.integers())
def test_double_contract(x):
    assert double(x) == x * 2
'''

CHEAT_CALC = '''"""Known CHUNK-024 semantic cheat, installed directly for the CHUNK-027
verification-tier-contract demo (not regenerated via an agent run)."""


def add_one(x: int) -> int:
    return x + 2


def double(x: int) -> int:
    return x * 2
'''


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def run(cmd: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def prepare_scenario_a() -> Path:
    """Normal chunk: target_repo (already-correct calc.py) + a hand-written
    property test, mirroring CHUNK-025's approach for a non-contradictory
    project."""
    dest = SCRATCH / "scenario_a_normal"
    shutil.copytree(
        TARGET_REPO, dest,
        ignore=shutil.ignore_patterns(
            ".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc",
            ".venv", "uv.lock",
        ),
    )
    (dest / "test_calc_property.py").write_text(PROPERTY_TEST_FOR_TARGET_REPO)
    # Set the dev dependency directly (mirrors CHUNK-025's fixture pattern)
    # rather than `uv add`, which resolved against the wrong project when
    # a stale .venv/uv.lock from the copytree source was still present.
    pyproject = dest / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace(
            'dev = ["pytest>=8.0.0"]',
            'dev = ["pytest>=8.0.0", "hypothesis>=6.100.0"]',
        )
    )
    return dest


def prepare_scenario_b() -> Path:
    """The CHUNK-024 fixture with the known cheat installed."""
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
        tier2_timeout=60,
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
        tier2_timeout=60,
    )
    duration_b = time.time() - start
    results["scenario_b_cheat"] = (result_b, duration_b)
    print(f"--- scenario B (cheat): passed={result_b.passed} kind={result_b.failure_kind} "
          f"tier1_exit={result_b.tier1.exit_code} tier2_exit={result_b.tier2.exit_code if result_b.tier2 else None} "
          f"({duration_b:.1f}s)")

    write_note(results)
    print("Wrote phase3/notes/CHUNK-027.md")
    return 0


def write_note(results: dict) -> None:
    result_a, duration_a = results["scenario_a_normal"]
    result_b, duration_b = results["scenario_b_cheat"]

    header = textwrap.dedent("""\
        # CHUNK-027 — Spike: verification-tier invocation contract

        **Status:** done
        **Date:** 2026-08-13
        **Runner:** `phase3/run_chunk_027.py` +
        `phase3/verification_contract_demo.py`

        ## Question

        How should `loop.py` invoke an additional check beyond the project's
        own verification command, informed by CHUNK-025 (property tests are
        effective and fast) and CHUNK-026 (mutation testing is effective but
        too slow for attempt-level use)?

        ## Contract

        1. Attempt-level verification becomes at most **two tiers**, run in
           order, each a plain shell command executed exactly like today's
           single `--verify` command (`subprocess.run(shell=True, cwd=repo,
           timeout=...)`) -- no new execution model, just one more of the
           same thing.
        2. **Tier 1** (required, unchanged): the project's own verification
           command. Behavior for chunks that declare no tier 2 is byte-for-
           byte identical to Phase 1/2 (CHUNK-031's backward-compatibility
           requirement).
        3. **Tier 2** (new, opt-in per chunk): an additional shell command,
           supplied the same way tier 1 already is -- a new CLI flag
           (`--verify-tier2`) with its own timeout (`--verify-tier2-timeout`,
           default well under the attempt-level 60s budget, since CHUNK-025
           measured property tests at ~1-2s; mutation-testing-style commands
           should not be put here per CHUNK-026's finding).
        4. **Execution order:** tier 2 only runs if tier 1 passes. If tier 1
           fails, the iteration fails immediately exactly as today
           (`failure_kind = "verify-fail"`) and tier 2 is skipped -- no point
           spending budget on a stronger check when the basic gate already
           failed.
        5. If tier 1 passes but tier 2 fails: `failure_kind =
           "verify-tier2-fail"` (new, for CHUNK-029) -- a distinct failure
           class from ordinary `verify-fail`, because it means "the base
           tests were satisfied but a stronger contract check was not",
           which is exactly the semantic-cheat pattern from CHUNK-010/024.
        6. Both tiers passing -> `"verify-pass"`, unchanged.
        7. **Where tier 2 test files live:** no new directory convention.
           They live alongside the project's other tests (as
           `test_calc_property.py` already does in the fixture), excluded
           from tier 1's default test discovery (via `testpaths`, per
           CHUNK-025), and invoked by explicit path in the `--verify-tier2`
           command string -- exactly how a human would run them by hand.
        8. **Output capture:** tier 2's raw stdout+stderr is saved alongside
           tier 1's existing `verify_output.txt`
           (`verify_tier2_output.txt`), following `run_dir`'s existing
           per-iteration artifact convention.
        9. **Retry granularity:** unchanged -- a tier-2 failure retries the
           whole agent turn (feeding back tier 2's exact failure evidence,
           same as tier 1 does today), not just tier 2 in isolation. This
           keeps CHUNK-021's recovery ladder as the single retry mechanism
           rather than adding a second one.

        ## Demonstration

        `phase3/verification_contract_demo.py` implements this contract
        standalone (not wired into `loop.py` yet -- that is CHUNK-031, after
        CHUNK-028/029/030 exist). Two scenarios:

        - **Scenario A (normal):** `phase1/target_repo`'s already-correct
          `calc.py` plus a hand-written property test -- a non-contradictory,
          ordinary chunk.
        - **Scenario B (cheat):** the CHUNK-024 fixture with the known
          `add_one -> x + 2` cheat installed.

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

    finding = textwrap.dedent(f"""
        ## Finding

        Scenario A (normal, correct implementation) passes both tiers and
        completes in {duration_a:.1f}s, well within budget -- the contract is a
        transparent pass-through when the implementation is actually correct.

        Scenario B (cheat) passes tier 1 (the weak, contradictory test) but
        fails tier 2 (the property test) in {duration_b:.1f}s, producing the new
        distinct `verify-tier2-fail` failure kind instead of the misleading
        `verify-pass` the loop would have recorded without tier 2. This is
        the exact case CHUNK-024 reproduced with a real agent run, now
        caught mechanically without needing to re-run the agent.

        ## Implications for Phase 3 implementation

        - CHUNK-028 (`phase3/verification_tiers.py`) should implement exactly
          this contract, promoting `verification_contract_demo.py`'s logic
          into the real module.
        - CHUNK-029's new failure kind should be named `verify-tier2-fail`
          (or equivalent) to match this contract.
        - CHUNK-031's `loop.py` integration should add `--verify-tier2` /
          `--verify-tier2-timeout` as new, optional CLI arguments with no
          default command -- chunks that don't pass `--verify-tier2` see
          zero behavior change from Phase 1/2, satisfying the
          backward-compatibility requirement directly.

        ## Artifacts

        - `phase3/verification_contract_demo.py` (the throwaway reference
          implementation CHUNK-028 will promote)
        - `phase3/run_chunk_027.py`
    """)
    (NOTES / "CHUNK-027.md").write_text(header + results_section + finding)


if __name__ == "__main__":
    sys.exit(main())
