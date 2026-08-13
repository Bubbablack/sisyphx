# CHUNK-027 — Spike: verification-tier invocation contract

**Status:** done
**Date:** 2026-08-13
**Runner:** `phase3/run_chunk_027.py` +
`phase3/verification_contract_demo.py`

## Question

How should `loop.py` invoke an additional check beyond the project's
own verification command, informed by CHUNK-025 (property tests are
effective and fast) and CHUNK-026 (mutation testing is effective but
too slow for attempt-level use)?

## Contract

1. Attempt-level verification becomes at most **two tiers**, run in
   order, each a plain shell command executed exactly like today's
   single `--verify` command (`subprocess.run(shell=True, cwd=repo,
   timeout=...)`) -- no new execution model, just one more of the
   same thing.
2. **Tier 1** (required, unchanged): the project's own verification
   command. Behavior for chunks that declare no tier 2 is byte-for-
   byte identical to Phase 1/2 (CHUNK-031's backward-compatibility
   requirement).
3. **Tier 2** (new, opt-in per chunk): an additional shell command,
   supplied the same way tier 1 already is -- a new CLI flag
   (`--verify-tier2`) with its own timeout (`--verify-tier2-timeout`,
   default well under the attempt-level 60s budget, since CHUNK-025
   measured property tests at ~1-2s; mutation-testing-style commands
   should not be put here per CHUNK-026's finding).
4. **Execution order:** tier 2 only runs if tier 1 passes. If tier 1
   fails, the iteration fails immediately exactly as today
   (`failure_kind = "verify-fail"`) and tier 2 is skipped -- no point
   spending budget on a stronger check when the basic gate already
   failed.
5. If tier 1 passes but tier 2 fails: `failure_kind =
   "verify-tier2-fail"` (new, for CHUNK-029) -- a distinct failure
   class from ordinary `verify-fail`, because it means "the base
   tests were satisfied but a stronger contract check was not",
   which is exactly the semantic-cheat pattern from CHUNK-010/024.
6. Both tiers passing -> `"verify-pass"`, unchanged.
7. **Where tier 2 test files live:** no new directory convention.
   They live alongside the project's other tests (as
   `test_calc_property.py` already does in the fixture), excluded
   from tier 1's default test discovery (via `testpaths`, per
   CHUNK-025), and invoked by explicit path in the `--verify-tier2`
   command string -- exactly how a human would run them by hand.
8. **Output capture:** tier 2's raw stdout+stderr is saved alongside
   tier 1's existing `verify_output.txt`
   (`verify_tier2_output.txt`), following `run_dir`'s existing
   per-iteration artifact convention.
9. **Retry granularity:** unchanged -- a tier-2 failure retries the
   whole agent turn (feeding back tier 2's exact failure evidence,
   same as tier 1 does today), not just tier 2 in isolation. This
   keeps CHUNK-021's recovery ladder as the single retry mechanism
   rather than adding a second one.

## Demonstration

`phase3/verification_contract_demo.py` implements this contract
standalone (not wired into `loop.py` yet -- that is CHUNK-031, after
CHUNK-028/029/030 exist). Two scenarios:

- **Scenario A (normal):** `phase1/target_repo`'s already-correct
  `calc.py` plus a hand-written property test -- a non-contradictory,
  ordinary chunk.
- **Scenario B (cheat):** the CHUNK-024 fixture with the known
  `add_one -> x + 2` cheat installed.

## Results

| Scenario | tier1 exit | tier2 exit | passed | failure_kind | duration |
|---|---|---|---|---|---|
| A (normal) | 0 | 0 | True | `verify-pass` | 5.64s |
| B (cheat) | 0 | 1 | False | `verify-tier2-fail` | 5.86s |

## Finding

Scenario A (normal, correct implementation) passes both tiers and
completes in 5.6s, well within budget -- the contract is a
transparent pass-through when the implementation is actually correct.

Scenario B (cheat) passes tier 1 (the weak, contradictory test) but
fails tier 2 (the property test) in 5.9s, producing the new
distinct `verify-tier2-fail` failure kind instead of the misleading
`verify-pass` the loop would have recorded without tier 2. This is
the exact case CHUNK-024 reproduced with a real agent run, now
caught mechanically without needing to re-run the agent.

## Implications for Phase 3 implementation

- CHUNK-028 (`phase3/verification_tiers.py`) should implement exactly
  this contract, promoting `verification_contract_demo.py`'s logic
  into the real module.
- CHUNK-029's new failure kind should be named `verify-tier2-fail`
  (or equivalent) to match this contract.
- CHUNK-031's `loop.py` integration should add `--verify-tier2` /
  `--verify-tier2-timeout` as new, optional CLI arguments with no
  default command -- chunks that don't pass `--verify-tier2` see
  zero behavior change from Phase 1/2, satisfying the
  backward-compatibility requirement directly.

## Artifacts

- `phase3/verification_contract_demo.py` (the throwaway reference
  implementation CHUNK-028 will promote)
- `phase3/run_chunk_027.py`
