# CHUNK-042 — Phase 4 retro and Phase 5 scoping

**Status:** done
**Date:** 2026-08-13

## Phase 4 summary

Phase 4 targeted the property-test-authorship gap CHUNK-033's retro
identified: Phase 3 proved a property test reliably catches semantic
cheating, but nothing in the framework decided *when* a chunk needed one
or *wrote* it — a human always had to know the real contract and state it
as an invariant. Phase 4 asked, empirically: can a live agent, given only
a task's acceptance criteria, author a property test that actually
distinguishes a cheat from a genuine fix? No domain models, no ontology,
no learning/promotion, no Spec Kit/APM — same discipline as Phase 0/2/3.
Still self-hosting.

### Spikes (034–037) — learn first, build second

| Chunk | Question | Key finding |
|---|---|---|
| CHUNK-034 | A harder semantic-cheat scenario than `calc.py`? | List rotation (`rotate_left`) — order/modulo-dependent, not trivially invertible. Confirmed the genuine-bug-vs-contradictory-test pattern reproduces; the cheat here needed an explicit `if`-branch, not just a wrong constant. |
| CHUNK-035 | Can a live agent author a property test from acceptance criteria alone? | Yes — 9 Hypothesis properties in one pass, with zero access to the implementation, materially stronger in scope than CHUNK-025's hand-written one. |
| CHUNK-036 | Does the agent-authored test actually catch the cheat? | **No, and not for the reason assumed.** The cheat was a *surgical single-point hardcode* (correct everywhere except one exact input); random sampling essentially never generates that exact input, even at 5000 examples. A structural blind spot in property-based testing, not an agent-specific failure. Separately found the agent's own test had a `FailedHealthCheck` bug that never executed its intended check. |
| CHUNK-037 | Can the framework close this gap without relying on the agent? | Yes — auto-extract literal `func(args) == expected` examples already stated in the acceptance criteria and run them as a deterministic companion check. Also found combined-exit-code checking is itself unsafe: one broken agent-authored check can permanently block a correct fix if the whole file's exit code is trusted naively. |

### Implementation (038–041)

| Chunk | Output | Verified by |
|---|---|---|
| CHUNK-038 | `phase4/test_author.py` | Config-driven authoring step; 7 unit tests + a real authoring run producing an independently-structured 4-property test. |
| CHUNK-039 | `phase4/meta_verify.py` | Per-individual-check filtering (not combined exit codes); 5 unit tests + a real run that correctly discarded CHUNK-036's broken check while still catching the real cheat via the literal-example file. |
| CHUNK-040 | `phase4/plan_and_run.py` | Full pipeline wiring; 4 unit tests + two real live-agent runs (sound and rejected paths). Found and fixed a real integration bug (tamper-guard false positive from uncommitted tier-2 files). |
| CHUNK-041 | Real end-to-end confirmation | Two more real live-agent runs. Cheat scenario: agent refused across 4 iterations (recovery ladder correctly detected "stuck"). Genuine-fix scenario: found a third real failure mode — a live-authored test that was *too strict* (an unstated object-identity check), resolved by one ordinary retry. |

## What the pipeline actually does, end to end

Given only a task's acceptance criteria, `phase4/plan_and_run.py`:

1. Authors a candidate property test in complete isolation from the
   implementer's workspace (CHUNK-038).
2. Escalates to a human immediately, without running the implementer
   agent, if nothing was authored.
3. Auto-generates a deterministic companion test from the acceptance
   criteria's own literal examples (CHUNK-037), regardless of what the
   agent wrote.
4. Meta-verifies both files together: discards any individual check that
   fails against a known-good reference (so a broken check never
   permanently blocks a correct fix), then confirms at least one surviving
   check discriminates a known-bad reference (CHUNK-039).
5. Escalates to a human, without running the implementer agent, if no
   check survives both filters.
6. Only then writes the meta-verified files into the implementer's real
   workspace (committed as a baseline, not left uncommitted — CHUNK-040's
   fix) and runs `phase1/loop.py` with `--verify-tier2` set to the exact
   verified command.

Every step of this was demonstrated with real, live agent calls at least
once — none of the core claims rest solely on a scripted stand-in.

## Open questions resolved

| Question | Resolution |
|---|---|
| Can a live agent author a property test from acceptance criteria alone, with zero access to the implementation? | Yes (CHUNK-035/038), consistently, across three independent live authoring runs, each producing a differently-structured but reasonable test. |
| Does an agent-authored property test reliably catch semantic cheats on its own? | No — random-sampling property tests have a structural blind spot against a surgical single-point cheat (CHUNK-036), true for hand-written tests too. |
| Can the framework close this gap without relying on the agent to get it right? | Yes — auto-extracting literal examples from the acceptance criteria and meta-verifying per-individual-check, not by combined exit code (CHUNK-037/039). |
| Does the full pipeline add unacceptable friction to genuinely correct work? | No — one real live-agent genuine-fix run in CHUNK-040 passed on the first attempt; a second in CHUNK-041 needed one extra retry (due to an overly strict agent-authored check, not a real bug), resolved by the ordinary recovery ladder without escalation. |

## Open questions carried forward

Unchanged from Phase 2/3 (CHUNK-023/033), still not touched by Phase 4:

- Whether `--sandbox` changes the CHUNK-003 grandchild-process-orphan
  behavior.
- Whether Devin CLI's native `/loop` slash command is scriptable
  non-interactively.
- Second verification adapter target language — still deferred until a
  real second project is in scope.
