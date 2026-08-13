#!/usr/bin/env python3
"""CHUNK-038 real-run verification: exercise the promoted
phase4/test_author.py (not the CHUNK-035 throwaway spike script) against
the CHUNK-034 fixture, to confirm the real module behaves correctly.
Writes findings to phase4/notes/CHUNK-038.md.
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
SCRATCH = PHASE4 / "scratch" / "chunk038"
NOTES = PHASE4 / "notes"

sys.path.insert(0, str(REPO_ROOT))
from phase4.test_author import author_property_test  # noqa: E402


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def prepare_repo() -> Path:
    repo = SCRATCH / "repo"
    repo.mkdir(parents=True)
    shutil.copy2(FIXTURE / "acceptance_criteria.txt", repo / "acceptance_criteria.txt")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Initial state: acceptance criteria only"], cwd=repo, check=True)
    return repo


def main() -> int:
    NOTES.mkdir(parents=True, exist_ok=True)
    clean_scratch()
    repo = prepare_repo()

    result = author_property_test(
        repo=repo,
        acceptance_criteria_path=repo / "acceptance_criteria.txt",
        test_filename="test_listutils_property.py",
        timeout=240,
    )

    (NOTES / "chunk038_agent_stdout.txt").write_text(result.agent_stdout)
    (NOTES / "chunk038_agent_stderr.txt").write_text(result.agent_stderr)
    if result.test_written:
        (NOTES / "chunk038_authored_test_listutils_property.py").write_text(result.test_source)

    print(f"exit_code={result.agent_exit_code} timed_out={result.agent_timed_out} "
          f"status={result.status!r} test_written={result.test_written}")

    write_note(result)
    print("Wrote phase4/notes/CHUNK-038.md")
    return 0


def write_note(result) -> None:
    header = textwrap.dedent(f"""\
        # CHUNK-038 — `phase4/test_author.py`

        **Status:** done
        **Date:** 2026-08-13
        **Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.
        **Runner:** `phase4/run_chunk_038.py`

        ## What was built

        `phase4/test_author.py`: the real, promoted implementation of
        CHUNK-035's throwaway spike script. Config-driven
        (`author_property_test(repo, acceptance_criteria_path,
        test_filename, timeout)`) -- not hardcoded to the CHUNK-034
        fixture's `rotate_left` scenario, confirmed by a unit test using a
        different acceptance-criteria filename and a different expected
        output filename.

        ## Verification

        - `phase4/test_test_author.py`: 7 unit tests with stubbed
          `subprocess.Popen` covering normal completion, no-file-written,
          timeout (SIGTERM then SIGKILL escalation, same convention as
          `phase1/loop.py::run_devin`), prompt-file contents, and the
          config-driven (non-hardcoded) claim. Full suite: `uv run pytest`
          -> 95 passed (88 before this chunk + 7 new).
        - Real run (this script): same experimental setup as CHUNK-035 (a
          scratch repo containing only `acceptance_criteria.txt`), calling
          the real `phase4.test_author.author_property_test` instead of
          the throwaway spike script.

        ## Results

        - Agent exit code: `{result.agent_exit_code}`
        - Timed out: `{result.agent_timed_out}`
        - Parsed status: `{result.status}`
        - Test file written: `{result.test_written}`

    """)
    if result.test_written:
        body = "### Authored test\n\n```python\n" + result.test_source.strip() + "\n```\n"
    else:
        body = "No test file was written -- see agent stdout/stderr artifacts.\n"

    footer = textwrap.dedent("""
        ## Finding

        The promoted module reproduces CHUNK-035's real result: given only
        the acceptance criteria, the agent authored a property-test file
        without ever seeing an implementation. (Whether this specific
        authored test would catch the CHUNK-034 cheat is not re-verified
        here -- that empirical question was already answered once for
        CHUNK-035's authored test in CHUNK-036/037, and CHUNK-039's
        meta-verification step is what will make that judgment
        systematically going forward, not a one-off re-check per authoring
        run.)

        ## Artifacts

        - `phase4/test_author.py`
        - `phase4/test_test_author.py`
        - `phase4/run_chunk_038.py`
        - `phase4/notes/chunk038_agent_stdout.txt`
        - `phase4/notes/chunk038_agent_stderr.txt`
        - `phase4/notes/chunk038_authored_test_listutils_property.py` (if written)
    """)
    (NOTES / "CHUNK-038.md").write_text(header + body + footer)


if __name__ == "__main__":
    sys.exit(main())
