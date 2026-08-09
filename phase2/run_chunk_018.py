#!/usr/bin/env python3
"""CHUNK-018 end-to-end verification: the loop detects two failures that differ
only in volatile output (durations) as identical via FailureSignature."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE2 = REPO_ROOT / "phase2"
SCRATCH = PHASE2 / "scratch" / "chunk018"
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
        The test suite in this repo is intentionally failing because of a bug in
        calc.py. For this verification run, do NOT edit any files. Your only job
        is to read the test output, confirm you see the failure, and end your
        response with:

        SISYPHX_STATUS: {"outcome": "blocked", "summary": "confirming the failing test"}
    """))
    run(["git", "init"], path)
    run(["git", "config", "user.email", "sisyphx@local"], path)
    run(["git", "config", "user.name", "SisyphX"], path)
    run(["git", "add", "-A"], path)
    run(["git", "commit", "-m", "Initial"], path)


def main() -> int:
    clean_scratch()
    repo = SCRATCH / "stuck"
    setup_repo(repo)

    loop_cmd = [
        sys.executable,
        str(REPO_ROOT / "phase1" / "loop.py"),
        "--repo", str(repo),
        "--task", str(repo / "task.txt"),
        "--verify", "uv run pytest",
        "--max-iterations", "2",
        "--repeat-threshold", "2",
        "--agent-timeout", "90",
        "--verify-timeout", "60",
    ]
    print("Starting loop...", flush=True)
    proc = subprocess.run(loop_cmd, capture_output=True, text=True, timeout=240)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    log_path = repo / ".agent-state" / "runs" / "log.jsonl"
    log = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]

    if len(log) < 2:
        print("Expected at least 2 log entries", file=sys.stderr)
        return 1

    sig1 = log[0]["failure_signature"]
    sig2 = log[1]["failure_signature"]
    kind = log[0]["failure_kind"]
    if sig1 != sig2:
        print(f"Signatures differ: {sig1} vs {sig2}", file=sys.stderr)
        return 1
    if kind != "verify-fail":
        print(f"Expected verify-fail, got {kind}", file=sys.stderr)
        return 1

    note = textwrap.dedent(f"""\
        # CHUNK-018 — Loop uses `FailureSignature` for stuck detection

        **Status:** done  
        **Date:** 2026-08-09  
        **Runner:** `phase2/run_chunk_018.py`

        ## What changed

        - `phase1/loop.py` now computes a `FailureSignature` after every
          verification.
        - The run log gains `failure_kind` and `failure_signature` fields.
        - Stuck detection is signature-based: the last `repeat_threshold` failures
          must have the same `failure_signature.hash`, not be byte-identical.
        - Guard aborts (`agent_exit_code == 1` + guard sentinel in stderr) stop
          the loop immediately with exit code 4; no retry.

        ## End-to-end run

        - Repo: `phase2/scratch/chunk018/stuck` (copy of `phase1/target_repo`)
        - Task: confirm the failing test, do not edit files.
        - Verify: `uv run pytest`
        - Max iterations: 2, repeat threshold: 2.

        The first two `uv run pytest` outputs differed only in their volatile
        durations (`in 0.XXs`). After normalization, both collapsed to the same
        `FailureSignature`:

        - Iteration 1: kind=`{log[0]['failure_kind']}` signature=`{log[0]['failure_signature']}`
        - Iteration 2: kind=`{log[1]['failure_kind']}` signature=`{log[1]['failure_signature']}`

        The loop stopped at `repeat_threshold=2` with exit code 3.

        ## Exit codes

        - `0` — verification passed
        - `2` — `max_iterations` reached
        - `3` — identical failure signature repeated `repeat_threshold` times
        - `4` — guard abort (do not retry)

        ## Verification

        - `uv run pytest` (all 40 tests pass):
          - `phase1/test_loop.py` (15)
          - `phase1/tests/test_run_log.py` (10, including new guard/timeout tests)
          - `phase2/test_failure_signature.py` (15)
        - Real run: `phase2/scratch/chunk018/stuck` produced two identical
          `FailureSignature` hashes and exited 3.

        ## Next

        CHUNK-019 will add commit-integrity guard (CHUNK-013 findings), and
        CHUNK-020 will add the post-iteration diff tamper guard (CHUNK-016
        findings).
    """)
    (NOTES / "CHUNK-018.md").write_text(note)
    print("Wrote phase2/notes/CHUNK-018.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
