# CHUNK-048 — Review-marker startup precondition in `loop.py`

**Status:** done
**Date:** 2026-08-16
**Deps:** 047

## What was built

- `phase2/review_marker_check.py` — promotes CHUNK-047's spike
  (`phase6/run_chunk_047.py`) into a real module: `find_review_markers(root)`
  (list of `(path, line, text)` matches) and `check_review_markers(repo)`
  (`(ok, offending)` tuple, matching `tamper_guard.scan_tamper`'s existing
  return-shape convention). Same source-extension filter, same
  comment-leader-adjacent regex, same repo-wide (non-`permitted_paths`-scoped)
  walk as the confirmed spike design.
- `phase1/loop.py` wires it in as a **one-shot startup precondition**,
  checked immediately after the existing `--repo`-toplevel check
  (CHUNK-045's pattern) and before any state directory / event store /
  iteration setup. On a hit, it logs every offending `path:line: text` and
  returns exit code `1` — the same "fail fast before anything starts"
  exit code as the toplevel check, not a new `FailureSignature` kind and
  not routed through the recovery ladder, per PLAN.md's Phase 6 design.
- `phase2/test_review_marker_check.py` — 8 unit tests covering the module
  directly, reusing CHUNK-047's five fixture shapes (clean,
  genuine-comment-marker, genuine-trailing-marker (PHP), string/docstring
  false positive, markdown-doc false positive) plus `.git`/`.agent-state`
  exclusion and multi-file reporting.
- `phase1/tests/test_run_log.py` — 2 new integration tests: a real marker
  present stops `run_loop` at exit 1 with no commit and no log file
  written (confirming zero agent invocation happens); a marker present
  only in a `.md` file does not block a run.

## Verify

- `uv run pytest -q` — full suite: **119 passed** (up from 117 after
  CHUNK-045/046; +2 in `test_run_log.py`, +8 in the new
  `test_review_marker_check.py`, net +10 minus prior double count noted in
  CHUNK-045's log — the authoritative number is this run's `119 passed`).
- **Real manual run** (per acceptance criteria): a fresh scratch git repo
  with a genuine `# REVIEW: ...` marker in `calc.py`, invoked via
  `python3 phase1/loop.py --repo <scratch> --task <task> --verify true
  --max-iterations 1` from the actual CLI (not the test harness). Output:

  ```
  === ERROR: unresolved REVIEW: markers found -- refusing to start ===
      calc.py:2: # REVIEW: off-by-one risk if x is already at int max -- fix?
      Resolve these (see AGENTS.md's REVIEW: convention) before starting a run -- either manually, or as an ordinary chunk through loop.py.
  ```

  Exit code `1`, confirmed before any agent iteration ran (no
  `.agent-state/` directory was created at all).

## Notes

- Resolution of markers is explicitly out of scope here, per PLAN.md:
  handled either manually or as an ordinary chunk run through `loop.py`
  (whose own `--verify` command could invoke
  `phase2/review_marker_check.py` as a plain script if a CLI entry point
  is ever wanted — not added now, since nothing yet needs it).
- A Devin CLI skill for on-demand resolution remains explicitly deferred
  to the user, per PLAN.md's 2026-08-15 note — not built here.
