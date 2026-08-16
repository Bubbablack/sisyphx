# CHUNK-049 — Review pass: `experiments/planner/` chunk-quality review, ahead of promotion

**Status:** done
**Date:** 2026-08-16
**Deps:** none (independent of 047/048; ordered after per the 2026-08-15 priority decision)

## Question

What concretely makes today's chunk format (`experiments/planner/BRIEF.md`)
produce weak vs. strong inputs to `loop.py`, using real usage evidence
(Illima Energy's 22 real tickets, including the `failed` `004.013` one,
and Phase 5's one real `loop.py`-driven chunk) rather than speculation?
Does the format need revising, and should `experiments/planner/` be
promoted out of `experiments/`?

## Method

Read every real ticket and chunk file under
`Illima_Energy/experiments/planner/tickets/` (22 tickets; read-only —
nothing in the Illima Energy repo was modified by this review) and
compared them against `experiments/planner/BRIEF.md`'s documented format.

## Findings

### 1. Most real, shipped work never went through the chunk format at all

Of 22 real tickets, only 4 (`001.001`, `001.002`, `002.001`, `003.001`) —
all early, foundational CRUD/model scaffolding — were ever decomposed
into the documented `chunks/`+`prompts/` structure with
`permitted_paths`/`prohibited_changes`/a single verify command. Every
actual dashboard feature ticket that shipped (`004.005`–`004.009`,
`004.014`, and the reverted `004.013`) was completed as a single
ticket-level task: a `## Behaviour` + checklist `## Acceptance criteria`
+ free-form `## Implementation notes`, with **no `permitted_paths`, no
`prohibited_changes`, and no single independently-run verify command** —
run through a live/interactive session, not `loop.py`.

Of the 4 tickets that *were* chunked, only **one chunk**
(`001.001.001`) has ever actually been run through `loop.py` (Phase 5,
CHUNK-045); the rest are still `planned`.

**Implication:** the chunk file format's actual real-world track record
is a single successful automated run. Everything else — including the one
concrete failure this review is meant to learn from — happened entirely
outside the format being reviewed. Any claim that "the chunk format is
strong" can only be evidenced this narrowly; the review below is honest
about that.

### 2. Where the chunk format *was* used, the fields themselves are already tight

`001.001.001`/`001.001.002`, `001.002.*`, `002.001.*`, `003.001.*` are
consistently well-scoped: narrow `permitted_paths` (often a single file
plus its natural test file), explicit `prohibited_changes` that correctly
anticipate the next ticket's scope (e.g. "do not create the Filament
resource yet"), and a single, precise verify command
(`php artisan test tests/Unit/DeliveryModelTest.php`, not the whole
suite). CHUNK-045's real run found zero problems with the chunk file's
own content — every bug found in Phase 5 was in `loop.py`/`tamper_guard.py`
itself, not in how the chunk was written. **The template's structural
fields (`permitted_paths`, `prohibited_changes`, `Verification`,
`Acceptance criteria`) do not need revising.**

### 3. The one real, load-bearing gap: no chunk has ever asked for a human to look at a browser

Every chunk touching Filament/Livewire UI (`001.001.002`'s
`CustomerResource`, `001.002.002`'s `DeliveryResource`, `002.001.002`'s
customer delivery page) has "Feature tests pass" as its *only*
verification-shaped acceptance criterion. This is the exact shape of gap
`004.013` (not itself chunked, but the same project, same author
discipline) hit for real: 14 tests / 48 assertions passed, including two
tests written specifically to cover the new behavior, and it still
"didn't work" in a real browser — and the acceptance criterion asking for
a browser check (`004.013`'s final bullet) was only added to the ticket
**after** the failure, not stated up front. `004.008` (a closed,
non-chunked ticket) shows the opposite, healthier pattern by accident —
its implementation notes end with "Manually verified in-browser against
live FMA data" — but that was one author's habit on one ticket, not
something the format asked for or would have caught if skipped.

This is not a hypothetical "what if" concern invented for this review; it
is the single most expensive real failure in the project's history so far
(a full revert), and it is exactly the class of gap `PLAN.md` has flagged
since Phase 5's retro as the most concrete carried-forward finding.

## Re-authoring exercise

Per the acceptance criteria, re-authored 3 real chunks against a proposed
revision (adding a required `## Manual verification` section for any
chunk touching rendered UI) — see `phase6/chunk049_reauthored/`:

- `001.001.002_revised.md` — the real, still-`planned` `CustomerResource`
  chunk, with concrete browser steps for search/sort/create/edit/delete.
- `002.001.002_revised.md` — the real, still-`planned` customer delivery
  history chunk; the added steps specifically target the
  security-relevant "customer sees only their own data" criterion, which
  a minimal test fixture could pass without actually proving correct
  scoping under multiple customers' data.
- `004.013.001_retroactive_revised.md` — a hypothetical *before-the-fact*
  version of the real `004.013` pagination work, written as a proper
  chunk using only information genuinely available up front (not
  hindsight beyond the one lesson being tested). Its `## Manual
  verification` section names the exact browser interaction (paginate,
  confirm the table actually updates, confirm the two widgets don't
  collide) that the real attempt's automated tests could not have caught
  and that a human did in fact catch — just after implementation instead
  of being asked for as a planned step before it.

Comparing originals to revised versions: the structural fields
(`permitted_paths`/`prohibited_changes`/`Verification`) are unchanged in
all three — confirming finding #2, that revision isn't needed there. The
only real content difference is the new section, and in all three cases
it names something concrete and specific to that chunk's actual UI
surface, not a generic "test in browser" placeholder.

## Decision

**Revise, don't rewrite.** `experiments/planner/BRIEF.md` is updated
in place (still under `experiments/`, not moved) with one addition: every
chunk file gets a required `## Manual verification` section — `N/A` with
a one-clause reason for chunks with no rendered UI surface, concrete
human-checkable steps otherwise. It is explicitly excluded from the
generated `chunk_prompt.txt` (it is a human gate, not an agent
instruction) and explicitly **not** a substitute for the still-deferred
automated UI/browser verification tier tracked in `PLAN.md`'s Phase 6+
list — it is the cheap, zero-tooling stopgap available today, using the
same "make an already-existing manual habit a required, structural part
of the format" pattern the review-marker guard (CHUNK-047/048) just used
for `REVIEW:` comments. Also cross-referenced CHUNK-048's now-real
review-marker guard into the workflow's Close-gate step, which previously
described it as still-deferred.

**Promotion: not yet, and not blanket.** Per the acceptance criteria,
promotion itself is a separate follow-up, but this chunk does decide
*whether and how*:

- The **ticket+chunk markdown format** (front matter + section
  structure, now including `## Manual verification`) is sound enough to
  promote out of `experiments/` as SisyphX's Control-plane planning
  convention, replacing Spec Kit per the 2026-08-15 decision — its
  structural fields have zero real defects found across 22 real tickets
  and one real automated run.
- There is **no code to promote** — `planner.py` was never built in
  either repo; every real ticket/chunk file was hand-authored markdown.
  "Promotion" is therefore a documentation/convention move (e.g. out of
  `experiments/` into a permanent top-level location), not a code
  migration, when it happens.
- Given finding #1 (only one real chunk has ever actually run through
  `loop.py`), the honest recommendation is to **defer the promotion move
  itself until more real chunks — including some deliberately UI-facing
  ones with the new `## Manual verification` field — have actually gone
  through `loop.py`**, rather than promote on the strength of a single
  successful run plus a paper revision. The format is good; the evidence
  base for it is still thin.

## Implications / carried forward

- Next real Illima Energy work should prefer running the *planned but
  never-executed* chunks (`001.001.002`, `001.002.*`, `002.001.*`,
  `003.001.*`) through `loop.py` for real, using the revised template
  from this review, both to grow the format's real evidence base and to
  make real, not hypothetical, use of the new `## Manual verification`
  field.
- The `004.013` UI/browser automated-verification-tier gap itself remains
  unaddressed and deferred, per the 2026-08-15 priority decision — this
  chunk's `## Manual verification` field is a stopgap for that gap, not a
  resolution of it.

## Artifacts

- `experiments/planner/BRIEF.md` (revised in place)
- `phase6/chunk049_reauthored/001.001.002_revised.md`
- `phase6/chunk049_reauthored/002.001.002_revised.md`
- `phase6/chunk049_reauthored/004.013.001_retroactive_revised.md`
