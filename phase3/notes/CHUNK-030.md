# CHUNK-030 — `EventStore` schema gains verification-tier fields

**Status:** done
**Date:** 2026-08-13
**Runner:** `phase3/run_chunk_030.py`

## What was built

`phase2/event_store.py::EventStore.append_verify_result()` -- a new,
additive convenience method, not a SQL schema migration. The
`events` table's `payload` column was already an opaque JSON blob
(CHUNK-022), so no `ALTER TABLE` was needed or possible to make
meaningfully different -- any event can already carry any fields.
What was missing was a single place that defines the CHUNK-029
tier-2 field names (`verify_tier2_ran`, `verify_tier2_exit_code`,
`verify_tier2_output`) so `loop.py`'s CHUNK-031 integration doesn't
have to remember or guess them, and so every `verify_result` event
going forward carries them consistently (with harmless defaults when
no tier 2 was configured).

## Verification

- `phase2/test_event_store.py`: 2 new tests -- round-trip of the new
  fields, and confirmation that plain pre-CHUNK-030 `append()` calls
  for `verify_result` events still work unchanged. Full suite: 84
  passed (82 before this chunk + 2 new).
- Real run (this script): ran the full pipeline --
  `verification_tiers.run_tiered_verification` against a scratch
  copy of the CHUNK-024 fixture with the known cheat installed,
  `failure_signature.failure_signature` to classify the result, then
  `EventStore.append_verify_result` to record it, then **reopened
  the database as a fresh `EventStore` instance** and queried the
  event back by `run_id`/`event_type` to confirm it's durable and
  queryable, not just an in-memory round trip.

## Result

Queried back from a freshly reopened SQLite file:

```
failure_kind = 'verify-tier2-fail'
verify_tier2_ran = True
verify_tier2_exit_code = 1
```

Confirms the full chain -- verification tiers, failure
classification, and the event store -- produces a durable,
queryable record of exactly why the CHUNK-024 cheat was caught.

## Artifacts

- `phase2/event_store.py` (extended: `append_verify_result`)
- `phase2/test_event_store.py` (extended)
- `phase3/run_chunk_030.py`
