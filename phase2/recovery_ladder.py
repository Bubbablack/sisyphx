#!/usr/bin/env python3
"""CHUNK-021 — minimal recovery ladder.

Pure function: given the run log so far, decide what to do next.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RecoveryAction:
    kind: str          # 'retry', 'escalate', 'stop'
    prompt_text: str   # text to feed into the next prompt (empty for 'stop')
    stop: bool         # if True, the loop should stop now


STOP_KINDS = ("guard", "tamper", "commit-integrity", "agent-error")


def _same_signature_run_length(history: list[dict[str, Any]]) -> int:
    """Count how many of the most recent consecutive entries share the same
    failure_signature."""
    if not history:
        return 0
    target = history[-1]["failure_signature"]
    count = 0
    for entry in reversed(history):
        if entry.get("failure_signature") == target:
            count += 1
        else:
            break
    return count


def decide_action(
    history: list[dict[str, Any]],
    repeat_threshold: int = 3,
) -> RecoveryAction:
    """Return the next recovery action based on the log history.

    Policy (CHUNK-021):
      1. New failure signature -> feed exact failure evidence.
      2. Second consecutive identical signature -> escalate with a warning
         to investigate before editing.
      3. Third (or repeat_threshold-th) identical signature, or any
         guard/tamper/commit-integrity/agent-error -> stop and escalate.
    """
    if not history:
        return RecoveryAction("retry", "", False)

    last = history[-1]
    kind = last.get("failure_kind", "unknown")
    if kind in STOP_KINDS:
        return RecoveryAction("stop", "", True)

    same = _same_signature_run_length(history)

    if same >= repeat_threshold:
        return RecoveryAction("stop", "", True)

    if same == repeat_threshold - 1 and repeat_threshold > 1:
        return RecoveryAction(
            "escalate",
            (
                "You have produced the same failure twice in a row. "
                "Do not repeat the same edit. Investigate the root cause "
                "before changing any file."
            ),
            False,
        )

    evidence = last.get("verify_output", "")
    return RecoveryAction("retry", evidence.strip(), False)


def _last_diff(repo: Path) -> str:
    """Best-effort diff of the most recent changes. Prefers the last commit,
    falls back to the working tree."""
    commit_diff = subprocess.run(
        ["git", "diff", "HEAD~1..HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if commit_diff.returncode == 0 and commit_diff.stdout:
        return commit_diff.stdout
    working = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if working.returncode == 0:
        return working.stdout
    return "[diff unavailable]"


def write_escalation_brief(
    repo: Path,
    task_text: str,
    history: list[dict[str, Any]],
) -> Path:
    """Generate `.agent-state/escalation.md` for human review."""
    path = repo / ".agent-state" / "escalation.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    iterations_md = "\n".join(
        f"- iteration {e.get('iteration')}: kind=`{e.get('failure_kind')}` "
        f"signature=`{e.get('failure_signature')}` "
        f"verify_exit={e.get('verify_exit_code')}`"
        for e in history
    )

    body = f"""# SisyphX escalation brief

## Task

```
{task_text.strip()}
```

## Iterations

{iterations_md}

## Last diff

```diff
{_last_diff(repo)}
```

## Summary

The loop stopped after repeated failures or a guard/tamper event.
The same failure signature appeared {len(history)} time(s); the agent
did not make progress.
"""
    path.write_text(body)
    return path
