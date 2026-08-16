# Experimental Planner — Project Brief

**Goal:** Build a small, disposable planning helper that acts like a lightweight ticketing system inside SisyphX. A **ticket** is a container of work; a **chunk** is the unit of work handed to the agent. This is a side experiment, not a framework component.

**Principle:** Plain markdown + YAML front matter. No state-machine enforcement, no database, no runtime integration with `loop.py`. Humans edit state and links directly. Learn first, formalize later.

---

## Core concepts

### Ticket

A **ticket** is a planning and tracking container. It can be an `epic`, `task`, `sub-task`, `bug`, `change_request`, or `support` item.

A leaf ticket (`task`, `sub-task`, `bug`, `change_request`, `support` with no child tickets) can contain **chunks**.

### Chunk

A **chunk** is the actual unit of work sent to an agent. It has:

- A clear goal
- `permitted_paths`
- `prohibited_changes`
- A verification command
- Acceptance criteria
- A structured status line instruction
- A **Manual verification** section (CHUNK-049, 2026-08-16) -- required
  whenever the chunk touches rendered UI (views/templates, Livewire/
  Filament components, or equivalent in another stack). See "Manual
  verification" below for why and what it must contain.

A ticket can have **many chunks**. A chunk becomes one `chunk_prompt.txt`.

### Chunk types

| Type | Purpose |
|---|---|
| `spike` | Confirm an assumption, try a flow, or reduce uncertainty while the ticket is still in `planned`. A spike is a small, throwaway exploration. |
| `implementation` | The concrete steps to build the thing. These run while the ticket is in `developing`. |

---

## Ticket states

`unplanned → planned → developing → developed → testing → closed`

These are **manual metadata only**.

| State | Meaning |
|---|---|
| `unplanned` | Captured but not yet refined. |
| `planned` | Scope is clear. The ticket may have `spike` chunks to confirm assumptions before moving on. |
| `developing` | `implementation` chunks are being run one at a time. |
| `developed` | All implementation chunks report completion. Still needs independent verification. |
| `testing` | Independent verification is running or evidence is being reviewed. |
| `closed` | Verification passed and the ticket is accepted. |

---

## Chunk status

Chunks track their own execution status, also manual for now:

- `planned` — defined but not yet sent to the agent
- `running` — sent to the agent / loop is executing it
- `passed` — verification passed
- `failed` — verification failed
- `aborted` — stopped by a guard, timeout, or human decision

---

## Directory

```
experiments/planner/
├── BRIEF.md                 # this file
├── spike/                   # throwaway scripts and scratch notes about the planner itself
├── planner.py               # optional CLI helper (create tickets, add chunks, generate prompts)
├── templates/               # markdown templates
│   ├── epic.md
│   ├── task.md
│   ├── sub-task.md
│   ├── bug.md
│   ├── change_request.md
│   ├── support.md
│   ├── spike_chunk.md
│   └── implementation_chunk.md
└── tickets/                 # the ticket store
    ├── 001-event-store-models.md       # epic
    ├── 001.001-pydantic-models.md      # task (container)
    ├── 001.001-pydantic-models/        # chunks and prompts for this task
    │   ├── chunks/
    │   │   ├── 001.001.001.md          # spike chunk
    │   │   └── 001.001.002.md          # implementation chunk
    │   └── prompts/
    │       ├── 001.001.001_prompt.txt
    │       └── 001.001.002_prompt.txt
    └── 002-failure-classifier.md
```

Ticket files live directly under `tickets/`. A task that has chunks gets a directory named after the ticket file (without `.md`) to hold its `chunks/` and `prompts/`.

---

## Ticket file format

```markdown
---
id: 001.001
name: Pydantic EventStore models
type: task
state: planned
parent: 001
created: 2026-08-12
updated: 2026-08-12
---

# Pydantic EventStore models

## Behaviour
Define Pydantic models for the append-only event store records.

## Acceptance criteria
- [ ] `Event` base model exists with required fields.
- [ ] All current loop events can be represented.

## Notes
...
```

Parent/child links between **tickets** are declared in front matter (`parent: 001`). To find children, scan all ticket files for that parent.

---

## Chunk file format

```markdown
---
id: 001.001.001
ticket: 001.001
type: spike
status: planned
created: 2026-08-12
updated: 2026-08-12
---

# Spike: confirm Event schema with one test

## Goal
Define a minimal `Event` Pydantic model and a single passing test to confirm the schema shape.

## Assumption to confirm
- An `Event` can be represented as a Pydantic model with `id`, `type`, `timestamp`, and `payload` fields.

## Acceptance criteria
- [ ] A Pydantic `Event` model exists.
- [ ] One unit test passes against it.

## Permitted paths
- `src/SisyphX/domain/`
- `tests/domain/`

## Prohibited changes
- Do not modify `phase2/event_store.py`.

## Verification
- `uv run pytest tests/domain/test_event.py`

## Manual verification
- N/A -- this chunk has no rendered UI surface.
```

