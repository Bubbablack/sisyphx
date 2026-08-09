# CHUNK-018 — Loop uses `FailureSignature` for stuck detection

**Status:** done  
**Date:** 2026-08-09  
**Runner:** `phase2/run_chunk_018.py`

## What changed

- `phase1/loop.py` now computes a `FailureSignature` after every
  verification.
- The run log gains `failure_kind` and `failure_signature` fields.
- Stuck detection is signature-based: the last `repeat_threshold` failures
  must have the same `failure_signature.hash`, not be byte-identical.
- Guard aborts (`agent_exit_code == 1` + guard sentinel in stderr) stop
  the loop immediately with exit code 4; no retry.

## End-to-end run

- Repo: `phase2/scratch/chunk018/stuck` (copy of `phase1/target_repo`)
- Task: confirm the failing test, do not edit files.
- Verify: `uv run pytest`
- Max iterations: 2, repeat threshold: 2.

The first two `uv run pytest` outputs differed only in their volatile
durations (`in 0.XXs`). After normalization, both collapsed to the same
`FailureSignature`:

- Iteration 1: kind=`verify-fail` signature=`cc8856f589d156ad`
- Iteration 2: kind=`verify-fail` signature=`cc8856f589d156ad`

The loop stopped at `repeat_threshold=2` with exit code 3.

## Exit codes

- `0` — verification passed
- `2` — `max_iterations` reached
- `3` — identical failure signature repeated `repeat_threshold` times
- `4` — guard abort (do not retry)

## Verification

- `uv run pytest` (all 40 tests pass):
  - `phase1/test_loop.py` (15)
  - `phase1/tests/test_run_log.py` (10, including new guard/timeout tests)
  - `phase2/test_failure_signature.py` (15)
- Real run: `phase2/scratch/chunk018/stuck` produced two identical
  `FailureSignature` hashes and exited 3.

## Next

CHUNK-019 will add commit-integrity guard (CHUNK-013 findings), and
CHUNK-020 will add the post-iteration diff tamper guard (CHUNK-016
findings).
