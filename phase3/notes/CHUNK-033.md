# CHUNK-033 — Phase 3 retro and Phase 4 scoping

**Status:** done
**Date:** 2026-08-13

## Phase 3 summary

Phase 3 was scoped as a narrow **verification-engine** slice: close the one
hard gap Phase 2's retro (CHUNK-023) identified — a path-based guard cannot
tell whether a source change is a legitimate fix or a semantic cheat that
only satisfies a contradictory test. No domain models, no ontology, no
learning/promotion, no Spec Kit/APM. Still self-hosting on SisyphX's own
repo.

### Spikes (024–027) — learn first, build second

| Chunk | Question | Key finding |
|---|---|---|
| CHUNK-024 | Can CHUNK-010's semantic cheat be reproduced as a permanent fixture? | Yes, twice, consistently. `phase3/target_repo_semantic_cheat/` is now tracked, stable ground truth (unlike Phase 1/2's gitignored throwaway repos). |
| CHUNK-025 | Can a Hypothesis property test catch the cheat? | Yes — an 11-line property test failed on the cheat and passed on a genuine fix, the exact opposite of the fixture's own contradictory example test. |
| CHUNK-026 | Which mutation-testing tool, if any, fits the attempt-level budget? | `mutmut` rejected (dependency + crash issues in this environment). `cosmic-ray` works but is too slow (52–64s) for attempt-level use once paired with a property test, and — more importantly — gave a *misleadingly high* kill rate against a weak example-based test, proving mutation testing measures test-suite thoroughness, not correctness. |
| CHUNK-027 | How should `loop.py` invoke a second verification tier? | At most two tiers, same execution primitive as tier 1, tier 2 opt-in and only runs if tier 1 passes; a tier-1-pass/tier-2-fail is a new, distinct `verify-tier2-fail` failure kind, not a misleading pass. |

### Implementation (028–032)

