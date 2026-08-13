# CHUNK-029 — New failure kinds for verification-tier results

**Status:** done
**Date:** 2026-08-13

## What was built

Extended `phase2/failure_signature.py` and `phase2/recovery_ladder.py`
(both untouched since Phase 2) for the new `verify-tier2-fail` failure kind,
per CHUNK-027's contract:

- `classify_failure()` gains an optional `verify_tier2_exit_code` parameter
  (default `None` = "no second tier configured", reproducing Phase 1/2
  behavior exactly). When tier 1 passes and tier 2 was configured but
  failed, it now returns `"verify-tier2-fail"` instead of `"verify-pass"`.
- `failure_signature()` gains matching `verify_tier2_output`/
  `verify_tier2_exit_code` parameters. For `verify-tier2-fail`, the hash
  identity and the reported `normalized` evidence both come from tier 2's
  output, not tier 1's -- tier 1 already passed, so its output isn't the
  useful failure evidence.
- `phase2/recovery_ladder.py::decide_action()` picks `verify_tier2_output`
  as the retry evidence when the failure kind is `verify-tier2-fail`,
  falling back to `verify_output` otherwise. `verify-tier2-fail` is
  deliberately **not** added to `STOP_KINDS` -- it goes through the normal
  retry -> escalate -> stop ladder (same as ordinary `verify-fail`), per the
  acceptance criteria's "treats them as their own class" (distinct
  signature/kind), not "treats them like a guard abort".

## A real normalization gap found and fixed

Building the "same failure twice" unit test with two genuinely independent
real captures of the CHUNK-024/025 cheat + property test (not the same file
reused) surfaced a real bug: Hypothesis sometimes appends a non-deterministic
inline comment to its failing-example output --
`x=0,  # or any other generated value` vs. plain `x=0,` -- which defeated
`normalize_verify_output`'s existing rules and would have produced two
different signatures for what is actually the same underlying failure. Added
rule 8b to strip it. Two fresh captures
(`phase3/notes/chunk025_cheat_property_pytest.txt` and the newly captured
`phase3/notes/chunk029_cheat_property_pytest_b.txt`) now correctly normalize
to the same text and hash.

## Verification

- `phase2/test_failure_signature.py`: added 3 new real scenarios built from
  CHUNK-025's actual captured tier1+tier2 outputs
  (`tier2_cheat_a`/`tier2_cheat_b`/`tier2_genuine_fix`, the latter two using
  a freshly captured second real run for `tier2_cheat_b`), plus 2 new test
  functions (`test_tier2_fail_is_a_distinct_kind_from_ordinary_verify_fail`,
  `test_tier2_not_configured_reproduces_phase1_2_behavior`). Existing
  `test_same_failure_same_signature`/`test_different_failures_different_signatures`
  extended to include the new scenarios.
- `phase2/test_recovery_ladder.py`: added 4 new tests confirming tier-2
  evidence selection, that a single `verify-tier2-fail` does not stop
  immediately, and that repeated `verify-tier2-fail` escalates/stops exactly
  like `verify-fail`.
- Full suite: `uv run pytest` -> **82 passed** (66 before this chunk + 7 from
  CHUNK-028 + 9 new here).
- Manual integration sanity check: ran `phase3.verification_tiers.run_tiered_verification`
  directly against the tracked fixture (unmodified, still has the original
  bug) and against a scratch copy with the known cheat installed, feeding
  each result straight into `phase2.failure_signature.failure_signature`:
  the unmodified fixture correctly produces `verify-fail` (tier 1 itself
  fails, since the bug is unfixed); the cheat variant correctly produces
  `verify-tier2-fail`. No glue code needed beyond passing the dataclass
  fields through -- the two modules' contracts line up directly.

## Artifacts

- `phase2/failure_signature.py` (extended)
- `phase2/recovery_ladder.py` (extended)
- `phase2/test_failure_signature.py` (extended)
- `phase2/test_recovery_ladder.py` (extended)
- `phase3/notes/chunk029_cheat_property_pytest_b.txt` (new real capture)
