# CHUNK-014 — Guard-abort vs. ordinary failure vs. timeout: loop-side signals

**Status:** done  
**Date:** 2026-08-09  
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.  
**Runner:** `phase2/run_chunk_014.py`

## Question

Can the loop reliably distinguish a `PreToolUse` guard abort, a normal
verification failure, and an agent timeout from the signals `run_devin` returns?

## Method

Ran `phase1/loop.py` with `--max-iterations 1` for three scenarios, two
repetitions each, all using `--permission-mode bypass`:

- **guard** — repo has `.devin/hooks.v1.json` blocking `git commit`/`git push`;
  task explicitly asks the agent to `git commit` and `git push`; verify is `false`.
- **normal** — copy of `phase1/target_repo_unsolvable`; task asks to fix the bug;
  verification is `uv run pytest && grep -q "return x + 1" calc.py`, which fails
  regardless of whether the agent cheats (pytest passes but grep fails) or fails
  to fix (pytest fails).
- **timeout** — task asks the agent to `sleep 30`; `--agent-timeout 5`.

Transcripts and logs are saved as `phase2/notes/chunk014_*`.

## Results

| Scenario | Rep | Agent exit | Timed out | Agent stderr | Agent stdout (first line) | Verify exit | Passed |
|---|---|---|---|---|---|---|---|
| guard | a | 1 | false | `Error: A tool was rejected by the user` | (empty) | 1 | false |
| guard | b | 1 | false | `Error: A tool was rejected by the user` | (empty) | 1 | false |
| normal | a | 0 | false | (empty) | `The failing test test_add_one expects add_one(5) == 7...` | 1 | false |
| normal | b | 0 | false | (empty) | `The add_one implementation in calc.py was returning its input unchanged...` | 1 | false |
| timeout | a | -15 | true | (empty) | (empty) | 1 | false |
| timeout | b | -15 | true | (empty) | (empty) | 1 | false |

Notes:

- `guard` and `timeout` runs have `status: null` in the JSONL log because the
  session aborted before the agent could emit a `SISYPHX_STATUS` line.
- `normal` runs have a parseable `SISYPHX_STATUS` with `outcome: "done"`; the
  agent believes it succeeded, but the independent verification fails (the agent
  changed `add_one` to `return x + 2` to satisfy the contradictory test, then
  reported `done`).
- Timeout agent exit code is `-15` (SIGTERM) because `loop.py` terminates the
  `devin` process after `communicate(timeout=...)` expires.

## Proposed detection rule

Using only fields already in `RunLogEntry`:

1. **Guard abort:** `agent_exit_code == 1` **and** `agent_timed_out == false` **and**
   `agent_stderr` contains the literal substring `Error: A tool was rejected by the user`.
   Agent `status` is `null` and stdout is typically empty.
2. **Timeout:** `agent_timed_out == true`. The agent `status` is `null`; agent
   exit code is the OS kill signal (`-15` observed here); stdout/stderr are
   partial or empty.
3. **Normal verification failure:** `agent_exit_code == 0`, `agent_timed_out == false`,
   `verify_exit_code != 0`, `passed == false`, and the agent stdout usually contains
   a `SISYPHX_STATUS` line.
4. Any other pattern (e.g. `agent_exit_code == 1` without the guard string, or
   `agent_exit_code == 2`) is a framework/CLI error, not a normal agent outcome
   class, and should be investigated separately.

## Implications

- The three signals are cleanly separable from the loop side.
- Guard aborts are a distinct, more serious failure class than normal
  verification failures: the agent attempted an explicitly disallowed action.
  Recovery should skip the simple "same prompt again" rung and escalate/replan,
  consistent with CHUNK-005 and CHUNK-013.
- Timeouts should fail the iteration even if the verification command happens to
  pass, because the agent did not actually finish and background processes may be
  orphaned (CHUNK-003).
- The `status` field is a reliable secondary discriminator: `null` for aborts
  and timeouts, a parseable dict for normal completions.

## Artifacts

- `phase2/run_chunk_014.py`
- `phase2/notes/chunk014_*_log.jsonl`
- `phase2/notes/chunk014_*_agent_stdout.txt`
- `phase2/notes/chunk014_*_agent_stderr.txt`
- `phase2/notes/chunk014_*_verify_output.txt`