| Chunk | Output | Verified by |
|---|---|---|
| CHUNK-028 | `phase3/verification_tiers.py` | 7 unit tests + real run against the CHUNK-024 fixture reproducing CHUNK-027's demo exactly. |
| CHUNK-029 | `verify-tier2-fail` failure kind in `phase2/failure_signature.py` + recovery-ladder integration | 9 new tests using real CHUNK-025 artifacts; found and fixed a real Hypothesis-output normalization gap along the way. |
| CHUNK-030 | `EventStore.append_verify_result()` | 2 new tests + a real run that reopened the SQLite file fresh and queried the tier result back. |
| CHUNK-031 | `loop.py` wires tier 2 in, opt-in per chunk | 4 new tests (all existing tests pass unmodified) + a **real live-agent adversarial run**. |
| CHUNK-032 | Confirmed both sides with real live-agent runs | Cheat case (reused CHUNK-031's run) + a fresh genuine-fix case, both with a live Devin CLI agent, not scripted stand-ins. |

### What Phase 3 actually caught, live

The strongest evidence in this phase is CHUNK-031/032's real adversarial
run: given the exact CHUNK-024 fixture and task, a live Devin CLI agent
**first refused to cheat**, explicitly stating the test was contradictory,
then on a retry (fed the exact tier-1 failure evidence) **produced the
exact CHUNK-010 cheat** (`add_one` → `return x + 2`). Tier 1 passed; tier 2
(the property test) caught it in real time, producing the new
`verify-tier2-fail` kind, and the loop never recorded a false pass. A
second live-agent run on a genuine, non-contradictory bug confirmed the new
tier adds zero friction to correct work — it passed both tiers on the
first attempt.

## Open questions resolved

| Question | Resolution |
|---|---|
| Can source-level semantic cheating (CHUNK-010/023's carried-forward finding) be mechanically caught? | Yes, for chunks where a property test encoding the real contract is supplied — resolved empirically with two real live-agent runs (CHUNK-031/032), not just a scripted demonstration. |
| Which mutation-testing tool fits this environment/budget? | Neither cleanly at attempt-level: `mutmut` is a hard no-go here; `cosmic-ray` works but only fits a chunk/feature-level cadence, not attempt-level, and needs a strong test (i.e. a property test) to be meaningful at all — making it a secondary check on top of property tests, not a substitute. |

## Open questions carried forward

Unchanged from Phase 2 (CHUNK-023), still not touched by Phase 3:

- Whether `--sandbox` changes the CHUNK-003 grandchild-process-orphan
  behavior. Low priority, still using plain bypass mode.
- Whether Devin CLI's native `/loop` slash command is scriptable
  non-interactively.
- Second verification adapter target language — still deferred until a real
  second project is in scope.
- Event-store retention — how long should raw events live, and what should
  be summarized/archived? Now more relevant since `verify_tier2_output` adds
  another potentially large text blob per event.

New from Phase 3:

- `experiments/planner/` (the markdown ticket+chunk experiment) remains
  completely untouched — zero tickets or spikes created. It did not feed
  Phase 3's own scoping or execution, per the 2026-08-13 decision. Whether
  it's still wanted is an open question for whoever scopes the
  specification pipeline in Phase 4+.
- Property-test authoring is still a human (or agent-in-planning-role)
  responsibility per chunk — CHUNK-025 found it cheap once the real
  contract is known, but nothing in Phase 3 generates that contract
  automatically. A future phase could explore whether an agent can
  reliably author property tests *from* an acceptance-criteria spec, but
  this was not attempted here.

## Decision log additions

- 2026-08-13 — Phase 3 is complete. The loop now has a real, live-agent-
  confirmed second verification tier (`phase3/verification_tiers.py`, wired
  into `loop.py` as `--verify-tier2`) that catches the exact semantic-cheat
  pattern CHUNK-010 first found, with zero added friction for genuine fixes.
- 2026-08-13 — `mutmut` is not viable in this environment (dependency-wheel
  friction + an internal crash); `cosmic-ray` works but is a chunk/feature-
  level tool, not an attempt-level one, and only adds value on top of an
  already-strong test (e.g. a property test) — it is not a substitute for
  one. Mutation testing is deferred as an optional, non-required addition
  for Phase 4+.
- 2026-08-13 — Building an honest "same failure twice" test with two
  genuinely independent real captures (not the same file reused) is what
  surfaced the real Hypothesis-output normalization gap in CHUNK-029. This
  reinforces the Phase 0/2 methodology of insisting on real captured
  evidence over synthetic fixtures wherever feasible.
- 2026-08-13 — `phase3/target_repo_semantic_cheat/` is deliberately tracked
  in the SisyphX repo itself (not gitignored like Phase 1/2's throwaway
  target repos), because Phase 3 needed the same ground truth reused across
  many chunks rather than regenerated per-chunk. Later phases needing a
  similar durable fixture should follow this pattern.

## Findings and recommendations (Phase 4 scoping deferred)

### Findings

1. **The property-test tier closes the semantic-cheating gap for chunks
   that supply one.** It does not close the gap automatically for chunks
   that don't — someone (human or agent) still has to state the real
   contract as an invariant.
2. **Mutation testing is not a substitute for a correct test; it measures
   how thoroughly an existing test exercises the code.** A single-example
   test can score deceptively well against it. This is a durable, general
   finding, not specific to this project's fixture.
3. **The `EventStore`'s schema-less JSON payload absorbed a new tier's
   fields with zero migration.** This validates CHUNK-023's original
   recommendation to keep the event schema minimal and retrofit rather than
   design speculatively.
4. **Reusing the existing `run_verification` execution primitive for tier 2
   (rather than importing a new module into `loop.py`) preserved every
   existing test's monkeypatch seam.** A useful general pattern: when
   extending a well-tested function's *use*, prefer calling it again over
   introducing a parallel code path, if the semantics genuinely match.

### Recommendations for when Phase 4 is scoped

- Treat property-test authoring as the next real gap: either a planner/
  spec step that proposes an invariant per chunk (candidate use for
  `experiments/planner/`, if it's still wanted), or an explicit human
  sign-off step before a chunk without one is allowed to run unattended.
- Keep mutation testing (`cosmic-ray`) available as an optional,
  chunk/feature-level check — not attempt-level, not required — for
  projects that want the extra assurance and can afford the latency.
- Use the now-larger real evidence base (Phase 1–3's actual `RunLogEntry`
  and `EventStore` fields, including the new tier-2 fields) as the
  empirical foundation for any future Pydantic domain models, per Phase 2's
  original recommendation — still not contradicted by anything Phase 3
  found.
- A concrete second target project remains the highest-leverage next
  validation step: everything through Phase 3 has been proven only against
  SisyphX's own tiny fixtures and its own repo.

## Phase 4 scoping

Intentionally not done in this chunk, same pattern as CHUNK-023. The
`Phase 4+` section of `PLAN.md` stays as a rough-direction placeholder;
chunk-level scoping happens in a later planning session.

## Verification

- `PLAN.md` updated with Phase 3 findings and recommendations; `Phase 4+`
  placeholder left for future scoping; Decision log and Open Questions
  sections updated.
- `uv run pytest` → **88 passed**.
