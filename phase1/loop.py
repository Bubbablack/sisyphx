#!/usr/bin/env python3
"""SisyphX Phase 1 -- minimal Ralph-style loop.

Implements PLAN.md's Phase 1 (CHUNK-009/010/011) and now CHUNK-018,
following phase0/DEVIN_CLI_CONTRACT.md. Deliberately plain: subprocess + git
+ files. No Pydantic/SQLite/state machines yet -- those come in Phase 2+,
retrofitted around whatever this loop actually needed, once it's proven itself.

Core principle carried over from every Phase 0 finding: the agent's exit
code and its own self-report are NEVER trusted. Only the independently-run
verification command decides pass/fail, and now `FailureSignature` decides
"same failure again".

Usage:
    python3 loop.py --repo <path> --task <task_prompt_file> \\
        --verify "<shell command>" [--max-iterations 6] \\
        [--repeat-threshold 3] [--agent-timeout 240] [--verify-timeout 120]

Stop conditions (first one hit wins):
    - verification passes                              -> exit 0
    - the last `repeat_threshold` failures have the same
      `FailureSignature` (stuck, not making progress)   -> exit 3
    - a guard aborts the session                       -> exit 4
    - max_iterations reached without passing             -> exit 2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import TypedDict

LOOP_AUTHOR_NAME = "SisyphX Loop"
LOOP_AUTHOR_EMAIL = "loop@sisyphx.local"

# Ensure SisyphX repo root is on sys.path so phase2.failure_signature is
# importable regardless of where loop.py is invoked from.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from phase2.failure_signature import (
    GUARD_SENTINEL,
    FailureSignature,
    failure_signature,
)


# Run log schema (CHUNK-011). Each line of `.agent-state/runs/log.jsonl` is one
# of these. Fields are intentionally primitive so the log stays human-readable
# and parseable without Pydantic. A `None` value means the field was unavailable
# (e.g. the agent produced no parseable status line).
class RunLogEntry(TypedDict, total=False):
    iteration: int
    timestamp: str              # ISO-8601 UTC, e.g. "2026-08-08T17:07:41Z"
    agent_exit_code: int
    agent_timed_out: bool
    status: dict | None         # parsed SISYPHX_STATUS, if any
    verify_exit_code: int
    passed: bool
    failure_kind: str           # CHUNK-018: guard / agent-timeout / verify-timeout / verify-fail / verify-pass / agent-error
    failure_signature: str      # CHUNK-018: 16-char hash of the failure identity
    head_before: str            # CHUNK-019: HEAD before the agent ran
    head_after: str             # CHUNK-019: HEAD after the agent ran
    git_sha: str                # HEAD after the loop's own commit attempt
    committed: bool             # True if the loop itself staged+committed changes
    duration_seconds: float
    run_dir: str                # relative path from repo to this attempt's artifacts


# Stable ordering for human-readable log lines. Extra keys are preserved by
# json.dumps but this is the canonical field set.
LOG_FIELDS: tuple[str, ...] = (
    "iteration",
    "timestamp",
    "agent_exit_code",
    "agent_timed_out",
    "status",
    "verify_exit_code",
    "passed",
    "failure_kind",
    "failure_signature",
    "head_before",
    "head_after",
    "git_sha",
    "committed",
    "duration_seconds",
    "run_dir",
)

STATUS_SUFFIX = (
    '\n\nWhen you are finished (whether fully successful, partially '
    'successful, or blocked), end your response with exactly one line in '
    'this exact format: SISYPHX_STATUS: {"outcome": "done|blocked|partial", '
    '"summary": "<one short sentence>"}. Use "done" only if fully '
    'successful, "blocked" if you could not proceed at all, "partial" if you '
    'made some progress but did not finish.'
)

_STATUS_LINE = re.compile(r"^[ \t]*SISYPHX_STATUS:[ \t]*(?P<rest>.+?)[ \t]*$", re.MULTILINE)


def parse_status(stdout: str) -> dict | None:
    """Extract the last SISYPHX_STATUS line as a dict, or None. Never
    raises. See phase0/CHUNK-006 for the formatting-drift tolerance this
    needs (whitespace, backticks, bare words, malformed JSON)."""
    matches = _STATUS_LINE.findall(stdout or "")
    if not matches:
        return None
    raw = matches[-1].strip().strip("`").strip()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"outcome": raw}
    if isinstance(parsed, dict):
        parsed.setdefault("outcome", "unknown")
        return parsed
    return {"outcome": str(parsed)}


def build_prompt(task_text: str, previous_failure: str | None) -> str:
    """Compose one iteration's prompt. If the previous attempt failed
    verification, feed that exact output back -- "exact failure evidence"
    is rung 1 of the recovery ladder, and cheap enough to include even in
    this minimal loop."""
    parts = [task_text.strip()]
    if previous_failure:
        parts.append(
            "\n\nHere is the output of the verification command from your "
            "previous attempt, which is still failing. Investigate and fix "
            f"this:\n\n```\n{previous_failure.strip()[:4000]}\n```"
        )
    parts.append(STATUS_SUFFIX)
    return "\n".join(parts)


def run_devin(repo: Path, prompt_text: str, timeout: int, run_dir: Path) -> tuple[int, bool, str, str]:
    """One bounded, non-interactive Devin CLI turn, per
    phase0/DEVIN_CLI_CONTRACT.md: --permission-mode bypass, -p
    --prompt-file, no -c/-r (fresh session), graceful SIGTERM->SIGKILL on
    timeout. Known limitation (CHUNK-003): this does not guarantee killing
    any shell command devin itself had already spawned."""
    prompt_path = run_dir / "prompt.txt"
    prompt_path.write_text(prompt_text)
    cmd = ["devin", "--permission-mode", "bypass", "-p", "--prompt-file", str(prompt_path)]

    proc = subprocess.Popen(
        cmd, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
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


def run_verification(repo: Path, verify_cmd: str, timeout: int) -> tuple[int, str]:
    """Run the project's own verification command as its own subprocess --
    never through the agent's exec tool. This is the one and only source of
    truth for pass/fail."""
    try:
        proc = subprocess.run(
            verify_cmd, shell=True, cwd=repo,
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        output = (e.stdout or "") + (e.stderr or "")
        return -1, output + "\n[SisyphX: verification command itself timed out]"


def git_commit_iteration(repo: Path, iteration: int, passed: bool) -> tuple[str, bool]:
    """Checkpoint every iteration regardless of outcome -- this is the
    loop's entire rollback/recovery story for now: git history.
    Commits are tagged with the loop author so a post-iteration audit can
    distinguish loop-committed changes from agent-committed changes."""
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    committed = False
    if diff.returncode != 0:  # non-zero means there ARE staged changes
        status_word = "PASS" if passed else "fail"
        env = {
            "GIT_AUTHOR_NAME": LOOP_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": LOOP_AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": LOOP_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": LOOP_AUTHOR_EMAIL,
        }
        subprocess.run(
            ["git", "commit", "-m", f"SisyphX loop iteration {iteration} [{status_word}]"],
            cwd=repo,
            check=True,
            capture_output=True,
            env={**os.environ, **env},
        )
        committed = True
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
    ).stdout.strip()
    return sha, committed


def get_head(repo: Path) -> str:
    """Return the current HEAD sha."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
    )
    return result.stdout.strip()


