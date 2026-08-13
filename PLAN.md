# SisyphX — Implementation Plan & Tracker

> SisyphX: the agent loop that knows when to stop.

## What this file is

Living tracker for building SisyphX. Update the **Status** section and check off
chunks (`- [ ]` → `- [x]`) as they're completed. Record any decision that changes
direction in the **Decision Log**, dated. Keep chunk IDs globally sequential and
never reuse a number, even if a chunk is dropped.

## Status

- **Current phase:** Phase 4 scoped — property-test-authorship slice (CHUNK-034–042), not yet started
- **Last updated:** 2026-08-13
- **Repo root:** `/Users/stini/Ai_Dev_Home/SisyphX`
- **Contract doc:** `phase0/DEVIN_CLI_CONTRACT.md`
- **Phase 1/2 loop:** `phase1/loop.py`; tests: `phase1/test_loop.py`, `phase1/tests/test_run_log.py`, `phase2/test_*.py`, `phase3/test_*.py`

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

- [x] **CHUNK-017** — `FailureSignature` hashing ✅ 2026-08-09
  - Acceptance: `phase2/failure_signature.py` implementing CHUNK-015's recorded
    rules: normalize verify output → stable hash; classify failure kind
    (verify-fail / timeout / guard-abort / agent-error) using CHUNK-014's
    detection rule
  - Verify: `pytest` unit tests built from the real captured outputs of
    CHUNK-015 (same failure twice → equal signatures; distinct failures →
    distinct); wired into nothing yet
  - Deps: 014, 015
- [x] **CHUNK-018** — Loop uses signatures for stuck detection + failure classes ✅ 2026-08-09
  - Acceptance: `loop.py` replaces byte-identical comparison with
    `FailureSignature`; guard-aborts skip the "same prompt retry" rung and
    stop (or escalate) immediately per CHUNK-005's finding; run log gains
    `failure_signature` and `failure_kind` fields
  - Verify: `pytest` (stubbed) + one real run where two failures differing only
    in volatile output (e.g. durations) are correctly detected as identical
  - Deps: 017
