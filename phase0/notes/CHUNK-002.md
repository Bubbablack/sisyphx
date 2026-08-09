# CHUNK-002 — Confirm fresh-session default

**Status:** done
**Date:** 2026-08-08

## Method

All tests continue in `phase0/scratch/` (same scratch repo as CHUNK-001, so
session history accumulates there — see note below).

## Results

### Test 6a/6b — no memory between independent `-p` calls

1. `devin -p "Remember this secret code: WATERMELON42. Just reply with: NOTED"`
   → replied `NOTED`.
2. Fresh call: `devin -p "What secret code did I just tell you a moment ago? ... reply UNKNOWN"`
   → replied `UNKNOWN`.

Confirms: **no `-c`/`-r` flag means no shared memory**, exactly as the fresh
session default should behave.

### Test 6c — `devin list --format json`

Every single `-p` invocation (from this chunk and CHUNK-001) shows up as its
own distinct, listable session:

```json
{
  "id": "aspiring-saffron",
  "short_id": "aspiring-saffron",
  "working_directory": "/Users/.../phase0/scratch",
  "last_activity_at": 1786206399,
  "last_activity_ago": "just now",
  "title": "What secret code did I just tell you a moment ago? ..."
}
```

Useful fields for SisyphX:
- `id`/`short_id` — human-readable slug (e.g. `aspiring-saffron`), stable
  identifier we can store on a `Run`/`Attempt` record for traceability. A human
  could later run `devin -r <id>` or `/resume <id>` to inspect a specific
  attempt interactively.
- `title` — appears to be derived directly from the prompt text (verbatim, at
  least for short prompts). Not a substitute for our own structured logging,
  but a free cross-check.
- `working_directory` — confirms which workspace the session ran in.

**Note:** sessions accumulate per working directory indefinitely (6 sessions
now exist for this one scratch dir after ~15 minutes of testing). Not a
problem for Phase 0, but the loop's run log (CHUNK-011) should capture the
session ID itself rather than relying on `devin list` growing forever as the
system of record.

### Test 6d/6e — positive control: `-c`/`--continue` DOES carry memory

1. `devin -p "Remember this second secret code: PLATYPUS99. Reply with exactly: NOTED2"`
   → replied `NOTED2`.
2. `devin -c -p "What was the second secret code I just told you? ..."`
   → replied `PLATYPUS99`.

Confirms the "fresh by default" behavior is deliberate, not just broken
memory — continuity is available and correct when explicitly requested via
`-c` (resumes most recent session in the current directory).

## Implications for the loop

1. **`loop.py` needs no special "start fresh" logic.** Simply never pass
   `-c`/`-r`/`--continue`/`--resume`, and every iteration is automatically a
   new, independent session — matches the Ralph philosophy (state lives in
   the filesystem/git, not the agent's own memory).
2. **Capture the session `id` from each iteration** (parseable from
   `devin list --format json` immediately after each call, matched by
   `working_directory` + most-recent `last_activity_at`) and store it in
   `runs/log.jsonl` (CHUNK-011) for human traceability, even though the loop
   itself doesn't use it.
3. `-c` remains available as a manual escape hatch (a human debugging a stuck
   chunk could resume the last session interactively) but is out of scope for
   the automated loop itself.