- Event-store retention.
- Whether `experiments/planner/` (still completely untouched) is wanted —
  Phase 4 did not need it; the authoring step turned out to need only a
  single acceptance-criteria text file, not a ticket/chunk system.

New from Phase 4:

- **Whether a live implementer agent can be reliably induced to cheat on
  a mathematically explicit contradiction** (like `rotate_left` to a
  non-permutation) is now genuinely open. Two independent real runs (6
  total iterations) on this fixture produced consistent, principled
  refusal, unlike `calc.py`'s off-by-one (CHUNK-031/032). This may reflect
  a real property of this agent model (harder to rationalize an
  impossible rotation than a plausible off-by-one), or may simply need
  more iterations/pressure than tried here. The mechanical proof
  (CHUNK-036/037/039, against a scripted cheat) stands regardless, but the
  live-agent claim for *this specific fixture* is not independently
  confirmed the way `calc.py`'s was.
- **Agent-authored property tests can be too strict, not just too weak.**
  An unstated object-identity requirement briefly blocked a correct fix.
  Low severity (self-corrects in one retry via the existing recovery
  ladder) but worth refining the authoring prompt for
  (`phase4/notes/CHUNK-041.md`'s recommendation: explicitly scope
  properties to the *stated* contract).
- **Whether authoring prompts should be refined to reduce over-strict
  properties**, and whether that refinement itself needs empirical
  validation (a meta-question Phase 4 did not have scope to answer).

## Decision log additions

- 2026-08-13 — Phase 4 is complete. `phase4/plan_and_run.py` closes the
  property-test-authorship gap Phase 3 left open: a live agent authors a
  candidate test from acceptance criteria alone, the framework
  auto-generates a deterministic companion from the criteria's own literal
  examples, and per-individual-check meta-verification decides whether to
  trust the combination as `--verify-tier2` before ever running the
  implementer agent unprotected.
- 2026-08-13 — Random-sampling property tests (Hypothesis) have a
  structural blind spot against a surgical single-point hardcoded cheat,
  discovered in CHUNK-036 and confirmed not tool-specific. This is a
  durable, general finding about property-based testing, not particular
  to this project's fixture.
- 2026-08-13 — Two real live-agent runs on the harder `rotate_left`
  fixture (CHUNK-040/041, 6 total iterations) did not reproduce a live
  cheat; the agent consistently identified the contradiction as
  impossible. The live cheat-catching claim for this fixture rests on the
  mechanical proof (CHUNK-036/037/039), not a live reproduction — recorded
  honestly per this project's standing principle against re-running to
  force an outcome.
- 2026-08-13 — Agent-authored tests can be unreliable in (at least) three
  independent ways: too weak (CHUNK-036's blind spot), never executing
  (CHUNK-036's `FailedHealthCheck`), and too strict (CHUNK-041's
  object-identity check). Only the first required a framework-level fix
  (the literal-examples companion); the other two are absorbed by
  existing mechanisms (meta-verification's discard step, and the ordinary
  recovery ladder, respectively) without needing new machinery.

## Findings and recommendations (Phase 5 scoping deferred)

### Findings

1. **The authorship gap is closed for chunks that go through this
   pipeline.** A human no longer has to write the property test by hand
   for tier 2 to work — but a human (or a future planning step) still has
   to decide *which chunks* warrant a tier-2 property-test-authoring pass
   in the first place; that decision itself is out of Phase 4's scope.
2. **Meta-verification, not the authoring agent, is what actually makes
   the system trustworthy.** Every real failure mode found (too weak,
   never executes, too strict) was either caught or safely absorbed by
   `phase4/meta_verify.py` or the existing recovery ladder — never by
   trusting the agent's output directly.
3. **The event/log infrastructure built in Phase 1–3 needed zero changes
   to support this.** `phase1/loop.py`'s existing `--verify-tier2`
   mechanism, `EventStore.append_verify_result`, and the recovery ladder
   all absorbed Phase 4's new failure modes without modification — a good
   sign the Phase 3 contract was designed with enough headroom.
4. **Live-agent cheating is not uniformly reproducible across fixtures.**
   This is a genuine finding about agent behavior, not a framework
   limitation, and should temper any claim that "the loop always makes
   the agent cheat eventually" — sometimes it doesn't, and that is a good
   outcome worth measuring, not a null result to discard.

### Recommendations for when Phase 5 is scoped

- If a second real project becomes available, that should take priority
  over further internal refinement — every claim through Phase 4 has been
  validated only against tiny, hand-built fixtures.
- Consider a lightweight "does this chunk need a tier-2 property test"
  decision step (which could be where `experiments/planner/`'s
  ticket/chunk format finally earns its place, if still wanted) rather
  than assuming every chunk should get one.
- If authoring prompts are refined to reduce over-strict properties
  (CHUNK-041's finding), treat that refinement itself as a small, testable
  spike (does the refined prompt actually reduce the over-strict rate,
  measured against a few repeated real runs) rather than a one-off prompt
  edit taken on faith.
- Domain models, ontology, learning/promotion, and Spec Kit/APM remain
  appropriately deferred — nothing in Phase 4 changed the case for
  building them now.

## Phase 5 scoping

Intentionally not done in this chunk, same pattern as CHUNK-023/033. The
`Phase 5+` section of `PLAN.md` stays as a rough-direction placeholder;
chunk-level scoping happens in a later planning session.

## Verification

- `PLAN.md` updated with Phase 4 findings and recommendations; `Phase 5+`
  placeholder left for future scoping; Decision log and Open Questions
  sections updated.
- `uv run pytest` → **104 passed**.
