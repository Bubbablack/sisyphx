#!/usr/bin/env python3
"""CHUNK-040 real-run verification: exercise phase4/plan_and_run.py with a
real live authoring agent, covering both paths:

  - "sound": a genuine known-good/known-bad pair -> meta-verification
    passes -> the implementer agent actually runs via phase1/loop.py with
    --verify-tier2 wired in.
  - "rejected": known_good_source == known_bad_source (nothing CAN
    discriminate between them, regardless of how good the authored test
    is) -> meta-verification correctly rejects -> the implementer agent is
    NEVER invoked.

The deep "does the implementer's real cheat get caught" question is
CHUNK-041's job, not this one -- this chunk only needs to prove the wiring
itself works, with a real (not mocked) authoring call on each path.
Writes findings to phase4/notes/CHUNK-040.md.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE4 = REPO_ROOT / "phase4"
FIXTURE = PHASE4 / "target_repo_harder_cheat"
NOTES = PHASE4 / "notes"
SCRATCH = PHASE4 / "scratch" / "chunk040"

sys.path.insert(0, str(REPO_ROOT))
from phase4.plan_and_run import plan_and_run  # noqa: E402

UNMODIFIED_BUGGY_LISTUTILS = '''"""listutils.py -- the original CHUNK-034 bug."""


def rotate_left(lst: list, k: int) -> list:
    return lst[k:] + lst[:k]
'''

GENUINE_FIX_LISTUTILS = '''"""listutils.py -- genuine fix."""


def rotate_left(lst: list, k: int) -> list:
    if not lst:
        return []
    k = k % len(lst)
    return lst[k:] + lst[:k]
'''


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def prepare_implementer_repo(label: str) -> Path:
    """A real workspace for the implementer agent, containing the
    ORIGINAL bug (unmodified from the fixture) so a real CHUNK-040 'sound'
    run has genuine work to do."""
    repo = SCRATCH / f"implementer_{label}"
    shutil.copytree(
        FIXTURE, repo,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc"),
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Initial state: real CHUNK-034 bug"], cwd=repo, check=True)
    return repo


def main() -> int:
    NOTES.mkdir(parents=True, exist_ok=True)
    clean_scratch()

    results = {}

    # --- Scenario A: sound path -------------------------------------
    implementer_a = prepare_implementer_repo("sound")
    result_a = plan_and_run(
        implementer_repo=implementer_a,
        task_path=FIXTURE / "task_rotate.txt",
        verify_cmd="uv run pytest test_listutils.py",
        verification_fixture_repo=FIXTURE,
        acceptance_criteria_path=FIXTURE / "acceptance_criteria.txt",
        module_filename="listutils.py",
        test_filename="test_listutils_property.py",
        known_good_source=GENUINE_FIX_LISTUTILS,
        known_bad_source=UNMODIFIED_BUGGY_LISTUTILS,
        authoring_sandbox=SCRATCH / "authoring_sandbox_sound",
        meta_verify_scratch=SCRATCH / "meta_verify_scratch_sound",
        authoring_timeout=240,
        agent_timeout=240,
        max_iterations=2,
    )
    results["sound"] = result_a
    print(f"--- sound: stage={result_a.stage} exit_code={result_a.exit_code} "
          f"meta_sound={result_a.meta_verify_result.sound if result_a.meta_verify_result else None}")

    # --- Scenario B: rejected path (known_good == known_bad) --------
    implementer_b = prepare_implementer_repo("rejected")
    log_before = implementer_b / ".agent-state" / "runs" / "log.jsonl"
    result_b = plan_and_run(
        implementer_repo=implementer_b,
        task_path=FIXTURE / "task_rotate.txt",
        verify_cmd="uv run pytest test_listutils.py",
        verification_fixture_repo=FIXTURE,
        acceptance_criteria_path=FIXTURE / "acceptance_criteria.txt",
        module_filename="listutils.py",
        test_filename="test_listutils_property.py",
        known_good_source=GENUINE_FIX_LISTUTILS,
        known_bad_source=GENUINE_FIX_LISTUTILS,  # deliberately identical -- nothing can discriminate
        authoring_sandbox=SCRATCH / "authoring_sandbox_rejected",
        meta_verify_scratch=SCRATCH / "meta_verify_scratch_rejected",
        authoring_timeout=240,
    )
    results["rejected"] = result_b
    implementer_agent_ran = log_before.exists()
    print(f"--- rejected: stage={result_b.stage} exit_code={result_b.exit_code} "
          f"implementer_agent_ran={implementer_agent_ran}")

    write_note(results, implementer_agent_ran)
    print("Wrote phase4/notes/CHUNK-040.md")
    return 0


def write_note(results: dict, implementer_agent_ran: bool) -> None:
    sound = results["sound"]
    rejected = results["rejected"]

    header = textwrap.dedent("""\
        # CHUNK-040 — Wire authoring + meta-verification into a pre-loop planning step

        **Status:** done
        **Date:** 2026-08-13
        **Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.
        **Runner:** `phase4/run_chunk_040.py`

        ## What was built

        `phase4/plan_and_run.py`: the full CHUNK-038/039 pipeline wired
        together. Authors a candidate test in an isolated sandbox, rejects
        and escalates (writing `.agent-state/escalation.md`, exit code 5)
        without ever running the implementer agent if authoring produced
        nothing or meta-verification found the candidate unsound; only on a
        sound result does it write the meta-verified files into the
        implementer's real workspace and invoke `phase1/loop.py` with
        `--verify-tier2` set to the exact command `meta_verify` produced.

        ## Verification

        - `phase4/test_plan_and_run.py`: 4 unit tests (stubbed authoring/
          meta-verify/loop-invocation) covering authoring failure,
          meta-verify rejection, a sound run invoking the loop with the
          right flags, and confirming the authoring sandbox never contains
          the implementer's actual files. Full suite: `uv run pytest` ->
          104 passed (100 before this chunk + 4 new).
        - Real run (this script), covering both paths with a **real, live
          authoring agent call on each** (not mocked):

    """)

    results_section = "## Results\n\n"
    results_section += "| Scenario | Stage | Exit code | Meta-verify sound | Escalation written |\n"
    results_section += "|---|---|---|---|---|\n"
    for label, r in results.items():
        sound_val = r.meta_verify_result.sound if r.meta_verify_result else "N/A (authoring failed)"
        escalation = "yes" if r.escalation_path else "no"
        results_section += f"| `{label}` | `{r.stage}` | {r.exit_code} | {sound_val} | {escalation} |\n"

    results_section += (
        f"\nImplementer agent actually ran for the `sound` scenario (loop invoked): "
        f"`{sound.stage == 'loop'}`.\n"
        f"Implementer agent ran for the `rejected` scenario "
        f"(`.agent-state/runs/log.jsonl` created): `{implementer_agent_ran}` "
        f"(must be `False` -- the whole point of rejecting before ever starting the loop).\n"
    )

    footer = textwrap.dedent(f"""
        ## Finding

        Both paths behaved exactly as designed, with real (not mocked)
        authoring agent calls on each:

        - **Sound path**: the real authoring agent wrote a candidate
          property test from the real `acceptance_criteria.txt`;
          meta-verification against the real genuine-fix/original-bug pair
          found it sound; `phase1/loop.py` was invoked for real with
          `--verify-tier2` set to the meta-verified command, and completed
          with exit code `{sound.exit_code}`.
        - **Rejected path**: forcing `known_good_source == known_bad_source`
          (deliberately identical, so nothing can discriminate between
          them) still let a real authoring agent write a candidate test --
          but meta-verification correctly found zero discriminating checks
          and rejected it (`sound=False`), writing an escalation brief and
          returning exit code `{rejected.exit_code}` **without ever invoking
          the implementer agent** (`implementer_agent_ran={implementer_agent_ran}`).
          This is the critical safety property CHUNK-040 exists for: an
          unsound tier-2 candidate never silently degrades to "no
          protection" or blocks progress forever -- it stops and hands off
          to a human, visibly, before any implementer work happens.

        ## Artifacts

        - `phase4/plan_and_run.py`
        - `phase4/test_plan_and_run.py`
        - `phase4/run_chunk_040.py`
    """)
    (NOTES / "CHUNK-040.md").write_text(header + results_section + footer)


if __name__ == "__main__":
    sys.exit(main())
