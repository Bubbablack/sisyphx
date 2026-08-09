#!/usr/bin/env python3
"""CHUNK-005 spike: PreToolUse guard that blocks write/edit outside a chunk's
permitted_paths. This is a hardcoded demo -- real SisyphX generates this
per-chunk from ImplementationChunk.permitted_paths, it doesn't hardcode it."""
import sys
import json
import os

WORKSPACE = "/Users/stini/Ai_Dev_Home/SisyphX/phase0/scratch"
PERMITTED_PREFIXES = [os.path.join(WORKSPACE, "allowed_src")]


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except Exception:
        # Fail open for this spike so a parser bug doesn't wedge the session.
        # Real SisyphX should fail closed + alert loudly instead.
        sys.exit(0)

    file_path = event.get("tool_input", {}).get("file_path")
    if not file_path:
        sys.exit(0)

    real_path = os.path.realpath(file_path)
    allowed = any(
        real_path == os.path.realpath(prefix)
        or real_path.startswith(os.path.realpath(prefix) + os.sep)
        for prefix in PERMITTED_PREFIXES
    )
    if not allowed:
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"SisyphX guard: {file_path} is outside this chunk's "
                f"permitted_paths ({PERMITTED_PREFIXES})"
            ),
        }))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
