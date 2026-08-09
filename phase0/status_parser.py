"""CHUNK-006: parse SisyphX's structured "done" status line out of a Devin
CLI response.

The prompt template asks the agent to end its response with exactly one line:

    SISYPHX_STATUS: {"outcome": "done", "summary": "..."}

`outcome` is one of "done", "blocked", "partial" (agent's own self-report --
NEVER treated as ground truth by the loop, only as a hint / log annotation.
Independent verification is what actually decides pass/fail).

This parser tolerates the formatting drift observed in real runs:
- extra leading/trailing whitespace
- markdown code-fence backticks around the line or the JSON value
- a bare word instead of a JSON object (e.g. "SISYPHX_STATUS: done")
- the instruction being echoed earlier in the response (we take the LAST
  match, not the first)
- malformed/truncated JSON (falls back to a raw-string outcome rather than
  raising)
"""
from __future__ import annotations

import json
import re

_STATUS_LINE = re.compile(r"^[ \t]*SISYPHX_STATUS:[ \t]*(?P<rest>.+?)[ \t]*$", re.MULTILINE)


def parse_status(stdout: str) -> dict | None:
    """Extract the last SISYPHX_STATUS line from `stdout` as a dict, or None
    if no such line is present. Never raises."""
    matches = _STATUS_LINE.findall(stdout or "")
    if not matches:
        return None

    raw = matches[-1].strip()
    # Strip surrounding markdown code-fence/backtick noise, e.g. `done` or ```{"outcome": "done"}```
    raw = raw.strip("`").strip()

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"outcome": raw}

    if isinstance(parsed, dict):
        parsed.setdefault("outcome", "unknown")
        return parsed
    return {"outcome": str(parsed)}
