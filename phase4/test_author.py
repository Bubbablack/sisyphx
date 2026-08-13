"""CHUNK-038 -- test-authoring step, per CHUNK-037's contract.

Promotes CHUNK-035's throwaway spike script into a real, reusable,
config-driven module: given a repo containing only an acceptance-criteria
file (no implementation, no existing tests -- the caller is responsible
for that isolation, same as CHUNK-035's spike), invoke one bounded,
non-interactive Devin CLI turn (per `phase0/DEVIN_CLI_CONTRACT.md`) asking
a live agent to author a candidate property-test file.

Not hardcoded to the CHUNK-034 fixture: the acceptance-criteria file path,
the expected output filename, and the timeout are all caller-supplied.

This module only authors the candidate test. It does not decide whether to
trust it -- that is `phase4/meta_verify.py` (CHUNK-039).
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

STATUS_SUFFIX = (
    '\n\nWhen you are finished (whether fully successful, partially '
    'successful, or blocked), end your response with exactly one line in '
    'this exact format: SISYPHX_STATUS: {"outcome": "done|blocked|partial", '
    '"summary": "<one short sentence>"}. Use "done" only if fully '
    'successful, "blocked" if you could not proceed at all, "partial" if you '
    'made some progress but did not finish.'
)

_STATUS_LINE = re.compile(r"^[ \t]*SISYPHX_STATUS:[ \t]*(?P<rest>.+?)[ \t]*$", re.MULTILINE)

DEFAULT_AUTHORING_TIMEOUT_SECONDS = 240


def parse_status(stdout: str) -> str | None:
    """Extract the last SISYPHX_STATUS line as raw text, or None. Never
    raises -- mirrors `phase1/loop.py::parse_status`'s tolerance for
    formatting drift, but this module only needs the raw line (the
    authoring step's own acceptance is "was a test file written", not the
    agent's self-report)."""
    matches = _STATUS_LINE.findall(stdout or "")
    return matches[-1].strip() if matches else None


@dataclass(frozen=True)
class AuthoringResult:
    agent_exit_code: int
    agent_timed_out: bool
    status: str | None
    test_written: bool
    test_path: Path
    test_source: str          # "" if test_written is False
    agent_stdout: str
    agent_stderr: str


def _run_devin(repo: Path, prompt_text: str, timeout: int) -> tuple[int, bool, str, str]:
    """One bounded, non-interactive Devin CLI turn, per
    `phase0/DEVIN_CLI_CONTRACT.md`: `--permission-mode bypass`, `-p
    --prompt-file`, no `-c`/`-r` (fresh session), graceful
    SIGTERM->SIGKILL on timeout. Same convention as
    `phase1/loop.py::run_devin` and CHUNK-035's spike script."""
    prompt_path = repo / "_authoring_prompt.txt"
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


def author_property_test(
    repo: Path,
    acceptance_criteria_path: Path,
    test_filename: str,
    timeout: int = DEFAULT_AUTHORING_TIMEOUT_SECONDS,
) -> AuthoringResult:
    """Ask a live agent to author a property test.

    `repo` must contain only the acceptance-criteria file (and nothing that
    would let the agent peek at an implementation or existing tests --
    enforcing that isolation is the caller's responsibility, same as
    CHUNK-035's spike). `acceptance_criteria_path` is read verbatim as the
    prompt body; `test_filename` is the file this function checks for
    afterward (the acceptance-criteria text should ask the agent to write
    exactly that filename, as every acceptance-criteria file in this
    project already does).
    """
    task_text = acceptance_criteria_path.read_text()
    prompt_text = task_text.strip() + STATUS_SUFFIX

    exit_code, timed_out, stdout, stderr = _run_devin(repo, prompt_text, timeout)
    status = parse_status(stdout)

    test_path = repo / test_filename
    test_written = test_path.exists()
    test_source = test_path.read_text() if test_written else ""

    return AuthoringResult(
        agent_exit_code=exit_code,
        agent_timed_out=timed_out,
        status=status,
        test_written=test_written,
        test_path=test_path,
        test_source=test_source,
        agent_stdout=stdout,
        agent_stderr=stderr,
    )
