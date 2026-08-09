# CHUNK-006 — Structured "done" signal

**Status:** done
**Date:** 2026-08-08
**Code:** `phase0/status_parser.py`, `phase0/test_status_parser.py`,
`phase0/run_status_signal_tests.py`

## Environment note

`pytest` wasn't available (no project scaffolding yet). Installed `uv` for
this and all future Python/test work, since it's the toolchain the whole
spec standardizes on (`uv run pytest`, `uv.lock`). **Used the official
standalone installer** (`curl -LsSf https://astral.sh/uv/install.sh | sh`),
**not** `brew install uv` — Homebrew wanted to compile LLVM + Rust from
source (no prebuilt bottles for this macOS 12 machine), which would have
taken a very long time for no benefit. The standalone installer just drops a
prebuilt binary in `~/.local/bin` (already on `PATH` via `.zshrc`/`.profile`).
Tests run via `uv run --with pytest pytest ...` (ephemeral env, no
`pyproject.toml` needed yet for this Phase 0 spike).

## Design

Prompt suffix instructs the agent to end its response with exactly one line:

```
SISYPHX_STATUS: {"outcome": "done|blocked|partial", "summary": "<one short sentence>"}
```

`parse_status(stdout: str) -> dict | None` extracts and parses it, tolerating
formatting drift: extra whitespace, markdown backtick-wrapping, a bare word
instead of JSON, the instruction being echoed earlier in the response (takes
the **last** match), and malformed JSON (falls back to a raw-string
`outcome` rather than raising).

**This status line is a hint for logs/debugging only.** It is the agent's own
self-report and is never treated as ground truth by the loop — independent
verification (running the actual test/lint command) is what decides
pass/fail, per every finding so far in this phase (CHUNK-001's "exit 0 ≠
success" and CHUNK-005's "zero narration on a hook abort" both already prove
self-reports can't be trusted or even guaranteed to exist).

## Results

### Parser unit tests

`uv run --with pytest pytest test_status_parser.py -v` — **9/9 passed**:
no-status-line, basic JSON, bare word, extra whitespace, markdown backticks,
last-match-wins, malformed JSON fallback, missing-outcome-key default,
trailing punctuation.

### 5 real, varied Devin CLI runs

| Task | Exit | Parsed status |
|---|---|---|
| Trivial arithmetic (no tools) | 0 | `{"outcome": "done", "summary": "Answered that 7 times 8 is 56."}` |
| Write a new file | 0 | `{"outcome": "done", "summary": "Created note_signal1.txt containing HELLO."}` |
| Read a file that doesn't exist | 0 | `{"outcome": "blocked", "summary": "The requested file does not exist, so its contents could not be read."}` |
| Create + edit a file | 0 | `{"outcome": "done", "summary": "Created allowed_src/note_signal2.txt with BASE and appended a MORE_TEXT line via edit."}` |
| Run a shell command | 0 | `{"outcome": "done", "summary": "Ran the date command and reported its output."}` |

**5/5 produced a parseable status line.** Notably, the "impossible" task
correctly self-reported `blocked` rather than `done` — the model followed the
semantic instruction, not just the format. File-producing tasks were
independently verified on disk (`note_signal1.txt` = `HELLO`,
`allowed_src/note_signal2.txt` = `BASE\nMORE_TEXT`), matching the self-reports
in this batch — but per the design note above, that agreement is a nice
sanity check, not a reason to start trusting the signal going forward.

## Implications for the loop

1. Append the `SUFFIX` instruction (see `run_status_signal_tests.py`) to
   every chunk prompt in `loop.py`.
2. Call `parse_status()` on every attempt's stdout and store the result in
   `runs/log.jsonl` as an annotation field — useful for humans skimming the
   log, not used in any stop-condition logic.
3. Stop conditions remain exactly as designed in `PLAN.md`: verification
   pass / max iterations / repeated failure signature. This status line
   changes nothing about that — it's purely observability.
