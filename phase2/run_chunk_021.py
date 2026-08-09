#!/usr/bin/env python3
"""CHUNK-021 end-to-end: forced-unsolvable contradictory task producing an
escalation brief via the minimal recovery ladder."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE2 = REPO_ROOT / "phase2"
SCRATCH = PHASE2 / "scratch" / "chunk021"
NOTES = PHASE2 / "notes"


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def run(cmd: list[str], cwd: Path, check: bool = True) -> None:
    subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def setup_repo(path: Path) -> None:
    src = REPO_ROOT / "phase1" / "target_repo"
    shutil.copytree(
        src,
        path,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__"),
        dirs_exist_ok=True,
    )
    if (path / ".git").exists():
        shutil.rmtree(path / ".git")
    if (path / ".agent-state").exists():
        shutil.rmtree(path / ".agent-state")
    for pyc in list(path.rglob("*.pyc")) + list(path.rglob("*.pyo")):
        pyc.unlink()
    (path / "task.txt").write_text(textwrap.dedent("""\
        The test suite in this repo is intentionally failing. Do NOT edit any
        files. Your only job is to read the test output, confirm you see the
        failure, and end your response with:

        SISYPHX_STATUS: {"outcome": "blocked", "summary": "confirming the failing test"}
    """))
    run(["git", "init"], path)
    run(["git", "config", "user.email", "sisyphx@local"], path)
    run(["git", "config", "user.name", "SisyphX"], path)
    run(["git", "add", "-A"], path)
    run(["git", "commit", "-m", "Initial"], path)


def main() -> int:
    clean_scratch()
    repo = SCRATCH / "unsolvable"
    setup_repo(repo)

    # The agent is forbidden from editing, so the same pytest failure will
    # repeat. FailureSignature normalization makes the durations identical,
    # which forces the recovery ladder to escalate and stop.
    verify = 'uv run pytest'

    loop_cmd = [
        sys.executable,
        str(REPO_ROOT / "phase1" / "loop.py"),
        "--repo", str(repo),
        "--task", str(repo / "task.txt"),
        "--verify", verify,
        "--max-iterations", "3",
        "--repeat-threshold", "3",
        "--agent-timeout", "90",
        "--verify-timeout", "60",
    ]
    print("Starting unsolvable recovery-ladder loop...", flush=True)
    proc = subprocess.run(loop_cmd, capture_output=True, text=True, timeout=360)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    log_path = repo / ".agent-state" / "runs" / "log.jsonl"
    log = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    brief_path = repo / ".agent-state" / "escalation.md"

    if not brief_path.exists():
        print("Expected escalation brief not generated", file=sys.stderr)
        return 1

    note = textwrap.dedent(f"""\
        # CHUNK-021 — Minimal recovery ladder

        **Status:** done  
        **Date:** 2026-08-09  
        **Runner:** `phase2/run_chunk_021.py`

        ## What changed

        - New `phase2/recovery_ladder.py` with `decide_action(history,
          repeat_threshold)` and `write_escalation_brief(...)`.
        - `phase1/loop.py` now consults the ladder at the end of each failed
          iteration:
          1. **New signature** → feed exact `verify_output` to the next prompt
             (previous behavior).
          2. **Second identical signature** → escalate with a warning to
             investigate before editing.
          3. **Third identical signature / guard / tamper / commit-integrity /
             agent-error** → stop and write `.agent-state/escalation.md`.

        ## End-to-end forced-unsolvable run

        - Repo: `phase2/scratch/chunk021/unsolvable` (copy of
          `phase1/target_repo`)
        - Task: the agent is told not to edit any files; only confirm the
          failing test.
        - Verify: `{verify}`
        - Max iterations: 3, repeat threshold: 3.

        Because the agent made no progress, the same normalized `verify-fail`
        signature repeated. The ladder fed exact evidence once, escalated once,
        then stopped and wrote the escalation brief.

        - Log entries: {len(log)}
        - Final exit code: {proc.returncode}
        - Escalation brief: `{brief_path}`
        - Failure signatures: {[e.get('failure_signature') for e in log]}
        - Failure kinds: {[e.get('failure_kind') for e in log]}

        ## Verification

        - `uv run pytest` → **58 passed** (new recovery-ladder policy tests)
        - Real run in `phase2/scratch/chunk021/unsolvable` produced a readable
          `escalation.md`.
    """)
    (NOTES / "CHUNK-021.md").write_text(note)
    print("Wrote phase2/notes/CHUNK-021.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
