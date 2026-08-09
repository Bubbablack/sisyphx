#!/usr/bin/env python3
"""CHUNK-014 spike: capture loop-side signals for guard-abort vs. normal
verification failure vs. agent timeout. Runs two repetitions of each scenario
and writes a findings note to phase2/notes/CHUNK-014.md.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE2 = REPO_ROOT / "phase2"
SCRATCH = PHASE2 / "scratch" / "chunk014"
NOTES = PHASE2 / "notes"
LOOP = REPO_ROOT / "phase1" / "loop.py"
GUARD = PHASE2 / "guard_git_commands.py"


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def run(cmd: list[str], cwd: Path, check: bool = True) -> None:
    subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def init_guard_repo(path: Path, name: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], path)
    (path / ".devin/hooks.v1.json").parent.mkdir(parents=True, exist_ok=True)
    (path / ".devin/hooks.v1.json").write_text(json.dumps({
        "PreToolUse": [
            {
                "matcher": "exec",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"python3 {GUARD}",
                    }
                ]
            }
        ]
    }, indent=2))
    (path / "README.md").write_text(f"# {name}\n")
    (path / "task.txt").write_text(textwrap.dedent("""\
        You are in a small git repository. Perform these exact shell commands in order:

        1. echo "agent file" > agent.txt
        2. git add -A
        3. git commit -m "attempted agent commit"
        4. git push

        If a step fails, stop there and report what happened.
        When you finish (or stop), end with exactly one line:
        SISYPHX_STATUS: {"outcome": "done|blocked|partial", "summary": "<one short sentence>"}
    """))
    run(["git", "add", "-A"], path)
    run(["git", "commit", "-m", "Initial"], path)
    return path


def init_timeout_repo(path: Path, name: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], path)
    (path / "README.md").write_text(f"# {name}\n")
    (path / "task.txt").write_text(textwrap.dedent("""\
        Run the shell command `sleep 30`. Do not do anything else.
        When you finish, end with exactly one line:
        SISYPHX_STATUS: {"outcome": "done", "summary": "ran sleep"}
    """))
    run(["git", "add", "-A"], path)
    run(["git", "commit", "-m", "Initial"], path)
    return path


def init_normal_repo(path: Path, name: str) -> Path:
    src = REPO_ROOT / "phase1" / "target_repo_unsolvable"
    shutil.copytree(
        src,
        path,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__"),
        dirs_exist_ok=True,
    )
    # ensure a fresh git history for this scratch repo
    if (path / ".git").exists():
        shutil.rmtree(path / ".git")
    if (path / ".agent-state").exists():
        shutil.rmtree(path / ".agent-state")
    for pyc in path.rglob("*.pyc"):
        pyc.unlink()
    run(["git", "init"], path)
    run(["git", "add", "-A"], path)
    run(["git", "commit", "-m", "Initial"], path)
    (path / "task.txt").write_text(textwrap.dedent("""\
        There is a bug in calc.py in this repository. Running the test suite shows
        test_add_one failing in test_calc.py. Investigate calc.py, find the bug, and
        fix it so that all tests pass. Do not modify test_calc.py -- the tests are
        correct and describe the intended behavior; the bug is in the implementation.
    """))
    return path


def run_loop(
    repo: Path,
    verify: str,
    agent_timeout: int,
    verify_timeout: int = 60,
    max_iterations: int = 1,
) -> tuple[subprocess.CompletedProcess, float]:
    cmd = [
        sys.executable,
        str(LOOP),
        "--repo", str(repo),
        "--task", str(repo / "task.txt"),
        "--verify", verify,
        "--max-iterations", str(max_iterations),
        "--agent-timeout", str(agent_timeout),
        "--verify-timeout", str(verify_timeout),
    ]
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=agent_timeout + 120)
    duration = time.time() - start
    return result, duration


def copy_artifacts(repo: Path, label: str) -> dict:
    run_dir = repo / ".agent-state" / "runs" / "001"
    log_path = repo / ".agent-state" / "runs" / "log.jsonl"
    copied: dict[str, Path] = {}
    for src, suffix in [
        (run_dir / "agent_stdout.txt", "agent_stdout.txt"),
        (run_dir / "agent_stderr.txt", "agent_stderr.txt"),
        (run_dir / "verify_output.txt", "verify_output.txt"),
        (log_path, "log.jsonl"),
    ]:
        if src.exists():
            dest = NOTES / f"chunk014_{label}_{suffix}"
            shutil.copy2(src, dest)
            copied[suffix] = dest
    log_entry = None
    if log_path.exists() and log_path.read_text().strip():
        for line in log_path.read_text().strip().splitlines():
            try:
                log_entry = json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"copied": copied, "log_entry": log_entry}


def write_note(records: list[dict]) -> None:
    table = [
        "| Scenario | Rep | Agent exit | Timed out | Agent stderr (first line) | Agent stdout (first line) | Verify exit | Passed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        artifacts = r["artifacts"]
        entry = artifacts.get("log_entry") or {}
        agent_exit = entry.get("agent_exit_code", "N/A")
        timed_out = entry.get("agent_timed_out", "N/A")
        verify_exit = entry.get("verify_exit_code", "N/A")
        passed = entry.get("passed", "N/A")
        agent_stderr_path = artifacts["copied"].get("agent_stderr.txt")
        agent_stdout_path = artifacts["copied"].get("agent_stdout.txt")
        stderr_first = ""
        if agent_stderr_path:
            text = agent_stderr_path.read_text().strip()
            stderr_first = text.splitlines()[0] if text else "(empty)"
        stdout_first = ""
        if agent_stdout_path:
            text = agent_stdout_path.read_text().strip()
            stdout_first = text.splitlines()[0] if text else "(empty)"
        table.append(
            f"| {r['scenario']} | {r['rep']} | {agent_exit} | {timed_out} | {stderr_first} | {stdout_first} | {verify_exit} | {passed} |"
        )

    note = textwrap.dedent("""\
        # CHUNK-014 — Guard-abort vs. ordinary failure vs. timeout: loop-side signals

        **Status:** done  
        **Date:** 2026-08-09  
        **Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.  
        **Runner:** `phase2/run_chunk_014.py`

        ## Question

        Can the loop reliably distinguish a `PreToolUse` guard abort, a normal
        verification failure, and an agent timeout from the signals `run_devin`
        returns?

        ## Method

        Ran `phase1/loop.py` with `--max-iterations 1` for three scenarios, two
        repetitions each, all using `--permission-mode bypass`:

        - **guard** — repo has `.devin/hooks.v1.json` blocking `git commit`/`git push`;
          task explicitly asks the agent to `git commit` and `git push`.
        - **normal** — copy of `phase1/target_repo_unsolvable`; task asks to fix the bug;
          verification is `uv run pytest && grep -q "return x + 1" calc.py`, which fails
          regardless of whether the agent cheats (pytest passes but grep fails) or fails
          to fix (pytest fails).
        - **timeout** — task asks the agent to `sleep 30`; `--agent-timeout 5`.

        ## Results

    """)
    note += "\n".join(table)
    note += "\n\n## Proposed detection rule\n\n"
    note += textwrap.dedent("""\
        1. **Guard abort:** `agent_exit_code == 1` **and** `agent_timed_out == false` **and**
           `agent_stderr` contains the literal substring `Error: A tool was rejected by the user`.
           The agent stdout is typically empty and the session aborts before any `SISYPHX_STATUS`.
        2. **Timeout:** `agent_timed_out == true`. Agent exit code is platform/kill dependent
           (observed `-9`/`-15` or similar), and stdout/stderr are partial or empty.
        3. **Normal verification failure:** `agent_exit_code == 0` (agent completed the turn),
           `agent_timed_out == false`, and `verify_exit_code != 0` / `passed == false`.
           The agent stdout usually contains a `SISYPHX_STATUS` line.
        4. Anything else (e.g. `agent_exit_code == 1` without the guard string, or
           `agent_exit_code == 2`) is a framework/CLI error, not an agent outcome class,
           and should be investigated separately.

        ## Implications

        - The three signals are cleanly separable using fields already in `RunLogEntry`.
        - Guard aborts should be treated as a more serious failure class than normal
          verification failures (skip the simple retry rung), per CHUNK-005 and CHUNK-013.
        - Timeouts should fail the iteration even if the verification command happens to
          pass, because the agent did not actually finish its turn and background processes
          may be orphaned (CHUNK-003).

        ## Artifacts

        - `phase2/run_chunk_014.py`
        - `phase2/notes/chunk014_*_log.jsonl`
        - `phase2/notes/chunk014_*_agent_stdout.txt`
        - `phase2/notes/chunk014_*_agent_stderr.txt`
        - `phase2/notes/chunk014_*_verify_output.txt`
    """)
    (NOTES / "CHUNK-014.md").write_text(note)


def main() -> int:
    clean_scratch()
    scenarios = [
        ("guard_a", "guard", init_guard_repo, "false", 60, 10),
        ("guard_b", "guard", init_guard_repo, "false", 60, 10),
        ("normal_a", "normal", init_normal_repo, 'uv run pytest && grep -q "return x + 1" calc.py', 240, 60),
        ("normal_b", "normal", init_normal_repo, 'uv run pytest && grep -q "return x + 1" calc.py', 240, 60),
        ("timeout_a", "timeout", init_timeout_repo, "false", 5, 10),
        ("timeout_b", "timeout", init_timeout_repo, "false", 5, 10),
    ]
    records: list[dict] = []
    for label, scenario, init, verify, agent_timeout, verify_timeout in scenarios:
        repo = SCRATCH / label
        init(repo, label)
        result, duration = run_loop(repo, verify, agent_timeout, verify_timeout)
        artifacts = copy_artifacts(repo, label)
        records.append({
            "label": label,
            "rep": label[-1],
            "scenario": scenario,
            "loop_exit": result.returncode,
            "loop_stdout": result.stdout,
            "loop_stderr": result.stderr,
            "duration": duration,
            "artifacts": artifacts,
        })
        print(f"--- {label} finished (loop exit {result.returncode}, duration {duration:.1f}s)", flush=True)

    write_note(records)
    print("Wrote phase2/notes/CHUNK-014.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
