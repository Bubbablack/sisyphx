#!/usr/bin/env python3
"""Throwaway PreToolUse hook for CHUNK-005: log the raw event JSON so we can
learn the real tool_input schema for edit/write/exec, then always allow
(exit 0) since this pass is observation-only."""
import sys
import json
import datetime

LOG_PATH = "/Users/stini/Ai_Dev_Home/SisyphX/phase0/notes/hook_debug_log.jsonl"

raw = sys.stdin.read()
entry = {"received_at": datetime.datetime.utcnow().isoformat(), "raw": raw}
try:
    entry["parsed"] = json.loads(raw)
except Exception as e:
    entry["parse_error"] = str(e)

with open(LOG_PATH, "a") as f:
    f.write(json.dumps(entry) + "\n")

sys.exit(0)
