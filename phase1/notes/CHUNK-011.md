# CHUNK-011 — Formalize + test `runs/log.jsonl` format

**Status:** done  
**Date:** 2026-08-08  
**Environment:** `uv` with pytest, Python 3.9.10.

## What was built

1. `RunLogEntry` `TypedDict` in `phase1/loop.py` defining the canonical schema.
2. `LOG_FIELDS` tuple giving a stable field order for human-readable log lines.
3. `read_log(log_path)` — parses `.agent-state/runs/log.jsonl` into a list of
   `RunLogEntry`, tolerating blank/malformed/non-dict lines.
4. `write_log_entry(log_path, entry)` — appends a single entry to the JSONL
   log and creates parent dirs.
5. `tests/test_run_log.py` — pytest suite covering the parser and `run_loop`
   integration logging.

## Method

- Refactored `run_loop` to build a `RunLogEntry` and call `write_log_entry`.
- Added `tests/conftest.py` to put the parent `phase1/` directory on
  `sys.path` so tests in `tests/` can `import loop`.
- Wrote `tests/test_run_log.py` with:
  - `read_log` parser tests (missing file, valid JSONL, blanks/malformed,
    non-dict lines)
  - `run_loop` integration tests using `monkeypatch` for `run_devin` and
    `run_verification` and real `tmp_path` git repos:
    - pass on first iteration → exit 0, log has 1 entry, all canonical fields
    - max iterations exhausted → exit 2, log has `max_iterations` entries
    - repeat-threshold stop → exit 3, log has `repeat_threshold` entries

## Results

All 23 tests passed:

```
$ uv run pytest tests/test_run_log.py test_loop.py -v
... 23 passed in 3.32s
```

The canonical `RunLogEntry` schema is:

| Field | Type | Meaning |
|---|---|---|
| `iteration` | `int` | 1-based attempt number |
| `timestamp` | `str` | ISO-8601 UTC, e.g. `"2026-08-08T17:07:41Z"` |
| `agent_exit_code` | `int` | Devin CLI process exit code |
| `agent_timed_out` | `bool` | `True` if `subprocess` had to kill Devin |
| `status` | `dict \| None` | Parsed `SISYPHX_STATUS` self-report, if any |
| `verify_exit_code` | `int` | Independent verification command exit code |
| `passed` | `bool` | `True` iff `verify_exit_code == 0` |
| `git_sha` | `str` | `HEAD` after the loop's own commit attempt |
| `committed` | `bool` | `True` if the loop itself staged+committed changes |
| `duration_seconds` | `float` | Wall-clock time for this iteration |
| `run_dir` | `str` | Path to artifacts, relative to repo root |

## Implications / learnings

1. A simple JSONL log is enough for Phase 1. It is human-readable,
   append-only, and survives a crashed/timeouted iteration because each line is
   written immediately.
2. `read_log` is forgiving: blank lines, malformed JSON, and non-dict lines
   are skipped. This matters for a log that may be partially written during a
   crash.
3. `run_loop` integration tests via `monkeypatch` are fast and give confidence
   in the stop-condition logic without invoking the real Devin CLI.
4. The `committed` field only records whether the **loop** committed. As
   discovered in CHUNK-010, the agent can make its own commits; that is not
   captured by this boolean. A Phase 2 field may need to track "HEAD changed
   since last iteration" separately, or a diff between the loop's intended
   commit and the actual HEAD.