A chunk’s `type` is either `spike` or `implementation`.

A chunk’s `status` is `planned`, `running`, `passed`, `failed`, or `aborted`.

---

## Manual verification

Added 2026-08-16, per CHUNK-049's review of real usage
(`phase6/notes/CHUNK-049.md`). **Every chunk file has a `## Manual
verification` section.** For a chunk with no rendered UI surface (a model,
a migration, a service class, a CLI command with no view), write `N/A` and
say why in one clause, as in the example above.

**Required, with concrete steps, whenever a chunk's `permitted_paths`
includes a view/template file or a UI component** (Blade, Livewire,
Filament resources/widgets/pages, or the equivalent in another stack).
Each step must name something a human can actually do and see -- click
this, confirm that renders/updates/disappears -- not a restatement of the
automated acceptance criteria in different words.

This exists because of a real, concrete failure, not a hypothetical one:
Illima Energy's ticket `004.013` (pagination for two dashboard widgets)
passed its full automated suite (14 tests, 48 assertions, including two
tests written specifically for the new behavior) and still didn't work
when checked in a real browser -- and the acceptance criterion asking for
that check was only added to the ticket *after* the failure, not before.
Automated `--verify`/`--verify-tier2` results answer "does the code do
what the test says," never "does this actually render and behave
correctly for a real user" -- no amount of chunk-file precision in the
`permitted_paths`/`prohibited_changes`/`Verification` fields changes that,
because none of those fields are about visual/interactive behavior at
all. This section is a required, explicit, up-front commitment to check
the one thing the loop's automated verification tiers structurally cannot
-- not a replacement for the deferred automated UI/browser verification
tier tracked in `PLAN.md`'s Phase 6+ list.

`Manual verification` is **not** included in the generated
`chunk_prompt.txt` sent to the implementer agent -- it is a human-facing
gate for the planner's `testing` state (see the workflow below), checked
before a chunk moves to `passed`/a ticket moves to `closed`, not something
the agent is asked to do or claim credit for in its `SISYPHX_STATUS` line.

---

## Spike chunks

Work in small, verifiable spikes to build the planner itself. Record findings in `spike/CHUNK-XXX.md`.

- **CHUNK-001** — Confirm the ticket + chunk format feels useful
  - Acceptance: a human can create one epic, one task, and at least two chunks (one spike, one implementation) in under 15 minutes.
  - Verify: create tickets and chunks for a real SisyphX Phase 3 feature and review them.

- **CHUNK-002** — Spike: can `planner.py` scaffold a task with a spike chunk and an implementation chunk?
  - Acceptance: `python planner.py init 001.001 "Pydantic EventStore models"` creates the task ticket plus `001.001.001-spike` and `001.001.002-impl` scaffolding.
  - Verify: run it. Decide whether the scaffold helps or gets in the way.

- **CHUNK-003** — Spike: generate a `chunk_prompt.txt` from a chunk file
  - Acceptance: `python planner.py prompt 001.001.001` reads the chunk and writes a prompt file matching the SisyphX contract.
  - Verify: run the prompt through `loop.py` on a target repo.

- **CHUNK-004** — Spike: can we list a ticket’s chunks and their status?
  - Acceptance: `python planner.py chunks 001.001` prints the task with its chunks and their `status` values.
  - Verify: review output against the actual files.

---

## Chunk prompt format

A chunk becomes a `prompt.txt` like this:

```
You are working on SisyphX chunk 001.001.001 (spike) for ticket 001.001: Pydantic EventStore models.

## Goal
Define a minimal `Event` Pydantic model and a single passing test to confirm the schema shape.

## Assumption to confirm
- An `Event` can be represented as a Pydantic model with `id`, `type`, `timestamp`, and `payload` fields.

## Acceptance criteria
- [ ] A Pydantic `Event` model exists.
- [ ] One unit test passes against it.

## Permitted paths
- `src/SisyphX/domain/`
- `tests/domain/`

## Prohibited changes
- Do not modify `phase2/event_store.py`.

## Verification
After you finish, the following command will be run to check your work:

    uv run pytest tests/domain/test_event.py

The test must pass. If you cannot complete the task, end your response with exactly one line in this format:
SISYPHX_STATUS: {"outcome": "blocked", "summary": "<reason>"}
Otherwise:
SISYPHX_STATUS: {"outcome": "done", "summary": "<one short sentence>"}
```

Only `spike` and `implementation` chunks in `planned` or `running` status generate prompts. Epics, tasks with child tickets, and `support` tickets do not generate prompts directly.

