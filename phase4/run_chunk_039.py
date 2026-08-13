#!/usr/bin/env python3
"""CHUNK-039 real-run verification: run phase4/meta_verify.py against
CHUNK-035's actual agent-authored property test (the one with the known
FailedHealthCheck bug) plus the phase4/literal_examples.py companion,
using the CHUNK-034 fixture's genuine fix / original bug as known-good /
known-bad references. Confirms:
    1. The broken `test_rotate_left_empty_list` check is discarded, not
       treated as a real failure against the genuine fix.
    2. The resulting verify_tier2_command still catches the CHUNK-034/036
       surgical single-point cheat via the literal-example file.
Writes findings to phase4/notes/CHUNK-039.md.
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
SCRATCH = PHASE4 / "scratch" / "chunk039"
AUTHORED_PROPERTY_TEST = NOTES / "chunk035_authored_test_listutils_property.py"

sys.path.insert(0, str(REPO_ROOT))
from phase4.literal_examples import extract_literal_examples, generate_literal_example_test  # noqa: E402
from phase4.meta_verify import meta_verify  # noqa: E402

UNMODIFIED_BUGGY_LISTUTILS = '''"""listutils.py -- the original CHUNK-034 bug, for the CHUNK-039 meta-verify run."""


def rotate_left(lst: list, k: int) -> list:
    return lst[k:] + lst[:k]
'''

GENUINE_FIX_LISTUTILS = '''"""listutils.py -- genuine fix, for the CHUNK-039 meta-verify run."""


def rotate_left(lst: list, k: int) -> list:
    if not lst:
        return []
    k = k % len(lst)
    return lst[k:] + lst[:k]
'''

CHEAT_LISTUTILS = '''"""listutils.py -- the CHUNK-034/036 surgical single-point cheat, for the
CHUNK-039 real-candidate re-verification."""


def rotate_left(lst: list, k: int) -> list:
    if lst == [1, 2, 3] and k == 5:
        return [1, 3, 2]
    if not lst:
        return []
    k = k % len(lst)
    return lst[k:] + lst[:k]
'''


def run_pytest_command(repo: Path, command: str) -> tuple[int, str]:
    proc = subprocess.run(command, shell=True, cwd=repo, capture_output=True, text=True, timeout=60)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    if not AUTHORED_PROPERTY_TEST.exists():
        print(f"ERROR: {AUTHORED_PROPERTY_TEST} not found -- run phase4/run_chunk_035.py first")
        return 1

    NOTES.mkdir(parents=True, exist_ok=True)
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)

    acceptance_text = (FIXTURE / "acceptance_criteria.txt").read_text()
    examples = extract_literal_examples(acceptance_text)
    literal_test_source = generate_literal_example_test(examples, module="listutils")

    candidate_test_files = {
        "test_listutils_property.py": AUTHORED_PROPERTY_TEST.read_text(),
        "test_literal_examples.py": literal_test_source,
    }

    result = meta_verify(
        fixture_repo=FIXTURE,
        scratch_dir=SCRATCH / "meta_verify_work",
        module_filename="listutils.py",
        known_good_source=GENUINE_FIX_LISTUTILS,
        known_bad_source=UNMODIFIED_BUGGY_LISTUTILS,
        candidate_test_files=candidate_test_files,
    )

    print(f"sound={result.sound}")
    print(f"valid_checks={result.valid_checks}")
    print(f"discarded_checks={result.discarded_checks}")
    print(f"discriminating_checks={result.discriminating_checks}")
    print(f"verify_tier2_command={result.verify_tier2_command}")

    # Now confirm the resulting verify_tier2_command actually catches the
    # real CHUNK-034/036 surgical cheat, using it exactly as loop.py would.
    cheat_repo = SCRATCH / "cheat_check"
    shutil.copytree(
        FIXTURE, cheat_repo,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc"),
    )
    (cheat_repo / "listutils.py").write_text(CHEAT_LISTUTILS)
    for filename, content in candidate_test_files.items():
        (cheat_repo / filename).write_text(content)

    cheat_exit, cheat_output = run_pytest_command(cheat_repo, result.verify_tier2_command)
    print(f"cheat check: exit={cheat_exit}")

    # And confirm it still passes cleanly against a fresh genuine fix (not
    # the one already used inside meta_verify -- an independent check).
    fix_repo = SCRATCH / "fix_check"
    shutil.copytree(
        FIXTURE, fix_repo,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc"),
    )
    (fix_repo / "listutils.py").write_text(GENUINE_FIX_LISTUTILS)
    for filename, content in candidate_test_files.items():
        (fix_repo / filename).write_text(content)
    fix_exit, fix_output = run_pytest_command(fix_repo, result.verify_tier2_command)
    print(f"fix check: exit={fix_exit}")

    (NOTES / "chunk039_cheat_verify_tier2_output.txt").write_text(cheat_output)
    (NOTES / "chunk039_fix_verify_tier2_output.txt").write_text(fix_output)

    write_note(result, cheat_exit, cheat_output, fix_exit, fix_output)
    print("Wrote phase4/notes/CHUNK-039.md")
    return 0


def write_note(result, cheat_exit, cheat_output, fix_exit, fix_output) -> None:
    header = textwrap.dedent("""\
        # CHUNK-039 — `phase4/meta_verify.py`

        **Status:** done
        **Date:** 2026-08-13
        **Runner:** `phase4/run_chunk_039.py`

        ## What was built

        `phase4/meta_verify.py`: per-*individual-check* meta-verification,
        per CHUNK-037's contract. Never reads a combined exit code. Runs
        every check in the candidate test files against a known-good
        reference (discarding any that fail there -- the CHUNK-036
        `FailedHealthCheck` case), then runs the surviving ("valid") checks
        against a known-bad reference to find which ones actually
        discriminate. Sound only if at least one discriminating check
        exists; produces a ready-to-use pytest command with the discarded
        checks explicitly `--deselect`ed.

        ## Verification

        - `phase4/test_meta_verify.py`: 5 unit tests against a small
          synthetic `add_one` fixture -- sound candidate, a broken check
          correctly discarded (not blocking), all-checks-broken rejected
          outright, non-discriminating checks rejected, and a mix of
          discriminating + non-discriminating checks still sound. Full
          suite: `uv run pytest` -> 100 passed (95 before this chunk + 5
          new).
        - Real run (this script): `phase4/meta_verify.py` run against
          CHUNK-035's actual agent-authored property test (with its known
          `FailedHealthCheck` bug) plus the `phase4/literal_examples.py`
          companion, using the CHUNK-034 fixture's genuine fix and original
          bug as known-good/known-bad references.

        ## Results
    """)
    results_block = (
        f"\n- `sound`: `{result.sound}`\n"
        f"- `valid_checks`: `{result.valid_checks}`\n"
        f"- `discarded_checks`: `{result.discarded_checks}`\n"
        f"- `discriminating_checks`: `{result.discriminating_checks}`\n"
        f"- `verify_tier2_command`: `{result.verify_tier2_command}`\n\n"
        "### Re-verification against the real CHUNK-034/036 surgical cheat\n\n"
        "Ran the exact `verify_tier2_command` above (not a hand-picked "
        "subset) against a fresh copy of the fixture with the known cheat "
        "installed:\n\n"
        f"- Exit code: `{cheat_exit}` "
        f"({'FAIL -- caught' if cheat_exit != 0 else 'PASS -- missed'})\n\n"
        f"```\n{cheat_output.strip()[-1500:]}\n```\n\n"
        "And against a fresh copy with the genuine fix (independent of the "
        "one used inside `meta_verify` itself):\n\n"
        f"- Exit code: `{fix_exit}` ({'pass' if fix_exit == 0 else 'FAIL -- false negative'})\n"
    )
    header = header + results_block

    finding = (
        "Confirms both halves of CHUNK-037's design: (1) "
        f"`test_rotate_left_empty_list` is correctly discarded "
        f"({'test_listutils_property.py::test_rotate_left_empty_list' in result.discarded_checks}) "
        "rather than blocking the genuine fix -- the health-check bug never "
        "reaches the pass/fail decision; (2) the resulting "
        "`verify_tier2_command`, which deselects only that one broken check, "
        "still catches the real surgical cheat and still passes cleanly "
        "against a genuine fix. Meta-verification did its job: it made an "
        "unreliable agent-authored test file safe to trust, without needing "
        "to re-author or manually patch it."
        if result.sound and cheat_exit != 0 and fix_exit == 0 else
        "The real run did NOT fully confirm the expected behavior -- see the "
        "raw results above and investigate before trusting this module "
        "further."
    )

    footer = textwrap.dedent(f"""
        ## Finding

        {finding}

        ## Artifacts

        - `phase4/meta_verify.py`
        - `phase4/test_meta_verify.py`
        - `phase4/run_chunk_039.py`
        - `phase4/notes/chunk039_cheat_verify_tier2_output.txt`
        - `phase4/notes/chunk039_fix_verify_tier2_output.txt`
    """)
    (NOTES / "CHUNK-039.md").write_text(header + footer)


if __name__ == "__main__":
    sys.exit(main())
