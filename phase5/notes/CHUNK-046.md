# CHUNK-046 — Phase 5 retro and Phase 6 scoping

**Status:** done
**Date:** 2026-08-14

## Phase 5 summary

Phase 5 was the highest-leverage recommendation carried forward since
CHUNK-023: validate SisyphX against a real second project, in a real
second language, not a hand-built toy fixture. The user provided one:
the Illima Energy Dashboard, a real, in-progress Laravel 11 + Filament v3
client application (`/Users/stini/Ai_Dev_Home/Projects/Illima_Energy/illima-dashboard`).

Scope was deliberately narrow, per the project's standing discipline:
prove the pipeline works end-to-end on one real, already-scoped, low-risk
chunk before doing more real tickets. No new domain models, ontology,
learning/promotion, or Spec Kit/APM.

| Chunk | What happened |
|---|---|
| CHUNK-043 | Initialized git for a project that had none anywhere. Verified no secrets committed. Confirmed a clean baseline (`php artisan test`: 12 passed, 42 assertions). |
| CHUNK-044 | Widened the tamper guard for PHP/Laravel conventions. Found and fixed **two real, previously-hidden bugs** that predate PHP and applied to Python too: an fnmatch pattern gap (`dir/**/*.ext` never matched files directly under `dir/`) and a more significant one (`git status --porcelain` without `--untracked-files=all` made every file inside a brand-new subdirectory invisible to the guard since Phase 2/CHUNK-020). Confirmed Docker-based verification works completely unmodified. |
| CHUNK-045 | First real chunk run hit a **third real, significant bug**: `--repo` must be the actual git toplevel, or the tamper guard misreads paths and fires on legitimate work. Fixed by restructuring the target repo and hardening `loop.py` with a fail-fast precondition check. Second attempt passed on iteration 1 with real, correct, independently-verified work. |

## What actually happened when SisyphX met a real project

Every one of Phase 5's three chunks found and fixed a real bug — not one
was purely additive. This is a genuinely different pattern from Phase 4,
where new mechanisms (`test_author.py`, `meta_verify.py`) were built and
then validated. Here, the framework was largely *already correct*; what
was missing was assumptions the framework had never had to confront:

1. **The tamper guard's directory-globbing had been subtly broken since
   CHUNK-020** (Phase 2) for two independent reasons, neither PHP-specific,
   both silently reducing coverage rather than causing visible failures.
   Neither was caught by 66+ passing tests across four phases, because
   every test fixture happened to avoid the exact shapes that triggered
   them (a file directly under a protected directory; a file inside a
   brand-new, previously-untracked directory).
2. **`loop.py` had an unvalidated precondition** (`--repo` is the git
   toplevel) that every prior use — always a purpose-built scratch/target
   repo, always at the root — happened to satisfy by construction. A real
   project, organized the way real projects actually are (planning docs +
   code, considered together), violated it immediately.

None of these would have been found by more testing *within* SisyphX's
own toy fixtures — they required a real, independently-organized
codebase with its own conventions to surface.

## What the real chunk itself proved

Setting the bugs aside: once the preconditions were correct, the pipeline
worked exactly as designed, unmodified, on a real production task:

- A live Devin CLI agent, given a real chunk's goal/acceptance
  criteria/permitted paths, produced a correct `Customer` Eloquent model,
  a correctly-shaped migration, and a test covering both the shape and a
  real constraint (uniqueness) — all inside a Laravel/PHP/Docker stack
  SisyphX had never touched before.
- The existing verification, commit-integrity, and tamper-guard machinery
  from Phase 1/2 required **zero changes** to work with a Docker-wrapped
  PHPUnit command — the `--verify` contract (an arbitrary shell command,
  `shell=True`, `cwd=repo`) was already general enough.
- Independent re-verification outside the loop (12→14 tests, 42→45
  assertions, hand-reviewed diff) confirmed the loop's own report was
  accurate — consistent with every prior phase's practice of never trusting
  self-report alone.

## Open questions resolved

| Question | Resolution |
|---|---|
| Does SisyphX's core loop/guard machinery generalize to a real second project and language without deep rework? | Yes, once repository-structure preconditions are met. The `--verify` contract, commit-integrity guard, and recovery ladder needed zero changes. Only the tamper guard's pattern list needed widening (an additive, expected change, not a rework). |
| Is `experiments/planner/`'s ticket+chunk format useful in practice? | Yes — independently confirmed by seeing it already in real, sustained use on a real project, including a `failed` ticket documented with the same honesty this project's own methodology requires. Chunk 001.001.001's existing `permitted_paths`/`Verification` sections needed no translation to be usable as `--permit`/`--verify` arguments. |

## Open questions carried forward

- **The `004.013` verification gap (tests passed, browser didn't) has not
  yet been directly addressed.** Phase 5 validated the pipeline on a safe,
  additive, backend-only chunk. Whether SisyphX's current verification
  model (a single shell command's exit code) can catch a UI/browser-level
  gap like 004.013's at all is unresolved — `php artisan test` alone,
  even for a correct implementation, would not have caught that failure
  originally, and neither would `loop.py` as currently built. This is a
  concrete, real candidate for Phase 6: does verification need a browser/
  visual-regression tier (analogous to Phase 3/4's tier 2) for UI work,
  and is that in scope for SisyphX or better left to the project itself?
- **Whether to continue driving Illima Energy's remaining planned tickets
  through SisyphX**, and if so, at what pace/autonomy level, given this is
  real client work with real stakes (unlike every prior phase's fixtures).
  Not decided in this retro — a human decision, not a technical one.
- Unchanged from Phase 4: whether `--sandbox` changes process-orphan
  behavior; whether Devin CLI's `/loop` is scriptable; event-store
  retention; whether a live agent can be reliably induced to cheat on a
  mathematically explicit contradiction (Phase 4's open question, not
  re-tested here).

## Decision log additions

- 2026-08-14 — Phase 5 complete. Validated SisyphX against a real second
  project (Laravel/PHP) for the first time. Found and fixed three real
  bugs (two in the tamper guard predating PHP, one a `loop.py` precondition
  never previously violated) — none were language-adapter gaps; the core
  `--verify` contract, commit-integrity guard, and recovery ladder needed
  zero changes to work on a real, different-language, Docker-based stack.
  One real chunk (001.001.001) completed correctly and independently
  verified.
- 2026-08-14 — A real project's own ticket/chunk planning format
  (independently modeled on SisyphX's `experiments/planner/`) needed no
  translation to drive `loop.py` directly — its `Permitted paths` and
  `Verification` sections mapped onto `--permit`/`--verify` almost
  verbatim. This is a positive signal for that format's design, observed
  in real use rather than SisyphX's own (until now, untouched) copy of it.

## Recommendations for Phase 6

- The `004.013` UI/browser verification gap is the single most concrete,
  motivating next target — it is a real instance of exactly the class of
  problem SisyphX exists to solve, sitting unaddressed in the same
  project Phase 5 just validated against.
- Before driving more real Illima Energy tickets at volume, get an
  explicit decision from the project owner on autonomy level (how many
  iterations, what's auto-committed vs. reviewed) given real stakes.
- Continue the established discipline: real runs over synthetic ones,
  independent re-verification, honest recording of failures (including,
  as this phase repeatedly showed, failures in SisyphX's own code).

## Phase 6 scoping

Intentionally not done in this chunk, same pattern as CHUNK-023/033/042.

## Verification

- `PLAN.md` updated with Phase 5 findings, decision log, and open
  questions.
- `uv run pytest` → **117 passed**.