Note the chunk file's `## Manual verification` section is deliberately
**not** reproduced in the generated prompt above (see "Manual
verification" earlier in this doc) -- it is checked by a human after the
agent finishes, not something the agent is asked to do.

---

## Lifecycle example

Ticket `001.001 — Pydantic EventStore models`:

1. Created in `unplanned`.
2. Human scopes it and moves to `planned`.
3. A `spike` chunk `001.001.001` is added to confirm the schema shape.
4. `planner.py prompt 001.001.001` generates a prompt; `loop.py` runs it.
5. Spike passes → chunk status `passed`. Plan is refined.
6. Implementation chunks `001.001.002`, `001.001.003`, etc. are added.
7. Ticket moves to `developing`.
8. Implementation chunks are run one at a time.
9. All chunks pass → ticket moves to `developed`, then `testing`, then `closed`.

---

## Recommended end-to-end workflow (planner + loop.py + REVIEW comments)

Captured 2026-08-15. This is the practical workflow for using the planner,
`loop.py`, and the manual `REVIEW:` review convention (see `AGENTS.md`)
together. None of this is enforced by code yet -- it is human discipline,
same as ticket `state`/chunk `status` are manual today.

1. **Plan** -- break real work into a ticket (`unplanned -> planned`), then
   into one or more chunks (`spike` first if there's real uncertainty,
   `implementation` once the approach is confirmed). Write tight
   `permitted_paths`, `prohibited_changes`, acceptance criteria, a real
   verify command, and a `## Manual verification` section per chunk
   (required with concrete steps for anything touching rendered UI --
   see "Manual verification" above). This is the contract everything
   downstream depends on -- weak acceptance criteria here is where
   quality leaks in no matter what runs later.
2. **Execute** -- generate the chunk's prompt (`planner.py prompt <id>` or
   equivalent) and run it through `loop.py` with `--verify` (and
   `--verify-tier2` for anything semantically trickier than a shape check,
   per the Phase 4 meta-verification pipeline). Move the ticket to
   `developing` while chunks run one at a time; `developed` once all
   chunks report `passed`. Do not skip the tamper/commit-integrity guards
   even for "simple" chunks -- Phase 5 found real bugs specifically
   because a real chunk exercised paths the toy fixtures never had.
3. **Review** -- this is the planner's `testing` state: "independent
   verification is running or evidence is being reviewed." `loop.py`
   passing only proves the verify command passed; it does not prove the
   code is good, matches intent, or actually renders/behaves correctly for
   a real user (the known `004.013` UI/browser gap -- see `PLAN.md` Phase
   5 notes and CHUNK-049). Read the actual diff yourself, work through the
   chunk's `## Manual verification` steps for real if it has any, drop
   `REVIEW:` comments wherever something needs a second pass, and
   explicitly ask an agent to "address the REVIEW comments in `<path>`"
   per `AGENTS.md`'s convention. Re-run the verify command after to
   confirm the fix didn't break anything.
4. **Close** -- only move the ticket to `closed` once no `REVIEW:`
   comments remain, every chunk's `## Manual verification` steps have
   actually been walked through (not just left unchecked), and
   verification still passes. As of CHUNK-048, the `REVIEW:` half of this
   gate is no longer just habit: `loop.py` mechanically refuses to *start
   a new run* while any `REVIEW:` marker exists anywhere in the repo
   (`phase2/review_marker_check.py`) -- it does not, and cannot, enforce
   the close decision itself (that is still a human action on the
   ticket's `state` field), but it does stop further automated chunks
   from proceeding past an unresolved one.

```
plan chunk (incl. Manual verification) -> generate prompt -> run loop.py
   -> read the diff yourself -> walk the Manual verification steps
   -> drop REVIEW: comments where needed -> ask agent to resolve them
   -> re-verify -> repeat until clean -> mark chunk passed -> close ticket
```

`loop.py` will refuse to start the *next* chunk while a `REVIEW:` comment
is outstanding anywhere in the repo (CHUNK-048), but nothing yet stops a
ticket from being marked `closed` with unresolved `REVIEW:` comments or
un-walked `Manual verification` steps -- both are still manual, by the
human running the workflow.

---

## Integration rules (for later)

- This experiment produces markdown. It does not call `loop.py`.
- Ticket `state` and chunk `status` are manual. Automation comes later, if at all.
- When Phase 3 starts and the real `spec → chunk` pipeline is designed, this code is either promoted (if the format proves good) or deleted and rewritten.
- No framework files may import from `experiments/planner/` during this experiment.

---

## Acceptance criteria for the experiment

1. A human can plan a real SisyphX Phase 3 feature using the ticket + chunk format.
2. `planner.py prompt <chunk-id>` (or equivalent manual flow) produces a `chunk_prompt.txt` that runs successfully through the existing `loop.py`.
3. A ticket can have multiple chunks, including both `spike` and `implementation` chunks.
4. Parent/child links between tickets can be discovered from the files.
5. A ticket’s chunks can be listed with their `status`.
6. The experiment stays within `experiments/planner/` and does not leak into framework code.

If all six are true, the format is worth carrying into Phase 3. If not, the brief is updated and the experiment continues.
