#!/usr/bin/env python3
"""CHUNK-013 spike: PreToolUse exec guard that blocks agent-initiated
`git commit` and `git push` commands in `--permission-mode bypass`.

Allows non-git shell commands and other git subcommands (add, status, log, ...).
A block prints `{"decision": "block", ...}` to stdout and exits 2.
An allow exits 0 with no output.
"""
import json
import re
import sys
from pathlib import Path

# Block any command containing a git commit or git push invocation.
# The agent may wrap commands (e.g. `sh -c "git commit ..."`), so we search.
BLOCKED_PATTERN = re.compile(r"\bgit\s+(?:commit|push)\b", re.IGNORECASE)


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except Exception:
        # Malformed hook event: fail open (allow) so the loop can see and log
        # the anomaly rather than silently killing every session.
        sys.exit(0)

    command = event.get("tool_input", {}).get("command", "")
    match = BLOCKED_PATTERN.search(command)
    if match:
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"SisyphX guard: command matches blocked git subcommand: {command!r}"
            ),
        }))
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
