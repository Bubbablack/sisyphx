# CHUNK-026 — Spike: mutation-testing tool selection

**Status:** done
**Date:** 2026-08-13
**Runner:** `phase3/run_chunk_026.py` (cosmic-ray scenarios); `mutmut`
trial below was run manually and is not scripted (see why).

## Question

Can a mutation-testing tool flag CHUNK-024's semantic cheat as poorly
tested, and does it fit the attempt-level <60s latency budget (Design
decision #4)?

## `mutmut` — rejected, not viable in this environment

Trialled first per PLAN.md's preference order. Findings from a manual
run against a scratch copy of the fixture with `hypothesis`,
`pytest`, and `mutmut` as dev dependencies:

1. **Dependency friction:** `mutmut`'s dependency `libcst` has no
   prebuilt wheel for `cp313-macosx_x86_64` at its latest version
   (1.9.0 dropped x86_64 macOS wheels entirely, arm64-only); building
   from source requires a Rust toolchain, which this project
   deliberately avoids installing for a spike (same reasoning as the
   CHUNK-006 `uv`-not-`brew` decision). Pinning `libcst<1.9` (1.8.6,
   which does ship a `cp313-macosx_10_13_x86_64` wheel) worked around
   this.
2. **Setup cost blows the budget on the very first run:** `mutmut run`
   builds its own fully isolated `mutants/.venv` and reinstalls every
   dependency into it before mutating anything. This was still
   running after 5+ minutes of 4-core CPU saturation with zero
   mutants actually tested (`exit_code_by_key` was still all `null`)
   on a **2-function module**. This is a one-time-per-invocation
   cost, not amortized across the run.
3. **Crashed on retry:** re-running `mutmut run` after that
   environment was already built failed in 8.5s with an internal
   `AssertionError` inside `create_mutants`, before running any
   mutants.

Given (2) alone already violates the <60s attempt-level budget by
multiple orders of magnitude on a trivial module, and (3) is an
outright tool crash, `mutmut` is rejected for this environment
without further investigation (out of scope for a spike).

## `cosmic-ray` — viable, with caveats

Installed cleanly (no compiler toolchain needed) and ran successfully.
Two scenarios, per `phase3/run_chunk_026.py`:

## Results

| Scenario | Test command | `init` | `exec` | Mutants | Survived |
|---|---|---|---|---|---|
| `cheat` | `test_calc.py` | 9.4s | 52.5s | 26 | 2 (7.69%) |
| `genuine_fix` | `test_calc_property.py` | 9.3s | 64.1s | 26 | 0 (0.00%) |

### Cheat + `test_calc.py`: tail of report (survivors visible above 'total jobs')

```
Shift 0
worker outcome: WorkerOutcome.NORMAL, test outcome: TestOutcome.KILLED
[job-id] 3a40eb0d820242358e3fbc7899a5b2f5
calc.py core/ReplaceBinaryOperator_Mul_BitOr 0
worker outcome: WorkerOutcome.NORMAL, test outcome: TestOutcome.KILLED
[job-id] 0dfc6153bd424479baa0d7b520528a3f
calc.py core/ReplaceBinaryOperator_Mul_BitAnd 0
worker outcome: WorkerOutcome.NORMAL, test outcome: TestOutcome.KILLED
[job-id] ed41cc2fc0db44488bd138e676f50da5
calc.py core/ReplaceBinaryOperator_Mul_BitXor 0
worker outcome: WorkerOutcome.NORMAL, test outcome: TestOutcome.KILLED
[job-id] a35a63b61f504782ab39b2a4db5f560b
calc.py core/NumberReplacer 0
worker outcome: WorkerOutcome.NORMAL, test outcome: TestOutcome.KILLED
[job-id] ad2ddc06819747a2a5c0ca9edc271341
calc.py core/NumberReplacer 1
worker outcome: WorkerOutcome.NORMAL, test outcome: TestOutcome.KILLED
[job-id] eec85c22493c49ae85149b98376b2e32
calc.py core/NumberReplacer 2
worker outcome: WorkerOutcome.NORMAL, test outcome: TestOutcome.KILLED
[job-id] dae3e317c65f4f6ab7aff5243d3ef72b
calc.py core/NumberReplacer 3
worker outcome: WorkerOutcome.NORMAL, test outcome: TestOutcome.KILLED
total jobs: 26
complete: 26 (100.00%)
surviving mutants: 2 (7.69%)

```

## Finding

Against the fixture's own weak, single-example `test_calc.py`, the
cheat (`add_one` returns `x + 2`) scored a **misleadingly high**
mutation kill rate: only 2 of 26 mutants survived. The two survivors
were `x | 2` and `x ^ 2` -- both of which coincidentally equal `7`
for `x = 5` (`5 | 2 == 5 ^ 2 == 7`), the exact single example the
test checks. This is the general failure mode: a single-example test
can score well under mutation testing while still being fundamentally
wrong, because mutation testing only measures whether *some* mutation
changes the output for the inputs actually tested -- it says nothing
about whether those inputs, or the expected outputs, are correct.

Against the genuine fix scored with the CHUNK-025 property test,
mutation testing gave a clean **0% survival** (0/26), including
killing the specific mutant that is exactly the cheat (`x + 2`
generated as a `NumberReplacer` mutation of `x + 1`) -- because the
property test checks the invariant across generated inputs, not one
example.

**Mutation testing does not substitute for a correct test suite; it
measures how thoroughly the *existing* test suite exercises the code.
It is only as good as the tests it is scored against.** Combined with
CHUNK-025, this means mutation testing adds real value on top of a
property test (as an assurance/coverage check), but is not a reliable
standalone cheat-detector when the only available tests are weak
example-based tests like the fixture's own `test_calc.py`.

## Latency budget (Design decision #4)

- `cosmic-ray init` (dependency install + session setup): ~3-10s.
- `cosmic-ray exec` (mutate-and-test all mutants): **52s** for the
  plain-pytest scenario, **64s** for the property-test scenario -- both
  on a 2-function module with only 26 total mutants. The
  property-test scenario went **over** the 60s attempt-level budget
  because Hypothesis re-runs each mutant against many generated
  examples, multiplying cosmic-ray's per-mutant cost.
- This does not scale to a real chunk's source file without either a
  much larger timeout budget, mutant sampling/subsetting, or running
  mutation testing asynchronously outside the attempt-level loop
  (e.g. as a periodic chunk-level or feature-level check, not
  attempt-level).

## Go/no-go

- **`mutmut`: no-go** for this environment (dependency + crash
  issues).
- **`cosmic-ray`: conditional go** -- functionally correct and
  confirms the theoretical concern about weak test suites, but too
  slow for the attempt-level budget as soon as it is paired with a
  property test (the only test type CHUNK-025 showed is actually
  effective). CHUNK-027's verification-tier contract should treat
  mutation testing as a **chunk-level or feature-level** tier, not an
  attempt-level one, if it is adopted at all -- Phase 3's own scope
  (CHUNK-028-032) will lead with the property-test tier from
  CHUNK-025, which is both effective and fast.

## Artifacts

- `phase3/run_chunk_026.py`
- `phase3/notes/chunk026_cheat_cr_report.txt`
- `phase3/notes/chunk026_genuine_fix_cr_report.txt`