- [x] **CHUNK-019** — Commit integrity guard ✅ 2026-08-09
  - Acceptance: per CHUNK-013's findings, either a hook that blocks
    agent-initiated `git commit`/`push`, or (if hooks can't in bypass mode) a
    post-iteration commit audit: loop records HEAD before the agent runs and
    flags/handles any commits it didn't author itself
  - Verify: `pytest` + one real adversarial run where the task explicitly asks
    the agent to `git commit` — the loop must prevent or detect it
  - Deps: 013
- [x] **CHUNK-020** — Test-tamper guard (detection layer) ✅ 2026-08-09
  - Acceptance: post-iteration `git diff` scan per CHUNK-016's recorded
    patterns; edits to protected paths (tests, verify config) fail the
    iteration with a distinct failure kind unless the task file explicitly
    allowlists them
  - Verify: `pytest` on the diff scanner + one real rerun of the CHUNK-010
    contradictory task — the `return x + 2`-style tamper must now be caught
  - Deps: 016, 018
- [x] **CHUNK-021** — Minimal recovery ladder ✅ 2026-08-09
  - Acceptance: explicit, small policy in the loop keyed on failure kind +
    signature repetition: (1) new signature → feed exact evidence (current
    behavior); (2) repeated signature → escalate prompt with a targeted
    "investigate before editing" instruction, once; (3) repeated again or
    guard-abort/tamper → stop with a generated escalation brief
    (`.agent-state/escalation.md`: task, iterations, signatures, last diff)
  - Verify: `pytest` on the policy (pure function: history → action) + one
    real forced-unsolvable run producing a readable escalation brief
  - Deps: 018, 020
- [x] **CHUNK-022** — `EventStore` retrofit (append-only, SQLite) ✅ 2026-08-09
  - Acceptance: `phase2/event_store.py` — append-only events table; loop emits
    events (iteration started/finished, verify result, guard trip, recovery
    action, stop) alongside the existing JSONL log, which stays; schema covers
    only fields the loop actually has, no speculative domain models
  - Verify: `pytest` (round-trip, append-only enforced — no update/delete
    API) + one real run leaving a queryable event trail
  - Deps: 018
- [x] **CHUNK-023** — Retro: Phase 2 findings + Phase 3 scoping ✅ 2026-08-09
  - Acceptance: Phase 2 findings and recommendations recorded in
    `phase2/notes/CHUNK-023.md`; `PLAN.md` Status and Decision-log updated;
    open questions resolved or explicitly carried forward. Actual chunk-level
    Phase 3 scoping is intentionally deferred.
  - Verify: manual review
  - Deps: 017–022

### Phase 3 — Verification engine: closing the semantic-cheating gap

Goal: close the one hard gap Phase 2's retro identified — a path-based guard
cannot tell whether a source change (e.g. `add_one` returning `x + 2`) is a
legitimate fix or a semantic cheat that only satisfies a contradictory test.
Scope is deliberately narrow, mirroring Phase 2: **verification engine only**,
still self-hosting against SisyphX's own repo (no second real project yet). No
Pydantic domain models, no ontology, no learning/promotion, no Spec Kit/APM.
`experiments/planner/` stays on hold — it does not feed Phase 3 chunks.
Structured like Phase 0/2: **spikes first (024–027), implementation only after
each spike's findings are recorded (028–032), retro last (033).**

#### Spikes — learn and confirm first (no framework code)

- [x] **CHUNK-024** — Spike: reproduce the CHUNK-010 semantic-cheat case as a
  permanent fixture ✅ 2026-08-13
  - Acceptance: `phase3/target_repo_semantic_cheat/` contains the exact
    contradictory-test scenario from CHUNK-010 (a function with a correct
    contract and a test that demands the wrong behavior), committed as a
    stable, versioned fixture — not regenerated ad hoc — so every later spike
    and implementation chunk in Phase 3 has the same ground truth to test
    against
  - Verify: manual run confirms the unmodified loop reproduces the original
    cheat (`return x + 2`-style) against this fixture; findings in
    `phase3/notes/CHUNK-024.md`
  - Deps: 010, 016 (real diffs), 023 (retro)
  - Findings: see `phase3/notes/CHUNK-024.md` and `phase3/run_chunk_024.py`.
    Two independent runs against the unmodified `phase1/loop.py` +
    `phase3/target_repo_semantic_cheat/` both reproduced the exact CHUNK-010
    cheat (`add_one` → `return x + 2`), verified with `passed=True` from
    plain `uv run pytest`. The fixture is tracked in the SisyphX repo itself
    (not gitignored, unlike Phase 1/2's throwaway target repos); only the
    ephemeral git-initialized copy under `phase3/scratch/` is gitignored.
- [x] **CHUNK-025** — Spike: can a Hypothesis property test catch the
  CHUNK-024 cheat? ✅ 2026-08-13
  - Acceptance: hand-write one property test against the CHUNK-024 fixture's
    real (correct) contract; empirically confirm it fails against the cheat
    and passes against a genuine fix; record authoring overhead (lines,
    time, how much domain knowledge the property required) in
    `phase3/notes/CHUNK-025.md`
  - Verify: `pytest` run against both the cheat and a genuine fix, both
    captured as transcripts
  - Deps: 024
  - Findings: see `phase3/notes/CHUNK-025.md`, `phase3/run_chunk_025.py`, and
    `phase3/target_repo_semantic_cheat/test_calc_property.py`. A single
    11-line Hypothesis property test correctly failed against the CHUNK-024
    cheat (exit 1) and passed against a genuine fix (exit 0) — the exact
    opposite pattern from the fixture's contradictory `test_calc.py`,
    confirming it checks a real invariant rather than agreeing with the bad
    example. Authoring cost was low but requires the real contract to be
    stated explicitly; it cannot be inferred from one example. Fixture
    `pyproject.toml` gained a `hypothesis` dev dependency and an explicit
    `testpaths = ["test_calc.py"]` so plain `uv run pytest` behavior is
    unchanged from CHUNK-024 (verified: still collects exactly 2 items).
- [x] **CHUNK-026** — Spike: mutation-testing tool selection ✅ 2026-08-13
  - Acceptance: trial `mutmut` (or `cosmic-ray` if `mutmut` doesn't fit the
    `uv`/pytest workflow) against the CHUNK-024 fixture; confirm it flags the
    cheat as a surviving mutant vs. a genuine fix killing the equivalent
    mutants; measure wall-clock cost on the tiny fixture repo against the
    attempt-level <60s budget from Design decision #4. Findings, including
    the go/no-go on latency, in `phase3/notes/CHUNK-026.md`
  - Verify: manual run, transcript + timing saved
  - Deps: 024
  - Findings: see `phase3/notes/CHUNK-026.md` and `phase3/run_chunk_026.py`.
    `mutmut` rejected: its `libcst` dependency needed a pinned older version
    to get a macOS x86_64 wheel at all, then `mutmut run` was still building
    its own isolated venv after 5+ minutes with zero mutants tested on a
    2-function module, and crashed with an internal `AssertionError` on
    retry — no further investigation attempted (out of scope for a spike).
    `cosmic-ray` worked and gave a real, informative result: against the
    fixture's own weak `test_calc.py`, the cheat scored a misleadingly
    **high** kill rate (2/26 survived, 92.3% killed) — the 2 survivors
    (`x | 2`, `x ^ 2`) coincidentally also equal 7 for the test's one
    hard-coded input, exposing exactly why single-example tests give false
    confidence under mutation testing. Against the CHUNK-025 property test,
    the genuine fix scored 0% survival (26/26 killed), including killing the
    cheat itself as a generated mutant. `cosmic-ray exec` took ~52-64s on
    this trivial module (over budget once paired with Hypothesis), so
    mutation testing is recommended as a chunk/feature-level check, not an
    attempt-level tier — Phase 3 implementation (028-032) leads with the
    property-test tier from CHUNK-025 instead.
- [x] **CHUNK-027** — Spike: verification-tier invocation contract ✅ 2026-08-13
  - Acceptance: decide and document how `loop.py` invokes an additional
    check beyond the project's own `pytest` command — subprocess convention,
    where per-chunk property/mutation tests live, pass/fail contract, and
    per-tier timeout — informed by CHUNK-025/026's actual tool choice(s).
    Findings in `phase3/notes/CHUNK-027.md`
  - Verify: manual review; a throwaway script demonstrates the contract
    running against the CHUNK-024 fixture
  - Deps: 025, 026
  - Findings: see `phase3/notes/CHUNK-027.md`,
    `phase3/verification_contract_demo.py`, and `phase3/run_chunk_027.py`.
    Contract: at most two tiers, both plain shell commands run exactly like
    today's `--verify` (`subprocess.run(shell=True, ...)`); tier 2 is new,
    optional (`--verify-tier2`/`--verify-tier2-timeout`), and only runs if
    tier 1 passes; tier 1 pass + tier 2 fail produces a new distinct
    `verify-tier2-fail` failure kind rather than a misleading `verify-pass`;
    tier 2 test files live alongside existing tests with no new directory
    convention, invoked by explicit path. Demonstrated on two real
    scenarios: a normal, correct chunk passes both tiers (5.6s); the
    CHUNK-024 cheat passes tier 1 but is caught by tier 2 (5.9s,
    `verify-tier2-fail`) — mechanically reproducing CHUNK-024's real-agent
    finding without re-running the agent.

#### Implementation — only after the spikes above are recorded

- [x] **CHUNK-028** — `phase3/verification_tiers.py` ✅ 2026-08-13
  - Acceptance: pluggable second-verification-tier interface per CHUNK-027's
    contract (property-test runner and/or mutation-test runner, whichever
    CHUNK-025/026 selected), config-driven per project/chunk, explicit
    per-tier timeout budget enforced the same way as CHUNK-003's subprocess
    timeout
  - Verify: `pytest` unit tests (stubbed subprocess) + one real run against
    the CHUNK-024 fixture
  - Deps: 027
  - Findings: see `phase3/notes/CHUNK-028.md`, `phase3/verification_tiers.py`,
    `phase3/test_verification_tiers.py`, and `phase3/run_chunk_028.py`.
    Promoted the CHUNK-027 throwaway demo into the real module, adding a
    `timed_out` flag per tier and `DEFAULT_TIER2_TIMEOUT_SECONDS = 30`
    (informed by CHUNK-025's ~1-2s property-test measurement and CHUNK-026's
    52-64s mutation-testing measurement). 7 new unit tests (stubbed
    `subprocess.run`) cover both timeout paths and the exact `shell=True`/
    `cwd` invocation convention; full suite is 73 passed. Real run against
    the same normal/cheat scenarios as CHUNK-027 confirmed the promoted
    module behaves identically (`verify-pass` / `verify-tier2-fail`).
- [x] **CHUNK-029** — New failure kinds for verification-tier results ✅ 2026-08-13
  - Acceptance: `FailureSignature`/failure classification (CHUNK-017/018)
    gains distinct kinds for the new tier (e.g. `property-fail`,
    `mutation-survived`); recovery ladder (CHUNK-021) treats them as their
    own class rather than folding into ordinary `verify-fail`
  - Verify: `pytest` extending `phase2/test_failure_signature.py` and
    `phase2/test_recovery_ladder.py` with the new kinds
  - Deps: 028
  - Findings: see `phase3/notes/CHUNK-029.md`. Added `verify-tier2-fail` to
    `classify_failure`/`failure_signature` (optional `verify_tier2_*`
    params, defaulting to `None`/reproducing Phase 1/2 exactly) and to
    `recovery_ladder.decide_action` (uses tier2's output as retry evidence,
    deliberately **not** in `STOP_KINDS` — goes through the normal
    retry/escalate/stop ladder like `verify-fail`, not treated like a guard
    abort). Building the "same failure twice" test with two genuinely
    independent real captures surfaced and fixed a real normalization gap:
    Hypothesis's non-deterministic inline comment
    (`# or any other generated value`) was defeating stable hashing for
    tier-2 property-test failures. 9 new tests using real CHUNK-025
    artifacts; full suite 82 passed. Manual integration check confirmed
    `verification_tiers` output plugs directly into `failure_signature`
    with no glue code.
- [x] **CHUNK-030** — `EventStore` schema gains verification-tier fields ✅ 2026-08-13
  - Acceptance: append-only schema addition (no update/delete, per
    CHUNK-022) storing the new tier's pass/fail result and summary evidence
    alongside existing verify-result events
  - Verify: `pytest` round-trip test on the new fields + one real run leaving
    a queryable event trail that includes a tier result
  - Deps: 028
  - Findings: see `phase3/notes/CHUNK-030.md`. The `events` table's
    `payload` column was already an opaque JSON blob (CHUNK-022), so no SQL
    migration was needed or meaningfully possible; added
    `EventStore.append_verify_result()` as an additive convenience method
    defining the CHUNK-029 tier-2 field names
    (`verify_tier2_ran`/`verify_tier2_exit_code`/`verify_tier2_output`) in
    exactly one place, harmless-default when no tier 2 is configured, fully
    backward compatible with raw `append("verify_result", {...})` calls.
    2 new tests; full suite 84 passed. Real run: full
    `verification_tiers` → `failure_signature` →
    `EventStore.append_verify_result` pipeline against the CHUNK-024 cheat,
    then reopened the SQLite file fresh and queried the event back by
    `run_id`/`event_type` — confirmed durable, not just an in-memory
    round trip.
- [x] **CHUNK-031** — `loop.py` wires the new tier in, opt-in per chunk ✅ 2026-08-13
  - Acceptance: chunks that declare the new tier (per CHUNK-027's contract)
    run it as a required check in addition to the project's own verification
    command; chunks that don't declare it are unaffected — fully backward
    compatible with Phase 1/2 behavior
  - Verify: `pytest` (stubbed) + one real run on a chunk *without* the tier
    declared, confirming no behavior change, plus one *with* it declared
  - Deps: 029, 030
  - Findings: see `phase3/notes/CHUNK-031.md`. Added `--verify-tier2`/
    `--verify-tier2-timeout` CLI args and matching `run_loop()` params
    (default `None`, reproducing Phase 1/2 exactly); tier 2 reuses the
    existing `run_verification` primitive a second time, only if tier 1
    passed, keeping the existing `monkeypatch.setattr(loop,
    "run_verification", ...)` test seam intact. 4 new tests; full suite 88
    passed. **Real adversarial run with a live Devin CLI agent** (not a
    scripted cheat) against a fresh copy of the CHUNK-024 fixture: iteration
    1 the agent explicitly refused to cheat and left tier 1 failing;
    iteration 2, given the exact failure evidence, the agent produced the
    exact CHUNK-010 cheat (`return x + 2`) — tier 1 passed but tier 2 caught
    it with `failure_kind="verify-tier2-fail"`, and the loop correctly never
    recorded a false pass before hitting `max_iterations`.
- [x] **CHUNK-032** — Real adversarial re-run: the semantic cheat is now
  caught ✅ 2026-08-13
  - Acceptance: replay the CHUNK-024 fixture end-to-end through the updated
    `loop.py` with the new tier declared; confirm the semantic cheat is
    caught (loop stops or escalates per the recovery ladder) rather than
    silently passing, and that a genuine fix still passes
  - Verify: real run transcripts for both the cheat and the genuine-fix case,
    saved to `phase3/notes/CHUNK-032.md`
  - Deps: 031
  - Findings: see `phase3/notes/CHUNK-032.md`. Cheat case reused CHUNK-031's
    own required real live-agent run (not repeated, to avoid a redundant
    Devin CLI invocation): the agent refused to cheat on iteration 1, then
    produced the exact CHUNK-010 cheat on iteration 2 given exact failure
    evidence, caught by tier 2 (`verify-tier2-fail`). New for this chunk:
    a genuine-fix scenario (`phase3/run_chunk_032_setup.py`, a fresh buggy
    `calc.py` with a correct, non-contradictory test suite) run through a
    **real live agent** — fixed the bug correctly on iteration 1, passing
    both tiers cleanly (`verify-pass`) with zero added friction from the new
    tier.
- [x] **CHUNK-033** — Retro: Phase 3 findings + Phase 4 scoping ✅ 2026-08-13
  - Acceptance: Phase 3 findings and recommendations recorded in
    `phase3/notes/CHUNK-033.md`; `PLAN.md` Status and Decision-log updated;
    open questions resolved or explicitly carried forward. Actual chunk-level
    Phase 4 scoping is intentionally deferred, same pattern as CHUNK-023
  - Verify: manual review
  - Deps: 024–032
  - See `phase3/notes/CHUNK-033.md` — full retro. **Phase 3 complete.**

### Phase 4 — Can the loop write its own tier-2 tests?

Goal: close the property-test-authorship gap CHUNK-033's retro identified —
Phase 3 proved a property test reliably catches semantic cheating, but
nothing in the framework decides *when* a chunk needs one or *writes* it; a
human still has to know the real contract and state it as an invariant.
Phase 4 asks, empirically: can an agent, given only a task's acceptance
criteria (not the buggy implementation), author a property test that
actually distinguishes a cheat from a genuine fix? Scope is deliberately
narrow, still self-hosting, no domain models/ontology/learning/Spec Kit —
same discipline as Phase 0/2/3. `experiments/planner/` stays untouched
unless a spike below concludes it's needed. Structured the same way:
**spikes first (034–037), implementation only after each spike's findings
are recorded (038–041), retro last (042).**

#### Spikes — learn and confirm first (no framework code)

- [x] **CHUNK-034** — Spike: a harder semantic-cheat scenario than `calc.py` ✅ 2026-08-13
  - Acceptance: pick a function whose real contract is less trivially
    invertible than "add one" (e.g. something with a multi-step or
    order-dependent contract), construct a genuine bug plus a
    contradictory/weak example test for it, and commit it as a permanent,
    tracked fixture `phase4/target_repo_harder_cheat/` (same convention as
    CHUNK-024 — tracked source, gitignored scratch copies only). Findings
    in `phase4/notes/CHUNK-034.md`
  - Verify: manual/scripted run reproduces a scripted cheat against the new
    fixture, mirroring CHUNK-024's method
  - Deps: 024 (fixture convention), 033 (retro)
  - Findings: see `phase4/notes/CHUNK-034.md` and `phase4/run_chunk_034.py`.
    Chose list rotation (`listutils.py::rotate_left`) — a genuinely harder,
    order/modulo-dependent contract than `add_one`. The fixture has a real
    missing-wraparound bug plus a contradictory test demanding a
    non-rotation output. Confirmed: unmodified buggy code fails, a genuine
    fix (adds the wraparound) still fails the contradictory assertion, and
    only a scripted hardcoded special-case branch passes both tests — same
    shape as CHUNK-024, but the cheat here required an explicit `if`
    branch, not just a different constant, since no simple formula
    coincidentally satisfies the contradiction. Also added
    `acceptance_criteria.txt`, a contract-only prompt (no bug/cheat hints)
    for CHUNK-035's authoring agent.
- [x] **CHUNK-035** — Spike: can a live agent author a property test from
  acceptance criteria alone? ✅ 2026-08-13
  - Acceptance: give a live Devin CLI agent *only* the CHUNK-034 fixture's
    task/acceptance criteria (not the buggy implementation, not any hint
    about cheating) and ask it to author a property test for the function's
    real contract. Capture the actual authored test file and transcript.
    Findings in `phase4/notes/CHUNK-035.md`
  - Verify: real live-agent run, transcript + authored test file saved
  - Deps: 034
  - Findings: see `phase4/notes/CHUNK-035.md` and
    `phase4/notes/chunk035_authored_test_listutils_property.py`. Given a
    scratch repo containing only `acceptance_criteria.txt` (no
    `listutils.py`, no `test_listutils.py`, no hint of the bug/cheat), a
    live agent authored 9 Hypothesis properties in one pass — the exact
    defining index-relationship property plus identity, periodicity,
    composition, and wraparound-equivalence laws that go beyond what was
    asked. Materially stronger than CHUNK-025's single hand-written
    property, with strictly less information available to the author.
    Whether it actually catches the cheat is verified in CHUNK-036, not
    assumed here.
- [x] **CHUNK-036** — Spike: does the agent-authored property test actually
  distinguish cheat from genuine fix? ✅ 2026-08-13
  - Acceptance: run the CHUNK-035 agent-authored property test against (a)
    a scripted cheat installed in the CHUNK-034 fixture (expect fail) and
    (b) a genuine fix (expect pass), exactly as CHUNK-025 did for the
    hand-written property test. If the agent's test does not cleanly
    distinguish them, that failure mode itself is the finding — document it
    plainly, do not paper over it. Findings in `phase4/notes/CHUNK-036.md`
  - Verify: real run, both scenarios, transcripts saved
  - Deps: 035
  - Findings: see `phase4/notes/CHUNK-036.md`. **Important, sobering real
    result: the agent-authored test did not catch the cheat** — but not for
    the reason first assumed. Both variants showed the same `1 failed, 8
    passed`; investigating showed the one failure (in both) was an
    unrelated authoring bug in the agent's own test
    (`assume(len(lst) == 0)` against a strategy that almost never
    generates an empty list — a `FailedHealthCheck`, not a real check).
    None of the 8 valid properties caught the cheat, even at
    `max_examples=5000`: CHUNK-034's cheat is a **surgical single-point
    hardcode** whose fallback path already contains the correct fix, so it
    is wrong for exactly one `(lst, k)` pair that random sampling
    essentially never generates. **This reveals a structural blind spot in
    pure random-sampling property testing** against a minimal adversarial
    hardcode — true for hand-written tests too, not specific to
    agent-authored ones. Also found: an agent can produce a
    thematically-sound property that never actually executes due to a
    strategy/assume mismatch, which itself needs to be checked for.
- [x] **CHUNK-037** — Spike: test-authoring invocation contract ✅ 2026-08-13
  - Acceptance: decide and document how a test-authoring step fits before
    `loop.py`'s existing implementer/verification flow — a separate
    planning-phase agent call producing a candidate `--verify-tier2`
    command. Per CHUNK-036's finding, the contract must address **two**
    distinct failure modes, not one: (1) a candidate test that never
    executes its intended check (e.g. a `FailedHealthCheck`/strategy-
    assume mismatch) must be rejected outright; (2) known-good/known-bad
    reference testing alone does not catch a surgical single-point
    hardcoded cheat, so the contract must also require the candidate test
    to explicitly exercise the task's own literal example values (e.g. via
    Hypothesis `@example(...)` or a small explicit-value check) in
    addition to random properties. Findings in `phase4/notes/CHUNK-037.md`
  - Verify: manual review; a throwaway script demonstrates the proposed
    contract against CHUNK-034's fixture, including the single-point-cheat
    case CHUNK-036 found
  - Deps: 036
  - Findings: see `phase4/notes/CHUNK-037.md` and `phase4/literal_examples.py`.
    Contract: (1) authoring stays a separate planning-phase agent call
    (CHUNK-035); (2) the framework itself — not the agent — deterministically
    auto-extracts every literal `` `func(args) == expected` `` example
    already stated in the acceptance criteria and generates a companion
    pytest module asserting each directly, regenerated fresh every time;
    (3) tier 2 is the combination of the agent-authored property test and
    this auto-generated file. Demonstrated: the auto-generated check alone
    catches the exact CHUNK-034/036 cheat (`[1,3,2] != [3,1,2]`) the
    property test alone missed, because the cheat's target input coincides
    with an example already in `acceptance_criteria.txt`. **Second real
    finding**: naive combined-exit-code checking is itself broken — the
    agent's CHUNK-036 health-check bug fails unconditionally on every
    variant including a genuine fix, so meta-verification must filter out
    individual checks that fail against a known-good reference *before*
    deciding pass/fail, not just run the combined command and check its
    exit code. Explicit, bounded limitation recorded: this only guarantees
    catching cheats targeting a *stated* example value, not an arbitrary
    unstated one.

#### Implementation — only after the spikes above are recorded

- [ ] **CHUNK-038** — `phase4/test_author.py`
  - Acceptance: a callable step that invokes a live Devin CLI agent with
    only a task's acceptance criteria and returns a candidate property-test
    file, per CHUNK-037's contract. Config-driven, not hardcoded to the
    CHUNK-034 fixture
  - Verify: `pytest` unit tests (stubbed subprocess) + one real run against
    the CHUNK-034 fixture
  - Deps: 037
- [ ] **CHUNK-039** — `phase4/meta_verify.py`
  - Acceptance: per-*individual-check* filtering, not combined-exit-code
    checking (CHUNK-037's second finding): (1) always generate and append
    the `phase4/literal_examples.py` companion test to the agent-authored
    one; (2) run every individual test function in both files against a
    known-good reference and discard/flag (not count against the verdict)
    any that fails there — this is what catches CHUNK-036's
    `FailedHealthCheck` case without permanently blocking a correct fix;
    (3) of the remaining, still-valid checks, confirm at least one fails
    against a known-bad reference (the original bug) *and* the CHUNK-034
    surgical single-point cheat specifically — reject the whole candidate
    (do not wire in) only if no valid check catches the known-bad
    reference, but treat the literal-example file's own failures as
    load-bearing signal even if the agent's property file contributes
    nothing valid
  - Verify: `pytest` unit tests + one real run using CHUNK-035's actual
    authored test as input, confirming: the known health-check-broken
    property is discarded rather than blocking the genuine-fix reference,
    and the surgical cheat is still caught via the literal-example file
  - Deps: 038
- [ ] **CHUNK-040** — Wire authoring + meta-verification into a pre-loop
  planning step
  - Acceptance: a script that runs `test_author` → `meta_verify` → only if
    sound, invokes `phase1/loop.py --verify-tier2` with the authored test;
    if the authored test fails meta-verification, stop and escalate to a
    human rather than running the implementer agent unprotected or silently
    falling back to tier 1 only
  - Verify: `pytest` (stubbed) + one real run covering both the sound-test
    and rejected-test paths
  - Deps: 039
- [ ] **CHUNK-041** — Real end-to-end run: full authoring pipeline catches a
  live cheat on the harder fixture
  - Acceptance: run the full CHUNK-040 pipeline against the CHUNK-034
    fixture with a live implementer agent attempting the task; confirm the
    agent-authored (not hand-written) property test catches a real cheat
    the same way CHUNK-031/032 did for the hand-written one, and that a
    genuine fix still passes. If the live agent produces a different cheat
    than CHUNK-034/036's scripted one and it slips through, that is a valid
    (if disappointing) result to record honestly, not to paper over
  - Verify: real run transcripts for both the cheat and the genuine-fix
    case, saved to `phase4/notes/CHUNK-041.md`
  - Deps: 040
- [ ] **CHUNK-042** — Retro: Phase 4 findings + Phase 5 scoping
  - Acceptance: Phase 4 findings and recommendations recorded in
    `phase4/notes/CHUNK-042.md`; `PLAN.md` Status and Decision-log updated;
    open questions resolved or explicitly carried forward. Actual
    chunk-level Phase 5 scoping is intentionally deferred, same pattern as
    CHUNK-023/033
  - Verify: manual review
  - Deps: 034–041

### Phase 5+ — Grow the framework outward (deferred — will be re-scoped after Phase 4)

Not detailed yet, on purpose. Rough direction, mapping loosely to the
original spec's milestones, unchanged from the earlier placeholder except
renumbered now that Phase 4 itself is scoped:

- Formalize contracts: Pydantic domain models, `EventStore`, chunk/learning state
  machines — *retrofitted around what Phase 1–4 actually needed*, not designed
  speculatively.
- Project setup: `AGENTS.md` generation, APM adapter, agent roles as Devin CLI
  permission profiles.
- Specification pipeline: Spec Kit artifact import, task → chunk conversion,
  dependency ordering, approval gate. Revisit `experiments/planner/` here if
  its ticket+chunk format is still wanted (and if Phase 4 didn't already
  need something like it for the authoring step).
- Recovery: further failure taxonomy beyond CHUNK-029's tier-specific kinds,
  Tenacity for transient-only, investigator role, checkpoint rollback.
- Human intervention: pause/resume, escalation brief, durable feedback.
- Ontology: RDFLib vocabulary, pySHACL shapes, retrieval router.
- Experience & learning: experience records, retrospectives, Inspect AI evals,
  champion/challenger.
- Promotion: intervention classifier, numeric promotion criteria, APM
  publication, monitoring, rollback.
- Advanced verification: Testcontainers, MegaLinter, dependency scanning,
  mutation testing as an optional chunk/feature-level check (CHUNK-026).
- Durability & UI: Postgres, DBOS, Phoenix, additional agent adapters.
- A concrete second target project/use case, once one exists.

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
| 2026-08-09 | Phase 2 complete. The loop is now untrickable (commit-integrity + tamper guards) and unstickable (`FailureSignature` + minimal recovery ladder), and every run leaves an append-only SQLite event trail (`phase2/event_store.py`). |
| 2026-08-09 | Source-level semantic cheating (e.g. changing `add_one` to `return x + 2` to pass a contradictory test) is not mechanically preventable by path-based guards alone. It must be caught by a stronger verifier, property tests, or human review. This is a key finding to feed into Phase 3 scoping when it happens. |
| 2026-08-09 | The JSONL run log stays as the human-readable line record; the SQLite `EventStore` is the queryable, structured audit trail. No speculative domain models were added to the event schema; it only stores fields the loop already has. |
| 2026-08-13 | Phase 3 scoped as a narrow verification-engine slice (CHUNK-024–033), mirroring Phase 2's spike-then-implement structure: reproduce the CHUNK-010 semantic-cheat case as a permanent fixture, evaluate Hypothesis property tests and mutation testing against it, then wire the winning approach into `loop.py` as an opt-in second verification tier. Still self-hosting on SisyphX's own repo — no second real project yet. `experiments/planner/` (unstarted ticket+chunk markdown experiment) stays on hold and does not feed Phase 3; revisit it in Phase 4+ if the spec→chunk pipeline is still needed. Domain models, ontology, learning/promotion, and Spec Kit/APM remain deferred to Phase 4+. |
| 2026-08-13 | Phase 3 is complete. The loop now has a real, live-agent-confirmed second verification tier (`phase3/verification_tiers.py`, wired into `loop.py` as `--verify-tier2`) that catches the exact semantic-cheat pattern CHUNK-010 first found, with zero added friction for genuine fixes. |
| 2026-08-13 | `mutmut` is not viable in this environment (dependency-wheel friction + an internal crash); `cosmic-ray` works but is a chunk/feature-level tool, not an attempt-level one, and only adds value on top of an already-strong test (e.g. a property test) — it is not a substitute for one. Mutation testing is deferred as an optional, non-required addition for Phase 4+. |
| 2026-08-13 | Building an honest "same failure twice" test with two genuinely independent real captures (not the same file reused) is what surfaced a real Hypothesis-output normalization gap in CHUNK-029. Reinforces the Phase 0/2 methodology of insisting on real captured evidence over synthetic fixtures wherever feasible. |
| 2026-08-13 | `phase3/target_repo_semantic_cheat/` is deliberately tracked in the SisyphX repo itself (not gitignored like Phase 1/2's throwaway target repos), because Phase 3 needed the same ground truth reused across many chunks rather than regenerated per-chunk. Later phases needing a similar durable fixture should follow this pattern. |
| 2026-08-13 | Phase 4 scoped as a narrow property-test-authorship slice (CHUNK-034–042), directly continuing Phase 3's theme rather than jumping to a new surface area: Phase 3 proved a property test catches semantic cheating but left "who writes the invariant" as a human responsibility. Phase 4 asks empirically whether a live agent, given only acceptance criteria, can author one reliably, with an explicit meta-verification step (test the candidate test against known-good/known-bad references) before ever trusting it as a `--verify-tier2` command. Domain models, ontology, learning/promotion, Spec Kit/APM, and a second real project remain deferred to Phase 5+; `experiments/planner/` stays untouched unless a Phase 4 spike concludes it's needed. |
| 2026-08-13 | CHUNK-036 empirically found a structural blind spot in pure random-sampling property testing (Hypothesis): a "surgical" single-point hardcoded cheat, whose fallback path is otherwise fully correct, is essentially never caught by randomly generated examples, even at 5000 examples per property — regardless of how many good-faith invariants the test checks. This is true for hand-written property tests too, not specific to agent-authored ones; it did not surface in CHUNK-025/026 because that cheat (`return x + 2`) was wrong for every input. CHUNK-037's meta-verification contract must add explicit-value checks (e.g. Hypothesis `@example(...)`) covering the task's own literal example values, not rely on random sampling alone. |
| 2026-08-13 | CHUNK-037 decided: the framework itself (not the agent) auto-extracts literal `func(args) == expected` examples already stated in a task's acceptance criteria and generates a deterministic companion pytest module, run alongside the agent-authored property test as tier 2. Demonstrated this alone catches the CHUNK-034/036 surgical cheat. Also found combined-exit-code checking is itself unsafe: CHUNK-036's health-check bug in the agent's own test fails unconditionally on every implementation including a correct one, so `phase4/meta_verify.py` (CHUNK-039) must filter individual checks against a known-good reference before deciding pass/fail, not just run the combined command and read its exit code. |

## Open questions

### Resolved

- [x] How to prevent or detect agent-initiated `git` commands (especially
  `git commit`) in `--permission-mode bypass` — resolved in CHUNK-013/019:
  `PreToolUse`/`exec` hook blocks `git commit`/`git push` in real time, and a
  post-iteration commit audit catches any that slip through.
- [x] What verification command should SisyphX use for CHUNK-012 (self-hosting)
  — resolved: `uv run pytest`; `pyproject.toml` and `uv.lock` are in place and
  the suite passes.
- [x] Can source-level semantic cheating (CHUNK-010/023's carried-forward
  finding) be mechanically caught? — resolved in CHUNK-025/031/032: yes, for
  chunks that supply a property test encoding the real contract; confirmed
  with two real live Devin CLI agent runs, not just a scripted demonstration.
- [x] Which mutation-testing tool fits this environment/budget? — resolved
  in CHUNK-026: `mutmut` is a no-go here (dependency + crash issues);
  `cosmic-ray` works but only fits a chunk/feature-level cadence, not
  attempt-level, and needs a strong test to be meaningful at all.

### Carried forward

- [ ] Whether `--sandbox` changes the CHUNK-003 grandchild-process-orphan
  behavior — attempted in CHUNK-004, result was inconclusive. Low priority since
  Phase 2 uses plain bypass mode.
- [ ] Whether Devin CLI's native `/loop` slash command is scriptable
  non-interactively (worth a quick empirical check, though SisyphX's own outer
  loop is still needed for independent verification).
- [ ] Second verification adapter target language — deferred until a real second
  project is in scope.
- [ ] Event-store retention — how long should raw events live, what should be
  summarized/archived, and when should the SQLite DB be rotated? Now more
  relevant since `verify_tier2_output` (CHUNK-030/031) adds another
  potentially large text blob per event.
- [ ] Whether `experiments/planner/` (the markdown ticket+chunk experiment,
  still completely untouched — zero tickets or spikes created) is still
  wanted, and if so, whether it should feed Phase 4's specification pipeline.
- [ ] Whether an agent can reliably author property tests *from* an
  acceptance-criteria spec, closing the remaining human-authorship gap
  Phase 3 left open (property tests are cheap to write once the contract is
  known, but nothing in Phase 3 generates that contract automatically).

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
