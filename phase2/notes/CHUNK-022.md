# CHUNK-022 — EventStore retrofit (append-only, SQLite)

**Status:** done  
**Date:** 2026-08-09  

## What changed

- New `phase2/event_store.py` with an append-only `EventStore` class backed by
  SQLite.
- Schema is minimal: `events(id, event_type, run_id, iteration, timestamp,
  payload)` plus indexes on `run_id`, `event_type`, and `(run_id, iteration)`.
- The table has `BEFORE UPDATE` and `BEFORE DELETE` triggers so history cannot
  be mutated, even via direct SQL.
- Public API is `append(...)`, `get_events(...)`, `get_event_types(...)`, and
  `close()`. There is no update or delete API.
- `phase1/loop.py` now emits events alongside the existing JSONL log:
  - `run_started`
  - `iteration_started`
  - `agent_finished`
  - `verify_result`
  - `guard_trip` (commit-integrity / tamper / PreToolUse guard)
  - `recovery_action`
  - `iteration_finished`
  - `stop`
- New `phase2/test_event_store.py` (round-trip, filtering, append-only
  enforcement, public API audit) and an integration test in
  `phase1/tests/test_run_log.py`.
- `pyproject.toml` testpaths updated.

## Real end-to-end run

- Repo: `phase1/target_repo`
- Task: `phase1/task_fix_calc.txt`
- Verify: `uv run pytest`
- Max iterations: 2

The agent fixed `add_one` to return `x + 1` on the first iteration and the
verification passed.

- Final exit code: 0
- Event store: `phase1/target_repo/.agent-state/events.db`
- Queryable event trail:

```
1 run_started
2 iteration_started 1
3 agent_finished 1
4 verify_result 1 verify-pass
5 iteration_finished 1 verify-pass
6 stop 1 verify-pass
```

The SQLite DB can be re-opened after the run and queried by `run_id`,
`event_type`, and `iteration`.

## Verification

- `uv run pytest` → **66 passed**
- Real run produced a queryable event trail with all expected event types.
