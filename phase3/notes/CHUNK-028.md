# CHUNK-028 — `phase3/verification_tiers.py`

**Status:** done
**Date:** 2026-08-13
**Runner:** `phase3/run_chunk_028.py`

## What was built

`phase3/verification_tiers.py`: the real, promoted implementation of
CHUNK-027's two-tier verification contract (the CHUNK-027 module,
`verification_contract_demo.py`, was explicitly a throwaway). Adds a
`timed_out` flag on `TierResult` (the CHUNK-027 demo didn't
distinguish a timeout from an ordinary non-zero exit) and a
`DEFAULT_TIER2_TIMEOUT_SECONDS = 30` constant, informed directly by
CHUNK-025 (property tests measured ~1-2s) and CHUNK-026 (mutation
testing measured 52-64s and does not belong at this tier).

## Verification

- `phase3/test_verification_tiers.py`: 7 unit tests with stubbed
  `subprocess.run` covering tier1-fail-skips-tier2,
  tier1-pass-no-tier2-configured (backward compatibility),
  tier1-pass-tier2-pass, tier1-pass-tier2-fail (the new failure
  kind), tier1 timeout, tier2 timeout, and the exact `shell=True`/
  `cwd=repo` invocation convention. All pass; full suite (`uv run
  pytest`) is 73 passed (66 existing + 7 new).
- Real run (this script) against the same two scenarios CHUNK-027
  used, but calling the real `phase3.verification_tiers` module
  instead of the throwaway demo, to confirm the promoted module
  behaves identically.

## Results

| Scenario | tier1 exit | tier2 exit | passed | failure_kind | duration |
|---|---|---|---|---|---|
| A (normal) | 0 | 0 | True | `verify-pass` | 5.93s |
| B (cheat) | 0 | 1 | False | `verify-tier2-fail` | 5.87s |

## Finding

The real `phase3/verification_tiers.py` module reproduces the exact
CHUNK-027 contract behavior: scenario A (normal, correct
implementation) passes both tiers; scenario B (the CHUNK-024 cheat)
passes tier 1 but is caught by tier 2 with the distinct
`verify-tier2-fail` failure kind, well within the 30s tier-2 timeout
default.

## Artifacts

- `phase3/verification_tiers.py`
- `phase3/test_verification_tiers.py`
- `phase3/run_chunk_028.py`
