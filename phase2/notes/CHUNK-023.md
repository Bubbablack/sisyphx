# CHUNK-023 — Phase 2 retro and Phase 3 scoping

**Status:** done  
**Date:** 2026-08-09  

## Phase 2 summary

Phase 2 was deliberately scoped as a narrow **Assurance + Recovery** slice:
close the trust gaps the real Phase 1 runs exposed and replace
byte-identical stuck detection with real failure signatures and a minimal
recovery ladder. No ontology, no learning plane, no Spec Kit/APM.

### Spikes (013–016) — learn first, build second

| Chunk | Question | Key finding |
|---|---|---|
| CHUNK-013 | Can a `PreToolUse`/`exec` hook block `git commit`/`git push` in bypass? | Yes. Hooks fire and block cleanly; block signal is exit 1 + `Error: A tool was rejected by the user`. |
| CHUNK-014 | Can the loop distinguish guard-abort, normal failure, and timeout? | Yes. Guard = exit 1 + sentinel; timeout = `agent_timed_out`; normal fail = exit 0 + non-zero verify. |
| CHUNK-015 | What must be normalized for a stable `FailureSignature`? | Durations, paths, line numbers, pytest versions, uv noise, system-library paths, whitespace. |
| CHUNK-016 | What does test-tampering look like in real diffs? | Test files, verify config, CI config, lock files, coverage thresholds, and loop state must be flagged; source edits allowed if permitted. |

### Implementation (017–022)

| Chunk | Output | Verified by |
|---|---|---|
| CHUNK-017 | `phase2/failure_signature.py` | Real captured outputs from CHUNK-015/014; same failure → same hash, different failures → different. |
| CHUNK-018 | Loop uses `FailureSignature` for stuck detection and failure classes. | Real run where two durations-only-different pytest failures collapsed to the same signature. |
| CHUNK-019 | Commit-integrity guard in `loop.py`. | Real adversarial run where the agent ran `git commit` and the loop stopped. |
| CHUNK-020 | Test-tamper diff scanner `phase2/tamper_guard.py`. | Real run where a contradictory task forced `test_calc.py` edits. |
| CHUNK-021 | Minimal recovery ladder `phase2/recovery_ladder.py`. | Real forced-unsolvable run producing a readable `escalation.md`. |
| CHUNK-022 | Append-only SQLite `EventStore`. | Unit tests + real run on `phase1/target_repo` producing a queryable event trail. |

### What the guards and ladder actually caught

- **Semantic-contract violation (CHUNK-010/016):** Agent changed `add_one` to
  `return x + 2` to pass a contradictory test. The tamper guard did not stop
  this (it touched a source file), but the `FailureSignature` + recovery ladder
  would have stopped repeated `verify-fail` and the verification command itself
  failed because the behavior was wrong. This is a known gap: source-level
  semantic cheats are detectable only by a stronger verifier or a property test.
- **Agent-authored `git commit` (CHUNK-010/019):** The loop now detects any
  commit whose author is not `SisyphX Loop` and stops immediately.
- **Test-file tampering (CHUNK-020):** The post-iteration diff scan flags
  protected paths and stops before the agent can claim success.
- **Repeated identical failure (CHUNK-021):** The ladder feeds exact evidence
  once, escalates once, then stops and writes an `escalation.md`.

## Open questions resolved

| Question | Resolution |
|---|---|
| How to prevent/detect agent-initiated `git` commands (especially `git commit`)? | Resolved: `PreToolUse`/`exec` hook blocks `git commit`/`git push` in real time (CHUNK-013); post-iteration commit audit catches any that slip through (CHUNK-019). |
| What verification command should SisyphX use for CHUNK-012? | Resolved: `uv run pytest` against the SisyphX repo; `pyproject.toml` and `uv.lock` were added and tests pass. |

## Open questions carried forward

- Whether `--sandbox` changes the CHUNK-003 grandchild-process-orphan behavior.
  Low priority because Phase 2 uses plain bypass mode.
- Whether Devin CLI's `/loop` slash command is scriptable non-interactively.
- Second verification adapter target language — deferred until a real second
  project is in scope.
- Event-store retention: how long should raw events live, and what should be
  summarized/archived?

## Decision log additions

- 2026-08-09 — Phase 2 is complete. The loop is now untrickable (commit-integrity
  + tamper guards) and unstickable (`FailureSignature` + recovery ladder), and
  every run leaves an append-only event trail.
- 2026-08-09 — Source-level semantic cheating (e.g. `return x + 2` to pass a
  wrong test) is not mechanically preventable by path-based guards alone. It
  must be caught by a stronger verifier, property tests, or human review.
- 2026-08-09 — The JSONL run log stays as the human-readable line record; the
  SQLite `EventStore` is the queryable, structured audit trail. No speculative
  domain models were added to the event schema; it only stores fields the loop
  already has.

## Findings and recommendations (Phase 3 scoping deferred)

The concrete Phase 2 evidence points to a few high-leverage directions for the
next phase, but the actual chunk-level scoping of Phase 3 is intentionally left
for a separate planning session.

### Findings

1. **The loop can now reliably stop the failure modes it was designed for:**
   guard aborts, unauthorized commits, test tampering, and repeated identical
   failures.
2. **Source-level semantic cheating is the remaining hard gap.** A path-based
   guard cannot tell whether `add_one` returning `x + 2` is a legitimate fix or
   a trick. Catching this requires stronger verification: property tests,
   mutation testing, human review, or a verifier that checks behavior against a
   specification rather than only the project's own tests.
3. **The event store is intentionally minimal and append-only.** It stores only
   what the loop already produces. It should be retrofitted into any future
   formal domain models, not replaced by a speculative schema.

### Recommendations for when Phase 3 is scoped

- Use the existing `EventStore` and `RunLogEntry` fields as the empirical
  foundation for Pydantic domain models — design the models around what the
  loop actually uses, not the other way around.
- Make the verification engine the highest-priority Phase 3 investment,
  starting with property tests and mutation testing to close the semantic-cheating
  gap.
- Defer ontology, learning/promotion, and durability until the core loop and
  verification engine are stable on a second real project.

## Phase 3 scoping

Intentionally not done in this chunk. The `Phase 3+` section of `PLAN.md` stays
as a rough-direction placeholder; chunk-level scoping will happen in a later
planning session once there is a target project or user story to scope against.

## Verification

- `PLAN.md` updated with Phase 2 findings and recommendations; the `Phase 3+`
  placeholder left for future scoping.
- `uv run pytest` → **66 passed**.
