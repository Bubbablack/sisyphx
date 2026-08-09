#!/usr/bin/env python3
"""CHUNK-005 spike: PreToolUse guard that blocks destructive git/shell
commands, matching spec section 12 ("do not execute destructive Git
commands"). Demo pattern list -- real SisyphX will maintain this as a
reviewed policy, not an ad hoc regex list."""
import sys
import json
import re

DESTRUCTIVE_PATTERNS = [
    r"git\s+push\s+.*--force",
    r"git\s+push\s+.*-f\b",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-[a-z]*f",
    r"\brm\s+-rf\b",
    r"git\s+branch\s+-D",
]


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except Exception:
        sys.exit(0)

    command = event.get("tool_input", {}).get("command", "")
    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command):
            print(json.dumps({
                "decision": "block",
                "reason": (
                    f"SisyphX guard: command matches destructive pattern "
                    f"'{pattern}': {command}"
                ),
            }))
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