def audit_commit_integrity(repo: Path, pre_head: str) -> tuple[bool, list[str]]:
    """Check whether any commits were added between pre_head and HEAD that were
    NOT authored by the loop. Returns (ok, list_of_offending_commits)."""
    if get_head(repo) == pre_head:
        return True, []
    log_proc = subprocess.run(
        ["git", "log", f"{pre_head}..HEAD", "--format=%H %an <%ae>"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    offending: list[str] = []
    for line in log_proc.stdout.strip().splitlines():
        if not line:
            continue
        sha, rest = line.split(" ", 1)
        if rest != f"{LOOP_AUTHOR_NAME} <{LOOP_AUTHOR_EMAIL}>":
            offending.append(line)
    return not offending, offending


def ensure_gitignored(repo: Path) -> None:
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    if ".agent-state/" not in existing:
        with gitignore.open("a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(".agent-state/\n")


def read_log(log_path: Path) -> list[RunLogEntry]:
    """Parse `.agent-state/runs/log.jsonl` into a list of entries.
    Tolerates blank lines and trailing newlines; skips unparseable lines
    (logging the failure would require a logger, so it returns `None` for
    those lines in `status` and continues)."""
    if not log_path.exists():
        return []
    entries: list[RunLogEntry] = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        entries.append(data)  # type: ignore[arg-type]
    return entries


def write_log_entry(log_path: Path, entry: RunLogEntry) -> None:
    """Append a single log entry to the JSONL log. Creates parent dirs."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(dict(entry), sort_keys=False) + "\n")


def run_loop(
    repo: Path,
    task_text: str,
    verify_cmd: str,
    max_iterations: int = 6,
    repeat_threshold: int = 3,
    agent_timeout: int = 240,
    verify_timeout: int = 120,
    log=print,
) -> int:
    """Returns a process-style exit code: 0 = passed, 2 = max_iterations
    exhausted, 3 = repeated identical failure signature detected,
    4 = guard abort or unauthorized commit (do not retry)."""
    state_dir = repo / ".agent-state" / "runs"
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "log.jsonl"
    ensure_gitignored(repo)

    previous_failure: str | None = None
    recent_signatures: list[FailureSignature] = []

    for iteration in range(1, max_iterations + 1):
        log(f"=== iteration {iteration}/{max_iterations} ===")
        run_dir = state_dir / f"{iteration:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)

        start = time.time()
        head_before = get_head(repo)
        (run_dir / "head_before.txt").write_text(head_before)

        prompt_text = build_prompt(task_text, previous_failure)
        agent_exit, timed_out, agent_stdout, agent_stderr = run_devin(
            repo, prompt_text, agent_timeout, run_dir
        )
        (run_dir / "agent_stdout.txt").write_text(agent_stdout)
        (run_dir / "agent_stderr.txt").write_text(agent_stderr)

        status = parse_status(agent_stdout)

        head_after = get_head(repo)
        (run_dir / "head_after.txt").write_text(head_after)
        ok, offending = audit_commit_integrity(repo, head_before)
        if not ok:
            log(f"=== STOPPING: unauthorized agent commit detected: {offending[0]} ===")
            duration = time.time() - start
            # Agent-committed code has bypassed the loop's checkpointing policy.
            signature = FailureSignature(
                kind="commit-integrity",
                normalized="",
                hash=hashlib.sha256("commit-integrity".encode()).hexdigest()[:16],
            )
            sha = get_head(repo)
            entry: RunLogEntry = {
                "iteration": iteration,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "agent_exit_code": agent_exit,
                "agent_timed_out": timed_out,
                "status": status,
                "verify_exit_code": -1,
                "passed": False,
                "failure_kind": signature.kind,
                "failure_signature": signature.hash,
                "head_before": head_before,
                "head_after": head_after,
                "git_sha": sha,
                "committed": False,
                "duration_seconds": round(duration, 1),
                "run_dir": str(run_dir.relative_to(repo)),
            }
            write_log_entry(log_path, entry)
            return 4

        verify_exit, verify_output = run_verification(repo, verify_cmd, verify_timeout)
        (run_dir / "verify_output.txt").write_text(verify_output)

        signature = failure_signature(
            verify_output,
            agent_exit,
            timed_out,
            agent_stderr,
            verify_exit,
            repo_path=repo,
            repo_root=REPO_ROOT,
        )
        passed = signature.kind == "verify-pass"

        sha, committed = git_commit_iteration(repo, iteration, passed)
        duration = time.time() - start

        entry: RunLogEntry = {
            "iteration": iteration,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent_exit_code": agent_exit,
            "agent_timed_out": timed_out,
            "status": status,
            "verify_exit_code": verify_exit,
            "passed": passed,
            "failure_kind": signature.kind,
            "failure_signature": signature.hash,
            "head_before": head_before,
            "head_after": head_after,
            "git_sha": sha,
            "committed": committed,
            "duration_seconds": round(duration, 1),
            "run_dir": str(run_dir.relative_to(repo)),
        }
        write_log_entry(log_path, entry)

        log(
            f"    agent_exit={agent_exit} timed_out={timed_out} status={status} "
            f"verify_exit={verify_exit} passed={passed} kind={signature.kind} "
            f"signature={signature.hash} sha={sha[:8]} committed={committed}"
        )

        if passed:
            log(f"=== PASSED on iteration {iteration} ===")
            return 0

        # Guard aborts are a distinct, more serious failure class: do not retry.
        if signature.kind == "guard":
            log("=== STOPPING: guard blocked an action ===")
            return 4

        previous_failure = verify_output
        recent_signatures.append(signature)
        recent_signatures = recent_signatures[-repeat_threshold:]
        if (
            len(recent_signatures) == repeat_threshold
            and len({s.hash for s in recent_signatures}) == 1
        ):
            log(f"=== STOPPING: identical failure signature repeated {repeat_threshold} times in a row ===")
            return 3

    log(f"=== STOPPING: max_iterations ({max_iterations}) reached without passing ===")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description="SisyphX Phase 1 minimal loop")
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--task", required=True, type=Path, help="path to a text file describing the task")
    ap.add_argument("--verify", required=True, help="shell command to run for independent verification")
    ap.add_argument("--max-iterations", type=int, default=6)
    ap.add_argument("--repeat-threshold", type=int, default=3)
    ap.add_argument("--agent-timeout", type=int, default=240)
    ap.add_argument("--verify-timeout", type=int, default=120)
    args = ap.parse_args()

    return run_loop(
        repo=args.repo.resolve(),
        task_text=args.task.read_text(),
        verify_cmd=args.verify,
        max_iterations=args.max_iterations,
        repeat_threshold=args.repeat_threshold,
        agent_timeout=args.agent_timeout,
        verify_timeout=args.verify_timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
