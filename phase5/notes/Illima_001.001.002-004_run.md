# Illima 001.001.002–001.001.004 — real run notes

**Date:** 2026-08-16
**Target:** `/Users/stini/Ai_Dev_Home/Projects/Illima_Energy/illima-dashboard`
**Chunks driven:** `001.001.002` (CustomerResource), `001.001.003` (redirect-after-save), `001.001.004` (test-data robustness)
**Final state:** all three chunks `passed`; ticket `001.001` in `testing`; full suite 28 passed / 106 assertions.

## What happened

1. `001.001.002` passed on iteration 1. It built the staff `CustomerResource` with list, create, edit, delete, soft delete, pagination, and 12 feature tests.
2. `## Manual verification` surfaced a real UX gap: after save, create redirected to the new record's edit page and edit stayed on the form. The automated suite did not catch this.
3. `001.001.003` was recorded *before* any code changed, then driven through `loop.py`. It added `getRedirectUrl()` to `CreateCustomer` and `EditCustomer` and two redirect assertions. Passed on iteration 1.
4. While trying to log in for manual verification, the `users` table was found empty. Re-seeding restored `admin@illima.test` / `password`.
5. `001.001.004` was recorded to fix the test-suite / manual-data collision. `CustomerFactory` used a static counter starting at `CUST-0001`, which immediately collided with any manually created customer (and with `CustomerModelTest`'s hard-coded `client_id`s).
6. `001.001.004` loop failed: the agent fixed `CustomerFactory` and `CustomerResourceTest` on iteration 1, but `CustomerModelTest` also needed updating and the chunk had not permitted it. Iteration 1 timed out; iteration 2 tried to edit the unit test and the tamper guard stopped the run.
7. The missing permit and a subtle `assertCanSeeTableRecords` / `assertCountTableRecords` interaction in the pagination test were resolved manually; the full suite re-ran and passed.

## Lessons

- **The `## Manual verification` field is not a decoration.** On the second UI chunk ever run through the system it caught a real, loop-invisible UX issue that the full PHPUnit suite missed.
- **A chunk's `permitted_paths` must include every protected test file the fix might touch.** The agent will not reliably guess which tests are off-limits, and guessing wrong trips the tamper guard. `CustomerModelTest.php` was protected and not permitted; the fix needed it.
- **Test data and dev manual data must coexist or be isolated.** Because `phpunit.xml` does not set `DB_DATABASE` to a separate test database, the same `database/database.sqlite` is used for both `php artisan test` and the running dev server. A factory that emits predictable `client_id`s collides with manual records, and vice versa.
- **Predictable test `client_id`s are fragile.** The original `CustomerFactory` used a process-local static counter (`CUST-0001`, `CUST-0002`, ...). A fresh test process starts the counter at 0 and immediately collides with any pre-existing customer that happens to use the same numbering.
- **Sorting in PHP vs SQLite can diverge.** `assertCanSeeTableRecords` on a paginated Livewire table uses the DB's `ORDER BY`; the test computed `firstPage` with PHP's `Collection::sortBy`. With random company names the two can disagree. Using predictable `Customer 01`–`Customer 15` names and a per-run search prefix fixed the test.
- **Pushing `PLAN.md` from a long-running local session can produce a merge conflict.** The remote had an older merge commit that the local branch had never integrated. Resolving with `git checkout --ours PLAN.md` worked, but it's a smell that the tracker file is both a local status display and a shared artifact.

## Areas of improvement

1. **Test / dev database isolation.** Add a `DB_DATABASE` override in `phpunit.xml` pointing to a separate file or `:memory:`, and consider adding `RefreshDatabase` or `DatabaseMigrations` to `tests/TestCase.php`. This is the cleanest way to let manual verification data and the test suite coexist without namespace games.
2. **Prompt / chunk `permitted_paths` preflight.** The planner prompt or a small pre-run check could warn when a fix is likely to touch protected files that are not in the chunk's `permitted_paths`. The loop should not be the first place this is discovered.
3. **Factory / test data hygiene.** Make all tests that create records use run-unique values by default, or provide a test helper that does so. The current mix of explicit `client_id`s and factory `client_id`s is easy to get wrong.
4. **Manual verification namespace convention.** If the dev and test DB stay shared, document that the test suite reserves a `CUST-TEST-...` namespace and manual users should not create customers with that prefix.
5. **Why was `users` emptied?** The `admin@illima.test` user was missing at the start of manual verification. The seeder had been run earlier, so the table was emptied by something after that. This is still not fully diagnosed; a future run should audit this before assuming the seeder is enough.
6. **Loop commit history cleanup.** The repo now contains a `SisyphX loop iteration 1 [fail]` commit (`fdb78e1`). This is honest, but noisy for a public history. Consider whether the loop should be allowed to squash or fast-forward its own failed iterations before final push, or whether `[fail]` commits should be a deliberate audit trail.
7. **Prompt generation still manual.** `planner.py` from `experiments/planner/` does not exist; prompts were hand-copied from chunk files. Implementing the prompt generator would reduce copy/paste errors and keep the chunk format as the single source of truth.
