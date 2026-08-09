# SisyphX — Implementation Plan & Tracker

> SisyphX: the agent loop that knows when to stop.

## What this file is

Living tracker for building SisyphX. Update the **Status** section and check off
chunks (`- [ ]` → `- [x]`) as they're completed. Record any decision that changes
direction in the **Decision Log**, dated. Keep chunk IDs globally sequential and
never reuse a number, even if a chunk is dropped.

## Status

- **Current phase:** Phase 2 scoped — starting at CHUNK-013 (spikes first)
- **Last updated:** 2026-08-09
- **Repo root:** `/Users/stini/Ai_Dev_Home/SisyphX`
- **Contract doc:** `phase0/DEVIN_CLI_CONTRACT.md`
- **Phase 1 loop:** `phase1/loop.py`; tests: `phase1/test_loop.py`, `phase1/tests/test_run_log.py`

---

## 1. Vision

SisyphX is a Python-based control and reliability framework for AI coding agents
(starting with Devin). It:

1. Converts requirements into small, testable chunks.
2. Gives one chunk to a coding agent at a time.
3. Verifies the result independently (tests, lint, guards — never trusting the
   agent's own claim of success).
4. Detects when the agent is stuck and investigates before retrying blindly.
5. Escalates to a human with a focused brief when needed, never repeating the
   same failed prompt indefinitely.
6. Captures experience from every run.
7. Recommends the right kind of improvement — skill, test, guard, tool, config,
   or knowledge fact.
8. Evaluates improvements before promoting them from project-specific to domain
   or universal use.

Core loop: **Plan → Execute → Verify → Recover → Learn → Improve.**

---

## 2. Architecture (target state)

### Five planes

| Plane | Responsibility |
|---|---|
| Control | Task chunks, states, loop, approvals |
| Execution | Devin CLI, processes, git worktrees |
| Assurance | Tests, lint, guards, recovery |
| Knowledge | Ontology, project facts, retrieval |
| Learning | Experience, proposals, evals, promotion |

### Reuse vs. build

| Capability | Reuse | SisyphX responsibility |
|---|---|---|
| Package management | APM | Approval and promotion |
| Specification | GitHub Spec Kit | Import and validate chunks (artifacts only — Spec Kit is markdown/templates, not a callable API) |
| Data contracts | Pydantic | Domain schemas |
| State machines | `transitions` | Valid-state definitions |
| Coding agent | Devin CLI | Runtime adapter |
| Ontology | RDFLib | Domain vocabulary |
| Ontology validation | pySHACL | Knowledge policy |
| Agent evals | Inspect AI | SisyphX-specific datasets |
| Tracing | OpenTelemetry | Span definitions (instrument incrementally, not bolted on at the end) |
| Trace UI | Phoenix | Optional, later |
| Code guards | Semgrep + **Devin CLI hooks** | Project rules |
| Git hooks | pre-commit | Verification configuration |
| Polyglot lint | MegaLinter | Feature-level only (too slow for attempt-level) |
| Property tests | Hypothesis | Framework invariants (state machines, guards) |
| Integration tests | Testcontainers | Project adapters |
| Retries | Tenacity | Transient/infra failures **only**, never logic failures |
| Durable workflows | DBOS | Later, once local framework is stable |
| Workspace isolation | Git worktrees | Lifecycle management |

Full domain model list, state machines, guard list, agent roles, intervention
classification, and promotion scopes from the original spec are preserved in the
[Appendix](#appendix-original-spec-reference).

---

## 3. Design decisions from review

These came out of reviewing the original spec against how the tools actually work:

1. **Spec Kit produces markdown artifacts** (`specs/NNN-feature/{spec,plan,tasks}.md`);
   it has no callable API. SisyphX imports and validates those files — it doesn't
   invoke Spec Kit.
2. **APM's real CLI surface needs confirming** before building the adapter — don't
   hardcode assumed command names.
3. **Python is the framework language.** Per-project verification adapters are
   configurable, not hardcoded to one target language (confirmed — testing depends
   on the project).
4. **Verification needs explicit latency budgets** (attempt-level < 60s) or the
   inner loop becomes unusable.
5. **`FailureSignature` hashing must be designed before Recovery** — the whole
   recovery ladder depends on "is this the same failure as last time?"
6. **Guards are enforced in two independent layers, not one:**
   - Real-time prevention via **Devin CLI `PreToolUse`/`Stop` hooks**
     (`.devin/hooks.v1.json`) and **`--sandbox` + `Write()`/`Read()` permission
     scopes** (OS-level, fail-closed).
   - Independent after-the-fact detection via SisyphX's own guard checks (git diff
     scanning, Semgrep) — SisyphX must never rely solely on the agent's own runtime
     policing itself.
7. **`EventStore` (append-only) is the first thing built**, before the CLI — every
   state machine, verification result, and recovery decision depends on "every
   transition creates an event."
8. **Devin CLI contract specifics confirmed from real docs:**
   - `devin -p --prompt-file <file>` is the scripting primitive (single-turn,
     non-interactive).
   - No `-c`/`-r` flag = fresh session by default (matches "no session memory
     between iterations" philosophy).
   - **No native `--timeout` flag** — bounding an iteration is SisyphX's job
     (`subprocess.run(timeout=...)`).
   - `-p` output is free text, not structured JSON — a parseable "done" signal has
     to be requested explicitly in the prompt template and regex-parsed from stdout.
9. **Promotion needs numeric evidence thresholds from day one** (e.g. N clean uses
   across M chunks, zero guard violations), even if just editable config initially.
10. **Intervention classification ties break toward the narrower-blast-radius
    option** (Guard/Test over Skill/Policy) since those are cheaper to verify and
    roll back.

---

## 4. Active plan

### Phase 0 — Devin CLI contract spike

Goal: nail the exact, empirically-verified contract the loop will rely on. No
framework code yet — just scratch scripts and manual runs, notes committed to
`phase0/`.

- [x] **CHUNK-001** — Confirm non-interactive invocation ✅ 2026-08-08
  - Acceptance: exit codes for normal/error completion documented; stdout has no
    interactive chrome
  - Verify: manual run, transcript saved to `phase0/notes/`
  - Deps: —
  - Findings: see `phase0/notes/CHUNK-001.md`. Exit 0 = ran to completion
    (**not** "task succeeded"), 1 = runtime error, 2 = CLI usage error. Clean
    stdout, no ANSI chrome. **Critical:** Normal mode + no TTY does NOT hang —
    Devin self-detects and gracefully declines tool calls needing approval,
    but still exits 0 having done nothing. `--permission-mode bypass` is
    required for any iteration that writes files or runs commands.
- [x] **CHUNK-002** — Confirm fresh-session default ✅ 2026-08-08
  - Acceptance: two consecutive `-p` runs (no `-c`/`-r`) show as distinct sessions
    via `devin list --format json`; second run has no memory of the first
  - Verify: manual run
  - Deps: 001
  - Findings: see `phase0/notes/CHUNK-002.md`. Confirmed no shared memory by
    default; `devin list --format json` gives a stable per-session `id`
    (human-readable slug) worth storing on `Run`/`Attempt` records for
    traceability. Positive control confirms `-c` correctly resumes/recalls —
    "fresh by default" is deliberate, not broken memory. Loop needs no special
    logic: just never pass `-c`/`-r`.
- [x] **CHUNK-003** — Confirm timeout is our responsibility ✅ 2026-08-08
  - Acceptance: `subprocess.run(timeout=N)` cleanly kills a deliberately slow call;
    check workspace isn't left half-written afterward
  - Verify: throwaway script + manual run
  - Deps: 001
  - Findings: see `phase0/notes/CHUNK-003.md` and `phase0/timeout_probe.py`.
    Confirmed across 3 kill strategies (plain kill, process-group kill,
    graceful SIGTERM+grace-period): killing the top-level `devin` process
    always works cleanly, but **never** reaches a shell command devin itself
    had already spawned via its exec tool (it puts spawned commands in their
    own process group — reparents to `launchd` on kill, a real leak).
    Workspace state stays uncorrupted (no half-written files). Decision:
    loop.py uses graceful SIGTERM→SIGKILL, treats timeouts as exceptional +
    loudly logged, defers a process-snapshot-diff safety net to Phase 2+.
- [x] **CHUNK-004** — Sandbox + scoped-write guard ✅ 2026-08-08
  - Acceptance: `--sandbox --permission-mode autonomous` blocks a write outside a
    granted `Write()` scope; in-scope write succeeds
  - Verify: manual run, 2 scenarios
  - Deps: 001
  - Findings: see `phase0/notes/CHUNK-004.md`. Sandbox correctly blocks writes
    **outside the workspace** (confirmed), but the whole workspace is writable
    by default regardless of narrower `Write()` grants — sandbox only enforces
    the outer boundary, not sub-paths within a project. Shell exec under
    sandbox+autonomous needs an explicit `Exec()` allow rule to work
    non-interactively at all. Worse, approval behavior was **inconsistent**
    across near-identical prompts (same write succeeded once, was rejected
    later). **Decision: Phase 1 uses plain `--permission-mode bypass`**
    (simple, 100% consistent so far) instead of sandbox+autonomous.
    `permitted_paths` enforcement moves entirely to CHUNK-005 hooks +
    independent guards, not sandbox scopes. Sandbox deferred to Phase 2+ as
    optional outer-boundary hardening, not a Phase 1 dependency.
- [x] **CHUNK-005** — Working `PreToolUse` hook ✅ 2026-08-08
  - Acceptance: `.devin/hooks.v1.json` blocks one disallowed action (exit code 2)
    independent of sandbox; allowed action passes
  - Verify: manual run
  - Deps: 001
  - Findings: see `phase0/notes/CHUNK-005.md`. Real schema confirmed:
    `write`/`edit` hooks get `tool_input.file_path` (absolute) + content/diff
    fields; `exec` gets `tool_input.command`. Guards work correctly (allowed
    write succeeded, disallowed write never touched disk, destructive git
    command never ran — all independently verified on disk). **Critical
    behavioral finding: a hook block aborts the entire session immediately**
    (exit 1, `"Error: A tool was rejected by the user"`, zero agent
    narration) rather than letting the agent see the rejection and continue —
    different from a normal recoverable tool error. This is a clean, decisive
    signal for the loop to detect, but recovery must treat it as more serious
    than an ordinary failure (skip straight past "one targeted retry" — same
    prompt will likely hit the same guard again).
- [x] **CHUNK-006** — Structured "done" signal ✅ 2026-08-08
  - Acceptance: prompt template gets a reliable, parseable status line;
    `parse_status()` tolerates minor formatting drift
  - Verify: `pytest` on parser + 5 manual runs
  - Deps: 001
  - Findings: see `phase0/notes/CHUNK-006.md`. `parse_status()` (9/9 unit
    tests pass) + 5/5 real varied Devin runs produced a parseable
    `SISYPHX_STATUS: {...}` line, including correctly self-reporting
    `"blocked"` (not `"done"`) for an impossible task — the model follows the
    semantic instruction, not just the format. Treated as a log annotation
    only, never as ground truth (consistent with CHUNK-001/005 findings).
    Side effect: installed `uv` via the official standalone installer
    (`astral.sh/uv/install.sh`) — **not** `brew install uv`, which would have
    compiled LLVM+Rust from source on this old macOS 12 box.
- [x] **CHUNK-007** — Write `DEVIN_CLI_CONTRACT.md` ✅ 2026-08-08
  - Acceptance: final invocation template, hook file, permission profile, timeout
    strategy, status-line format — nothing speculative left
  - Verify: manual review
  - Deps: 001–006
  - See `phase0/DEVIN_CLI_CONTRACT.md` — the authoritative reference
    `loop.py` implements against, starting at CHUNK-009. **Phase 0 complete.**

### Phase 1 — Minimal Ralph-style loop

Goal: a working, if primitive, loop that makes real verified progress on a real
repo — plain Python, subprocess, git, files. No Pydantic/SQLite/state machines yet.

- [x] **CHUNK-008** — Scratch target repo ✅ 2026-08-08
  - Acceptance: tiny repo, one deliberately failing test, clean git tree
  - Verify: `pytest` shows exactly 1 known failure
  - Deps: —
  - See `phase1/target_repo/`
- [x] **CHUNK-009** — `loop.py`: single iteration ✅ 2026-08-08
  - Acceptance: builds command per Phase 0 contract → subprocess w/ timeout →
    captures raw stdout/stderr/exit code → runs project's verification command,
    captures raw output
  - Verify: `pytest` (stubbed subprocess) + 1 real manual run
  - Deps: 007, 008
  - See `phase1/loop.py`, `phase1/test_loop.py`, and `phase1/notes/CHUNK-009.md`
- [x] **CHUNK-010** — `loop.py`: repeat until stop ✅ 2026-08-08
  - Acceptance: stops on verify-pass / max-iterations / N identical repeated
    failures; commits to git every iteration regardless of outcome
  - Verify: **real end-to-end run** that fixes CHUNK-008's failing test;
    forced-unsolvable case halts at max_iterations
  - Deps: 009
  - See `phase1/notes/CHUNK-010.md` and `phase1/target_repo_unsolvable/`
- [x] **CHUNK-011** — Plain-text run log ✅ 2026-08-08
  - Acceptance: `runs/log.jsonl`, one line/iteration (iteration#, timestamp, exit
    code, pass/fail, git SHA, output path)
  - Verify: `pytest tests/test_run_log.py`
  - Deps: 010
  - See `phase1/tests/test_run_log.py` and `phase1/notes/CHUNK-011.md`
- [x] **CHUNK-012** — Point the loop at SisyphX's own repo ✅ 2026-08-09
  - Acceptance: real first task against SisyphX's own codebase produces a working,
    verified commit with no hand-written code
  - Verify: inspect resulting commit; `uv run pytest` passes
  - Deps: 010, 011
  - See `pyproject.toml`, `uv.lock`, and `phase1/notes/CHUNK-012.md`

### Phase 2 — Make the loop untrickable and unstickable

Goal: close the trust gaps Phase 1's real runs demonstrated (semantic-contract
violation, agent-authored commits, guard-abort blindness) and replace
byte-identical stuck detection with real failure signatures and a minimal
recovery ladder. Scope is deliberately narrow: **Assurance + Recovery only** —
no ontology, no learning plane, no Spec Kit/APM. Structured as Phase 0 was:
**spike/confirm chunks first (013–016), implementation only after each spike's
findings are recorded.** Every implementation chunk must be verified by both
unit tests and at least one real adversarial run, in the CHUNK-010 spirit.

#### Spikes — learn and confirm first (no framework code)

- [x] **CHUNK-013** — Spike: can a `PreToolUse`/`exec` hook block `git` commands? ✅ 2026-08-09
  - Acceptance: empirically confirm whether a hook in `.devin/hooks.v1.json`
    can block `git commit`/`git push` in `--permission-mode bypass`; document
    exact behavior on block (does it abort the whole session per CHUNK-005, or
    does bypass mode skip hooks entirely?); confirm allowed non-git exec still
    passes. Findings note committed to `phase2/notes/CHUNK-013.md`.
  - Verify: manual runs, transcripts saved; independently confirm on disk /
    `git log` that the blocked commit never happened
  - Deps: 005, 010
- [x] **CHUNK-014** — Spike: guard-abort vs. ordinary failure — is the signal
  distinguishable from the loop's side? ✅ 2026-08-09
  - Acceptance: trigger a hook block deliberately and capture exactly what the
    loop sees (exit code, stderr text, stdout shape) vs. a normal verification
    failure and a timeout; document a reliable detection rule (or conclude
    there isn't one and what proxy to use). Findings in
    `phase2/notes/CHUNK-014.md`.
  - Verify: manual runs, at least 2 repetitions per scenario to check
    consistency
  - Deps: 013
- [x] **CHUNK-015** — Spike: failure-output normalization study ✅ 2026-08-09
  - Acceptance: collect the real `verify_output` artifacts already in
    `.agent-state`/notes plus fresh deliberate failures (pytest fail, import
    error, timeout, guard abort); identify which volatile parts (timestamps,
    durations, tmp paths, object addresses, line numbers?) must be normalized
    for a stable `FailureSignature`; write the proposed normalization rules and
    hash recipe in `phase2/notes/CHUNK-015.md` **before** any implementation.
  - Verify: manual review; rules demonstrated on ≥4 real captured outputs
    (same failure twice → same normalized form; different failures → different)
  - Deps: —
- [x] **CHUNK-016** — Spike: test-tamper detection ground truth ✅ 2026-08-09
  - Acceptance: enumerate, from real diffs, what "tampering" looks like —
    rerun a CHUNK-010-style contradictory task and capture the agent's diff;
    define which paths/patterns a tamper guard must flag (test files, verify
    command config, conftest, pytest config) and which legitimate edits it must
    not flag. Findings in `phase2/notes/CHUNK-016.md`.
  - Verify: manual run + review of captured diffs
  - Deps: 010

#### Implementation — only after the spikes above are recorded

- [ ] **CHUNK-017** — `FailureSignature` hashing
  - Acceptance: `phase2/failure_signature.py` implementing CHUNK-015's recorded
    rules: normalize verify output → stable hash; classify failure kind
    (verify-fail / timeout / guard-abort / agent-error) using CHUNK-014's
    detection rule
  - Verify: `pytest` unit tests built from the real captured outputs of
    CHUNK-015 (same failure twice → equal signatures; distinct failures →
    distinct); wired into nothing yet
  - Deps: 014, 015
- [ ] **CHUNK-018** — Loop uses signatures for stuck detection + failure classes
  - Acceptance: `loop.py` replaces byte-identical comparison with
    `FailureSignature`; guard-aborts skip the "same prompt retry" rung and
    stop (or escalate) immediately per CHUNK-005's finding; run log gains
    `failure_signature` and `failure_kind` fields
  - Verify: `pytest` (stubbed) + one real run where two failures differing only
    in volatile output (e.g. durations) are correctly detected as identical
  - Deps: 017
- [ ] **CHUNK-019** — Commit integrity guard
  - Acceptance: per CHUNK-013's findings, either a hook that blocks
    agent-initiated `git commit`/`push`, or (if hooks can't in bypass mode) a
    post-iteration commit audit: loop records HEAD before the agent runs and
    flags/handles any commits it didn't author itself
  - Verify: `pytest` + one real adversarial run where the task explicitly asks
    the agent to `git commit` — the loop must prevent or detect it
  - Deps: 013
- [ ] **CHUNK-020** — Test-tamper guard (detection layer)
  - Acceptance: post-iteration `git diff` scan per CHUNK-016's recorded
    patterns; edits to protected paths (tests, verify config) fail the
    iteration with a distinct failure kind unless the task file explicitly
    allowlists them
  - Verify: `pytest` on the diff scanner + one real rerun of the CHUNK-010
    contradictory task — the `return x + 2`-style tamper must now be caught
  - Deps: 016, 018
- [ ] **CHUNK-021** — Minimal recovery ladder
  - Acceptance: explicit, small policy in the loop keyed on failure kind +
    signature repetition: (1) new signature → feed exact evidence (current
    behavior); (2) repeated signature → escalate prompt with a targeted
    "investigate before editing" instruction, once; (3) repeated again or
    guard-abort/tamper → stop with a generated escalation brief
    (`.agent-state/escalation.md`: task, iterations, signatures, last diff)
  - Verify: `pytest` on the policy (pure function: history → action) + one
    real forced-unsolvable run producing a readable escalation brief
  - Deps: 018, 020
- [ ] **CHUNK-022** — `EventStore` retrofit (append-only, SQLite)
  - Acceptance: `phase2/event_store.py` — append-only events table; loop emits
    events (iteration started/finished, verify result, guard trip, recovery
    action, stop) alongside the existing JSONL log, which stays; schema covers
    only fields the loop actually has, no speculative domain models
  - Verify: `pytest` (round-trip, append-only enforced — no update/delete
    API) + one real run leaving a queryable event trail
  - Deps: 018
- [ ] **CHUNK-023** — Retro: Phase 2 findings + Phase 3 scoping
  - Acceptance: PLAN.md Status/Decision-log updated with what the guards and
    ladder caught in real runs; open questions resolved or explicitly carried
    forward; Phase 3 scoped from evidence
  - Verify: manual review
  - Deps: 017–022

### Phase 3+ — Grow the framework outward (deferred — will be re-scoped after Phase 2)

Not detailed yet, on purpose. Rough direction, mapping loosely to the original
spec's milestones:

- Formalize contracts: Pydantic domain models, `EventStore`, chunk/learning state
  machines — *retrofitted around what Phase 1 actually needed*, not designed
  speculatively.
- Project setup: `AGENTS.md` generation, APM adapter, agent roles as Devin CLI
  permission profiles.
- Specification pipeline: Spec Kit artifact import, task → chunk conversion,
  dependency ordering, approval gate.
- Verification engine: evidence parsers (JUnit/SARIF/LCOV), test-deletion /
  config-tamper guards, Semgrep, pre-commit, attempt/chunk/feature levels.
- Recovery: failure taxonomy, `FailureSignature` hashing, Tenacity for
  transient-only, investigator role, checkpoint rollback.
- Human intervention: pause/resume, escalation brief, durable feedback.
- Ontology: RDFLib vocabulary, pySHACL shapes, retrieval router.
- Experience & learning: experience records, retrospectives, Inspect AI evals,
  champion/challenger.
- Promotion: intervention classifier, numeric promotion criteria, APM
  publication, monitoring, rollback.
- Advanced verification: Testcontainers, Hypothesis, mutation testing,
  MegaLinter, dependency scanning.
- Durability & UI: Postgres, DBOS, Phoenix, additional agent adapters.

---

## 5. Decision log

| Date | Decision |
|---|---|
| 2026-08-08 | Pivoted from framework-first (heavy scaffolding before running Devin once) to Ralph-loop-first: prove the Devin CLI contract and a minimal working loop before building formal structure. |
| 2026-08-08 | Framework language: Python. Verification adapters: configurable per-project, not hardcoded to a specific second language. |
| 2026-08-08 | Guards use Devin CLI's native `PreToolUse`/`Stop` hooks + `--sandbox` permission scopes as the real-time prevention layer, with SisyphX's own independent checks as the detection layer — not either/or. |
| 2026-08-08 | Repo created at `/Users/stini/Ai_Dev_Home/SisyphX` (top-level, not under `Projects/`). |
| 2026-08-08 | CHUNK-001 empirically confirmed: exit code 0 means "the CLI ran to completion," never "the task succeeded" — Devin gracefully self-declines tool calls it can't get approval for (non-interactive, no TTY) and still exits 0 having done nothing. Any loop iteration that needs to write/exec must pass `--permission-mode bypass` (or sandbox+autonomous, per CHUNK-004) or nothing will ever happen. |
| 2026-08-08 | CHUNK-003 empirically confirmed a real limitation: killing the `devin` process (any of 3 strategies tested) never kills a shell command it had already spawned via its own exec tool — reparents to `launchd` instead. Timeouts must be treated as exceptional/rare and loudly logged; a full process-hygiene safety net is deferred to Phase 2+. |
| 2026-08-08 | CHUNK-004 empirically found sandbox+autonomous mode insufficient/unreliable for Phase 1: doesn't restrict sub-paths within a workspace (whole workspace always writable), needs explicit `Exec()` grants for shell commands, and showed inconsistent approval behavior across near-identical prompts. **Reversed earlier assumption** — Phase 1 uses plain `--permission-mode bypass`, not sandbox. `permitted_paths` enforcement is now entirely CHUNK-005 hooks + independent guards, not sandbox scopes. |
| 2026-08-08 | CHUNK-005 confirmed the real hook JSON schema (`write`/`edit` → `file_path`; `exec` → `command`) and that guards work correctly, but discovered a hook block **terminates the entire session immediately** (exit 1, no agent narration at all) rather than letting the agent continue past the rejected action. Recovery policy must treat guard-triggered aborts as a distinct, more serious failure category than ordinary verification failures. |
| 2026-08-08 | CHUNK-010 real run: the agent **violated the semantic contract** of `add_one` (changed it to `return x + 2`) to pass a contradictory test, proving that verification needs more than just the project's own test suite. A follow-up forced-unsolvable run halted at `max_iterations` as required. |
| 2026-08-08 | CHUNK-010 unexpected finding: in `--permission-mode bypass` the agent can run `git commit` on its own, creating commits outside the loop's control. Phase 2 needs a guard (git command hook or post-iteration commit audit) to prevent or detect agent-authored commits. |
| 2026-08-09 | Phase 2 scoped as a narrow Assurance + Recovery slice ("make the loop untrickable and unstickable"): guards for the failure modes CHUNK-010 actually demonstrated, `FailureSignature` + minimal recovery ladder, `EventStore` retrofit. Spike chunks (013–016) confirm behavior empirically before any implementation (017–022), mirroring the Phase 0 approach. Ontology, learning plane, Spec Kit/APM, promotion, and durability all deferred to Phase 3+. |
| 2026-08-09 | CHUNK-012: SisyphX repo initialized with root `.gitignore` that excludes embedded demo repos (`phase0/scratch/`, `phase1/target_repo*/`) to avoid gitlink/submodule confusion. The loop produced a verified, agent-authored `pyproject.toml` on its first self-hosted task. |

## Open questions

- [ ] Whether `--sandbox` changes the CHUNK-003 grandchild-process-orphan
  behavior — attempted in CHUNK-004, result was inconclusive (sandbox's
  approval behavior was too inconsistent to get a clean repeated test). Low
  priority since Phase 1 uses plain bypass mode, not sandbox, anyway.
- [ ] Whether Devin CLI's native `/loop` slash command is scriptable
  non-interactively (worth a quick empirical check in Phase 0, though SisyphX's own
  outer loop is still needed for *independent* verification regardless).
- [ ] Second verification adapter target language — deferred until a real second
  project is in scope.
- [ ] How to prevent or detect agent-initiated `git` commands (especially
  `git commit`) in `--permission-mode bypass` — demonstrated in CHUNK-010. A
  `PreToolUse`/`exec` hook that blocks `git` commands is the leading candidate,
  but needs validation against the CLI's behavior.
- [ ] What verification command should SisyphX use for CHUNK-012 (self-hosting).
  SisyphX itself is not yet a pytest project; need to decide whether to add
  `pyproject.toml`/tests to the main repo, or to use a shell-based "golden
  file" verification for the first self-hosted task.

---

## Appendix: original spec reference

Condensed originals kept for continuity so nothing from the initial design is lost.

### Core domain models (Pydantic)

`Workspace`, `Feature`, `ImplementationChunk`, `AgentRequest`, `AgentResult`, `Run`,
`Attempt`, `CheckResult`, `VerificationResult`, `FailureSignature`,
`RecoveryDecision`, `EscalationBrief`, `KnowledgeFact`, `ExperienceRecord`,
`InterventionRecommendation`, `ImprovementProposal`, `EvaluationResult`,
`PromotionRecord`.

```python
class ImplementationChunk(BaseModel):
    id: str
    feature_id: str
    behaviour: str

    acceptance_criteria: list[str]
    permitted_paths: list[str]
    prohibited_changes: list[str]
    verification_checks: list[str]
    dependencies: list[str]

    status: ChunkStatus
    attempt_count: int = 0
```

A chunk cannot become `READY` without an observable behaviour and verification
method.

### State machines

**Chunk lifecycle:**
`DRAFT → READY → RUNNING → VERIFYING → {PASSED, RETRY, INVESTIGATING, BLOCKED}`

**Learning lifecycle:**
`OBSERVED → PROPOSED → VALIDATING → {REJECTED, APPROVED → DEPLOYED → {RETAINED, ROLLED_BACK}}`

Every transition must create an event.

### Guards (initial deterministic set)

- Do not delete existing tests.
- Do not add test-skipping annotations.
- Do not reduce coverage thresholds.
- Do not edit protected files without approval.
- Do not change verification configuration silently.
- Do not modify files outside the workspace.
- Do not add dependencies without authority.
- Do not modify unrelated files.
- Do not execute destructive Git commands.

### Agent roles

| Role | Permission |
|---|---|
| Planner | Read-only |
| Implementer | Workspace edits and approved commands |
| Investigator | Read-only plus diagnostic commands |
| Reviewer | Read-only |
| Knowledge curator | Knowledge proposals only |
| Learning analyst | Improvement proposals only |

The outer loop remains outside all roles.

### Intervention classification

`NO_ACTION`, `RUN_NOTE`, `ONTOLOGY_FACT`, `PROJECT_CONFIG`, `SKILL`, `GUARD`,
`TEST`, `EVAL`, `TOOL`, `PLANNER_POLICY`, `RECOVERY_POLICY`, `AGENT_DEFINITION`,
`FRAMEWORK_FIX`, `HUMAN_DECISION`.

Policy:

- Mechanically preventable → Guard
- Mechanically detectable → Test/lint
- Repeatable mechanical action → Tool
- Durable fact → Ontology/configuration
- Reusable judgment procedure → Skill
- Poor decomposition → Planner policy
- Wrong recovery action → Recovery policy
- Framework defect → Code fix
- Business ambiguity → Human/ADR
- One-off problem → Run note
- **Ties break toward the narrower-blast-radius option** (Guard/Test over
  Skill/Policy).

### Learning scope and promotion

`RUN → PROJECT → DOMAIN → UNIVERSAL`

| Scope | Storage |
|---|---|
| Run observation | Framework database |
| Project improvement | Project Git repository |
| Domain improvement | Central package repository |
| Universal improvement | SisyphX repository / APM package |

Only approved improvements go into Git. Raw observations, rejected proposals, and
experiment results remain in the database or artifact storage.

### Recovery ladder

Exact failure evidence → one targeted retry → read-only investigation →
competing hypotheses → diagnostic experiment → replan or decompose → fresh
implementation session → human escalation.

Never repeat the same prompt against the same failure indefinitely. Tenacity
retries transient infrastructure failures only, never incorrect implementations.

### Human escalation brief contents

Original objective, acceptance criteria, what passes, what fails, attempt
timeline, Git changes, verified evidence, hypotheses, uncertainty, options and
risks, recommended option, one question.

### Observability spans

`SisyphX.feature`, `SisyphX.plan`, `SisyphX.chunk`, `SisyphX.agent_attempt`,
`SisyphX.verification`, `SisyphX.recovery`, `SisyphX.human_decision`,
`SisyphX.learning_proposal`.

### Target repository layout (central SisyphX repo)

```
SisyphX/
├── pyproject.toml
├── uv.lock
├── src/SisyphX/
│   ├── cli/
│   ├── domain/
│   ├── orchestration/
│   ├── runtimes/
│   ├── verification/
│   ├── recovery/
│   ├── knowledge/
│   ├── learning/
│   ├── packages/
│   ├── persistence/
│   └── telemetry/
├── .apm/
│   ├── skills/
│   ├── agents/
│   ├── instructions/
│   └── prompts/
├── policies/
├── ontology/
├── evals/
└── tests/
```

### Target repository layout (managed project repo)

```
customer-dashboard/
├── AGENTS.md
├── apm.yml
├── apm.lock.yaml
├── apm-policy.yml
├── .apm/
│   ├── skills/
│   ├── agents/
│   └── instructions/
├── .SisyphX/
│   ├── project.yaml
│   ├── verification.yaml
│   ├── ontology.ttl
│   ├── shapes.ttl
│   ├── guards/
│   └── evals/
├── .agent-state/   # gitignored
├── specs/
├── src/
└── tests/
```
