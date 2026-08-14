# CHUNK-045 — Real run: chunk 001.001.001 driven through `loop.py` against the real Illima Energy repo

**Status:** done
**Date:** 2026-08-14
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12; target: `illima-dashboard` (Laravel 11 + Filament v3, PHP 8.2 via Docker).

## Question

Can `phase1/loop.py`, unmodified except for CHUNK-044's tamper-guard
widening, drive a real, already-scoped chunk (001.001.001, from
`experiments/planner/`) to completion against a real client codebase?

## First attempt: a real, significant integration bug

```
python3 phase1/loop.py --repo .../illima-dashboard --task ... \
    --verify 'docker run --rm -v "$(pwd)":/app -w /app illima-php:8.2 php artisan test' \
    --permit "app/Models/Customer.php" --permit "database/migrations/**" \
    --permit "tests/**" --permit "phpunit.xml" --max-iterations 3 ...
```

Iteration 1: the agent produced a sensible `Customer` model, migration, and
`tests/Unit/CustomerTest.php` -- but the loop stopped immediately with
`STOPPING: tamper guard triggered by
['illima-dashboard/tests/Unit/CustomerTest.php']`, exit 4.

**Root cause**: CHUNK-043's git init was done at the *Illima_Energy*
project root, one level above `illima-dashboard/`. `loop.py` runs every
git command with `cwd=repo` (`illima-dashboard`), but since that directory
is a *subdirectory* of the actual git toplevel (`Illima_Energy`), `git
status` reports paths relative to the toplevel, not relative to `repo`.
The new, entirely legitimate, explicitly `--permit`ted test file was
reported as `illima-dashboard/tests/Unit/CustomerTest.php` instead of
`tests/Unit/CustomerTest.php`, which never matched the `--permit` patterns
(written relative to `illima-dashboard`) -- so the tamper guard fired on
a fully permitted change.

This also would have broken the Docker verification command outright: its
`-v "$(pwd)":/app` mount requires `cwd` to literally *be*
`illima-dashboard` for the mount to point at the right directory.

### Fix

1. **Restructured the target project** (not a SisyphX code change):
   `illima-dashboard` now has its own separate git repository, matching
   SisyphX's own established convention of gitignoring nested/embedded
   repos (CHUNK-012's decision) rather than nesting one repo inside
   another. The outer `Illima_Energy` repo (planning docs,
   `experiments/planner/`) now excludes `illima-dashboard/` entirely.
2. **Hardened `loop.py` itself** (a real framework fix, not just an
   operational note): `run_loop()` now checks `git rev-parse
   --show-toplevel` at startup and fails fast (exit 1, clear error
   message) if `--repo` is not itself the git toplevel, instead of
   silently proceeding with broken guard behavior. 3 new tests
   (`phase1/tests/test_run_log.py`) cover: no git repo at all, `--repo` as
   a subdirectory of a larger repo, and the normal (accepted) case.

The agent's first-attempt work (Customer model, migration, test) was
reviewed and found sound -- discarded only because of the framework/repo
mismatch, not because it was wrong. See git history in `illima-dashboard`
for the second, successful attempt's near-identical result.

## Second attempt: real success

Same command, `illima-dashboard` now its own git toplevel:

```
=== iteration 1/3 ===
    agent_exit=0 timed_out=False status={'outcome': 'done', ...} 
    verify_exit=0 passed=True kind=verify-pass sha=0801edc1 committed=True
=== PASSED on iteration 1 ===
```

- `app/Models/Customer.php`, a migration
  (`database/migrations/2026_08_14_132001_create_customers_table.php`),
  and `tests/Unit/CustomerModelTest.php` (2 tests) added, committed as
  `SisyphX loop iteration 1 [PASS]` (author `SisyphX Loop`, per CHUNK-019's
  commit-integrity convention).
- Independently re-verified outside the loop (not trusting `loop.py`'s own
  report, per this project's standing principle):
  `docker run --rm -v "$(pwd)":/app -w /app illima-php:8.2 php artisan
  test` → **14 passed, 45 assertions** (up from the CHUNK-043 baseline's
  12 passed / 42 assertions) -- exactly +2 tests / +3 assertions from the
  new file, zero regressions in the 6 pre-existing test files.
- Reviewed the actual diff by hand: a plain, idiomatic Eloquent model, a
  correctly-shaped migration (unique `client_id`, nullable `division_id`/
  `email`, timestamps), and a test covering both the expected shape
  (`assertDatabaseHas`) and the uniqueness constraint
  (`expectException(QueryException::class)`) -- matching the chunk's
  stated acceptance criteria exactly, nothing extra, nothing missing.
- Updated the real ticket (`experiments/planner/tickets/001.001-customer-crud/chunks/001.001.001.md`
  → `status: passed`; parent ticket `001.001-customer-crud.md` →
  `state: developing`), committed to the Illima Energy repo separately
  from the dashboard's own commit.

## Finding

The pipeline works end-to-end on a real, production client codebase, in a
different language (PHP) than every prior phase (Python), using the
project's own existing Docker-based test infrastructure completely
unmodified. The one real blocker was not a language-adapter gap -- it was
a repository-structure precondition `loop.py` had silently assumed but
never validated, discovered exactly the way this project's methodology
intends: by actually running it for real, not by inspection. It is now a
hard, tested precondition rather than an implicit assumption.

## Verification

- `phase1/tests/test_run_log.py`: 3 new tests for the toplevel
  precondition check. Full suite: `uv run pytest` → **117 passed** (114
  before this chunk + 3 new).
- Real run: iteration 1 passed on the second (corrected) attempt;
  independently re-verified test count/assertions and reviewed the actual
  diff by hand.

## Artifacts

- `phase1/loop.py` (toplevel precondition check added)
- `phase1/tests/test_run_log.py` (3 new tests)
- Illima Energy repo: `illima-dashboard` commit `0801edc1` ("SisyphX loop
  iteration 1 [PASS]"); outer repo commits `ba8fab3` (untrack
  illima-dashboard) and `c6ee328` (ticket status updates)
