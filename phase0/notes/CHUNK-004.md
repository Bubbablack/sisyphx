# CHUNK-004 — Sandbox + scoped-write guard

**Status:** done
**Date:** 2026-08-08

## Method

Scratch repo (`phase0/scratch/`) with a `.devin/config.local.json` granting a
narrow permission scope, tested under `--sandbox --permission-mode autonomous`
(the only permission mode sandbox supports, per docs).

## Results

### Test 8 — write scope, three targets in one session

Config: `{"permissions": {"allow": ["Write(allowed/**)"]}}`. Asked Devin to
attempt, in order: (1) write inside `allowed/`, (2) write inside `not_allowed/`
(not covered by the grant), (3) write to an absolute path outside the
workspace (`/tmp/...`).

| Target | Result (independently verified on disk, not just self-report) |
|---|---|
| `allowed/inside.txt` (in grant, in workspace) | **SUCCESS** |
| `not_allowed/inside.txt` (NOT in grant, but in workspace) | **SUCCESS** |
| `/tmp/sisyphx_sandbox_outside_test.txt` (outside workspace entirely) | **BLOCKED** — sandbox denied with "Operation not permitted"; scope-elevation request also rejected since non-interactive |

**Finding: the sandbox's writable-path default is "workspace directory PLUS
granted scopes," and the workspace-directory default wins for everything
inside it.** A narrower `Write(allowed/**)` grant does **not** restrict writes
to other paths *within* the same workspace — sandbox only enforces the
*outer* boundary (workspace vs. everything else on the filesystem), not
fine-grained sub-paths inside a project. This means **sandbox alone cannot
enforce `permitted_paths` at chunk granularity** — it can only guarantee "this
session never touches another project or system files." Confirms design
decision #6 (two independent guard layers) was the right call, and clarifies
*why*: sub-path enforcement has to come from `PreToolUse` hooks (CHUNK-005) or
post-hoc diff checking, not from sandbox permission scopes.

### Test 9/10 — shell exec under sandbox+autonomous

First attempt (no `Exec()` grant): asked it to run `sleep 60` under
`--sandbox --permission-mode autonomous`. **Rejected**, even though the docs
describe Autonomous as auto-approving shell commands:

> Tool execution was rejected: Running in non-interactive mode. Use
> `--permission-mode dangerous` to auto-approve all tools.

Added `"Exec(**)"` to the allow list and retried with a simple `echo` command
— **succeeded**, file written and independently verified. **Finding: sandbox
+ autonomous mode does not reliably auto-approve shell exec non-interactively
on its own; it needs an explicit `Exec()` allow rule in config** (contradicts
the docs' "auto-approved, contained by sandbox" framing, at least for
non-interactive `-p` sessions — possibly that framing only holds for
interactive sessions).

### Test 11 — re-attempt the CHUNK-003 orphan question under sandbox

With the same config (`Write(allowed/**)` + `Exec(**)`), re-ran the
write-then-`sleep 60`-then-write prompt used in CHUNK-003. This time the
**write step itself was rejected** as needing approval — inconsistent with
Test 8, where an equivalent write (to a different, non-`allowed/` path)
succeeded without issue moments earlier under what should be the same
permission logic.

**Finding: sandbox+autonomous's non-interactive approval behavior is not
fully deterministic across otherwise-similar prompts.** This is a more
important finding than the orphan question it was meant to answer — it means
sandbox+autonomous is **less predictable for unattended automation** than
plain `--permission-mode bypass` (which has been 100% consistent across every
test so far). The original CHUNK-003 orphan question (does sandbox change
grandchild-process cleanup on kill?) remains genuinely **unresolved** — we
never got a clean run under sandbox that both reached the `sleep 60` step and
was then killed. Not worth burning more invocations chasing it right now.

## Conclusion and decision for the loop

1. **`--sandbox --permission-mode autonomous` is not the right default for
   Phase 1's loop.** It requires extra config (`Exec()` allow rules) just to
   do basic work, doesn't restrict sub-paths within a workspace anyway (so it
   wouldn't fully deliver `permitted_paths` enforcement even if we used it),
   and showed inconsistent approval behavior across near-identical prompts in
   this testing.
2. **Phase 1 uses plain `--permission-mode bypass`** (per CHUNK-001 Test 5) —
   simple, and 100% consistent across every test run so far. We accept the
   reduced OS-level containment for now.
3. **Real enforcement of `permitted_paths`/`prohibited_changes` will come
   from `PreToolUse` hooks (CHUNK-005)** and SisyphX's own independent
   post-hoc git-diff guard checks — not from sandbox permission scopes. This
   updates design decision #6: hooks + independent checks are the mechanism;
   sandbox is optional future hardening for the *outer* workspace boundary
   only, worth revisiting once Phase 1 is stable, not a Phase 1 dependency.
4. The process-orphan-under-sandbox question stays open (carried forward,
   low priority — plain bypass mode's orphan behavior is already documented
   in CHUNK-003 and that's what we're actually using).

## Raw artifacts

- `test8_stdout.txt` (three-target write scope test)
- `test9_stdout.txt`, `test10_stdout.txt` (exec rejection / Exec() fix)
- `.devin/config.local.json` evolution kept in scratch repo git history
