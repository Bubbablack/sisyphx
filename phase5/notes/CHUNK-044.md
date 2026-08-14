# CHUNK-044 — Spike: PHP/Laravel-aware tamper guard + Docker-based verification

**Status:** done
**Date:** 2026-08-13

## Question

Does `phase2/tamper_guard.py` recognize PHPUnit/Composer/Laravel
conventions, and does the project's Docker-based `php artisan test`
command work unmodified as `loop.py`'s `--verify` command?

## What was done

1. Widened `PROTECTED_PATTERNS` in `phase2/tamper_guard.py` with PHP
   equivalents (`*Test.php`, `tests/*.php`, `composer.json`,
   `composer.lock`, `phpunit.xml`, `phpunit.xml.dist`) alongside the
   existing Python-specific ones, per Design decision #3 (verification
   adapters configurable per-project, not hardcoded to one language). This
   is a widening of an already-mixed list (it already had ecosystem-
   agnostic entries like `Makefile`), not a new configuration mechanism.
2. Added 10 new tests to `phase2/test_tamper_guard.py` covering the new
   PHP patterns.

## Two real, previously-hidden bugs found while adding this coverage

Both were latent in `phase2/tamper_guard.py` since CHUNK-020 (Phase 2) and
applied to Python too — neither is PHP-specific, they were only surfaced
now because the new PHP tests exercised code paths the original Python
tests never happened to hit.

### 1. `dir/**/*.ext` never matches files directly under `dir/`

`fnmatch`'s `*` already crosses `/` (unlike shell glob), so a *single*
star (`tests/*.py`) already matches at any depth, including
`tests/sub/test_foo.py`. But `tests/**/*.py` (the original pattern)
contains a **literal** `/` between the two star groups, which `fnmatch`
requires to be a real `/` character in the path -- so it only ever matched
files at least one directory *below* `tests/`, and silently never matched
a file placed directly in `tests/` itself. Confirmed empirically:

```python
fnmatch.fnmatch('tests/ExampleTest.php', 'tests/**/*.php')          # False
fnmatch.fnmatch('tests/Feature/ExampleTest.php', 'tests/**/*.php')  # True
fnmatch.fnmatch('tests/ExampleTest.php', 'tests/*.php')             # True
fnmatch.fnmatch('tests/Feature/ExampleTest.php', 'tests/*.php')     # True
```

Fixed by changing `tests/**/*.py` (and the new PHP equivalent) to
`tests/*.py` / `tests/*.php` -- functionally equivalent for the nested
case and now also correct for the direct case.

### 2. New files inside a brand-new directory were invisible to every check

`_changed_files()` used `git status --porcelain` without
`--untracked-files=all`. Git's default porcelain behavior **collapses an
entirely untracked directory into one line for the directory itself**
(`?? tests/`) instead of listing the files inside it. Since `tests/` in
this project's own test fixtures (and in any real chunk where an agent
creates a brand-new `tests/` subdirectory, e.g. Laravel's
`tests/Unit/`/`tests/Feature/` layout for a project that didn't have one
yet) did not previously exist as a tracked path, every file the agent
created inside it was **completely invisible to the tamper guard** --
not flagged as protected, but also not counted as a permitted change; it
simply never appeared in the scan at all. Confirmed with a minimal
reproduction (`git status --porcelain` shows `?? tests/`;
`--untracked-files=all` shows `?? tests/test_example.py`). Fixed by adding
`--untracked-files=all` to the `git status` invocation.

**This is a more significant finding than the PHP pattern gaps that
motivated looking here.** It means the tamper guard has had a real blind
spot since Phase 2 for any chunk where the agent's first file in a new
subdirectory happens to be a protected one (e.g. an agent-created
`tests/` directory whose first file is itself a test) -- the previous 66+
passing tests never happened to exercise "a brand-new subdirectory" as
the site of a protected-pattern violation.

## Docker-based verification

Ran the project's actual verify command exactly as `loop.py` would invoke
it (`subprocess.run(cmd, shell=True, cwd=repo, ...)`):

```python
subprocess.run(
    'docker run --rm -v "$(pwd)":/app -w /app illima-php:8.2 php artisan test',
    shell=True, cwd=repo, capture_output=True, text=True, timeout=120,
)
```

- Full suite: exit 0, 12 passed / 42 assertions, ~9s wall time. `$(pwd)`
  correctly resolves inside the `shell=True` subprocess to the repo path
  `loop.py` passes as `cwd` -- no quoting issues.
- Targeted single-file invocation
  (`php artisan test tests/Unit/CustomerModelTest.php`, matching chunk
  001.001.001's own `Verification` section) against a file that doesn't
  exist yet: exit **2**, clear `Test file "..." not found` message -- a
  good, unambiguous failure signal for `loop.py`'s classification, exactly
  analogous to pytest's behavior on a missing test path.

## Finding

The Docker-based verification command works completely unmodified as
`loop.py`'s `--verify` argument -- no changes needed to `loop.py` itself.
The only real framework changes needed were in the tamper guard, and both
turned out to be genuine, previously-undetected bugs rather than missing
PHP-specific knowledge, which is itself a valuable (if unplanned) result
of extending real coverage to a second language.

## Verification

- `phase2/test_tamper_guard.py`: 16 tests (6 new Python-focused
  regression tests + 10 new PHP-focused tests). Full SisyphX suite:
  `uv run pytest` → **114 passed** (104 before this chunk + 10 new).
- Real Docker verification run against the actual Illima Energy repo
  (read-only, no changes made to that repo in this chunk).

## Artifacts

- `phase2/tamper_guard.py` (PROTECTED_PATTERNS widened, two bugs fixed)
- `phase2/test_tamper_guard.py` (16 tests, up from 6)
