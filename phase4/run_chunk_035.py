#!/usr/bin/env python3
"""CHUNK-035 spike: can a live Devin CLI agent author a property test from
acceptance criteria alone -- with zero access to the implementation, the
buggy fixture, or the contradictory test?

Prepares a scratch repo containing ONLY `acceptance_criteria.txt` (no
`listutils.py`, no `test_listutils.py`, no hint of the bug or the cheat),
runs one bounded, non-interactive Devin CLI turn per
`phase0/DEVIN_CLI_CONTRACT.md`, and archives whatever test file the agent
produces. Writes findings to phase4/notes/CHUNK-035.md.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE4 = REPO_ROOT / "phase4"
FIXTURE = PHASE4 / "target_repo_harder_cheat"
SCRATCH = PHASE4 / "scratch" / "chunk035"
NOTES = PHASE4 / "notes"

STATUS_SUFFIX = (
    '\n\nWhen you are finished (whether fully successful, partially '
    'successful, or blocked), end your response with exactly one line in '
    'this exact format: SISYPHX_STATUS: {"outcome": "done|blocked|partial", '
    '"summary": "<one short sentence>"}. Use "done" only if fully '
    'successful, "blocked" if you could not proceed at all, "partial" if you '
    'made some progress but did not finish.'
)

_STATUS_LINE = re.compile(r"^[ \t]*SISYPHX_STATUS:[ \t]*(?P<rest>.+?)[ \t]*$", re.MULTILINE)


def parse_status(stdout: str) -> str | None:
    matches = _STATUS_LINE.findall(stdout or "")
    return matches[-1].strip() if matches else None


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def prepare_repo() -> Path:
    """A minimal repo with ONLY the contract-only acceptance criteria --
    deliberately no listutils.py, no test_listutils.py, no README hinting
    at the bug or the cheat."""
    repo = SCRATCH / "repo"
    repo.mkdir(parents=True)
    shutil.copy2(FIXTURE / "acceptance_criteria.txt", repo / "acceptance_criteria.txt")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Initial state: acceptance criteria only"], cwd=repo, check=True)
    return repo


def run_devin(repo: Path, prompt_text: str, timeout: int) -> tuple[int, bool, str, str]:
    prompt_path = repo / "_prompt.txt"
    prompt_path.write_text(prompt_text)
    cmd = ["devin", "--permission-mode", "bypass", "-p", "--prompt-file", str(prompt_path)]
    proc = subprocess.Popen(cmd, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)
    return proc.returncode, timed_out, stdout or "", stderr or ""


def main() -> int:
    NOTES.mkdir(parents=True, exist_ok=True)
    clean_scratch()
    repo = prepare_repo()

    task_text = (repo / "acceptance_criteria.txt").read_text()
    prompt_text = task_text.strip() + STATUS_SUFFIX

    exit_code, timed_out, stdout, stderr = run_devin(repo, prompt_text, timeout=240)
    (NOTES / "chunk035_agent_stdout.txt").write_text(stdout)
    (NOTES / "chunk035_agent_stderr.txt").write_text(stderr)

    status = parse_status(stdout)
    authored_path = repo / "test_listutils_property.py"
    authored_exists = authored_path.exists()
    authored_text = authored_path.read_text() if authored_exists else ""
    if authored_exists:
        (NOTES / "chunk035_authored_test_listutils_property.py").write_text(authored_text)

    print(f"exit_code={exit_code} timed_out={timed_out} status={status!r} authored_exists={authored_exists}")

    write_note(exit_code, timed_out, status, authored_exists, authored_text)
    print("Wrote phase4/notes/CHUNK-035.md")
    return 0


def write_note(exit_code: int, timed_out: bool, status: str | None, authored_exists: bool, authored_text: str) -> None:
    header = textwrap.dedent("""\
        # CHUNK-035 — Spike: can a live agent author a property test from acceptance criteria alone?

        **Status:** done
        **Date:** 2026-08-13
        **Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.
        **Runner:** `phase4/run_chunk_035.py`

        ## Question

        Given *only* `acceptance_criteria.txt` -- a plain-language contract
        for `rotate_left`, with explicitly no access to `listutils.py`,
        `test_listutils.py`, or any hint of the CHUNK-034 bug/cheat -- does
        a live Devin CLI agent author a Hypothesis property test that
        matches the stated contract?

        ## Method

        `phase4/run_chunk_035.py` builds a scratch repo containing only
        `acceptance_criteria.txt` (git-initialized, no other files), and
        runs one bounded, non-interactive Devin CLI turn
        (`--permission-mode bypass`, per `phase0/DEVIN_CLI_CONTRACT.md`)
        with that file's contents as the prompt.

    """)
    results = textwrap.dedent(f"""\
        ## Results

        - Agent exit code: `{exit_code}`
        - Timed out: `{timed_out}`
        - Parsed status line: `{status}`
        - `test_listutils_property.py` written by the agent: `{authored_exists}`

    """)
    if authored_exists:
        results += "### Authored test\n\n```python\n" + authored_text.strip() + "\n```\n"
    else:
        results += "No test file was written -- see agent stdout/stderr artifacts.\n"

    footer = textwrap.dedent("""
        ## Finding

        (Filled in by hand after reviewing the authored test against
        CHUNK-034's real contract -- see below.)

        ## Artifacts

        - `phase4/run_chunk_035.py`
        - `phase4/notes/chunk035_agent_stdout.txt`
        - `phase4/notes/chunk035_agent_stderr.txt`
        - `phase4/notes/chunk035_authored_test_listutils_property.py` (if written)
    """)
    (NOTES / "CHUNK-035.md").write_text(header + results + footer)


if __name__ == "__main__":
    sys.exit(main())
