# CHUNK-021 — Minimal recovery ladder

**Status:** done  
**Date:** 2026-08-09  
**Runner:** `phase2/run_chunk_021.py`

## What changed

- New `phase2/recovery_ladder.py` with `decide_action(history,
  repeat_threshold)` and `write_escalation_brief(...)`.
- `phase1/loop.py` now consults the ladder at the end of each failed
  iteration:
  1. **New signature** → feed exact `verify_output` to the next prompt
     (previous behavior).
  2. **Second identical signature** → escalate with a warning to
     investigate before editing.
  3. **Third identical signature / guard / tamper / commit-integrity /
     agent-error** → stop and write `.agent-state/escalation.md`.

## End-to-end forced-unsolvable run

- Repo: `phase2/scratch/chunk021/unsolvable` (copy of
  `phase1/target_repo`)
- Task: the agent is told not to edit any files; only confirm the
  failing test.
- Verify: `uv run pytest`
- Max iterations: 3, repeat threshold: 3.

Because the agent made no progress, the same normalized `verify-fail`
signature repeated. The ladder fed exact evidence once, escalated once,
then stopped and wrote the escalation brief.

- Log entries: 3
- Final exit code: 3
- Escalation brief: `/Users/stini/Ai_Dev_Home/SisyphX/phase2/scratch/chunk021/unsolvable/.agent-state/escalation.md`
- Failure signatures: ['cc8856f589d156ad', 'cc8856f589d156ad', 'cc8856f589d156ad']
- Failure kinds: ['verify-fail', 'verify-fail', 'verify-fail']

## Verification

- `uv run pytest` → **58 passed** (new recovery-ladder policy tests)
- Real run in `phase2/scratch/chunk021/unsolvable` produced a readable
  `escalation.md`.
