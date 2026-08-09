# CHUNK-001 — Confirm non-interactive invocation contract

**Status:** done
**Date:** 2026-08-08
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS, authenticated (Devin Pro),
team sandbox enforcement = optional.

## Method

All tests run from a disposable scratch git repo at `phase0/scratch/` (not the
SisyphX repo itself), so nothing here touches real project state. Raw
stdout/stderr for every test is saved alongside this file (`test*_stdout.txt`,
`test*_stderr.txt`).

## Results

### Test 1 — trivial prompt, no tool use, default mode

```
devin -p "Reply with exactly this text and nothing else, no explanation: SISYPHX_PING_OK"
```

- Exit code: **0**
- stdout: exactly `SISYPHX_PING_OK\n` — confirmed via `xxd` hexdump, **zero ANSI
  escape codes or interactive chrome**.
- stderr: empty
- Wall time: ~7.5s

### Test 2 — `--prompt-file` variant

```
devin -p --prompt-file prompt_test2.txt
```

Identical behavior to Test 1: exit 0, clean stdout, empty stderr. `-p` and
`--prompt-file` compose as documented (`-p` triggers single-turn/non-interactive
mode; `--prompt-file` just supplies the message instead of an inline string).

### Test 3 — error cases

| Case | Command | Exit code | stderr |
|---|---|---|---|
| 3a. Missing prompt file | `devin -p --prompt-file does_not_exist.txt` | **1** | `Error: Failed to read prompt file "...": No such file or directory (os error 2)` |
| 3b. Invalid model name | `devin --model definitely-not-a-real-model-xyz -p "hi"` | **1** | `Error: Unknown model: '...'` + full list of valid model names |
| 3c. Invalid CLI flag | `devin --this-flag-does-not-exist` | **2** | clap-style usage error + tip + usage line |

**Conclusion:** exit code **2** = CLI argument-parsing error (clap convention),
exit code **1** = runtime/semantic error (bad file, bad model, etc.), exit code
**0** = the CLI process completed its turn. stdout stays empty on all error
paths; errors always go to stderr. This gives SisyphX's runtime adapter a clean,
if coarse, way to distinguish "we called it wrong" (2) from "it errored during
the run" (1) from "it ran to completion" (0) — but see the critical caveat below.

### Test 4 — tool-requiring prompt, Normal mode, no TTY, no bypass flag

```
devin -p "Create a file named ping.txt ... using your write tool. Then reply with SISYPHX_WRITE_DONE."
```

- **Did not hang.** Completed in 19s.
- Exit code: **0**
- `ping.txt` was **not** created.
- stdout (verbatim):
  > I'm unable to create the file — this session is running in non-interactive
  > mode, which blocks tool calls that need approval (including file writes and
  > scope requests).
  >
  > To proceed, you'll need to either:
  > 1. Re-run with `--permission-mode dangerous` to auto-approve tools, or
  > 2. Grant write access to `.../phase0/scratch` interactively.
  >
  > I have not created ping.txt, so I won't reply with SISYPHX_WRITE_DONE since
  > the task wasn't actually completed.

**This is the single most important finding in this chunk:** Devin CLI
self-detects that it's running non-interactively with no way to prompt for
approval, and gracefully declines the tool call instead of hanging — but it
still **exits 0**. The task was not accomplished, and the only way to know that
is to read the response text or check the actual filesystem/verification
result. This is direct, reproducible confirmation of the core SisyphX
principle: **the CLI's exit code (and its own claim of success) must never be
trusted as ground truth. Independent verification is not optional.**

### Test 5 — same tool-requiring prompt, `--permission-mode bypass`

```
devin --permission-mode bypass -p "Create a file named ping.txt ..."
```

- Exit code: **0**
- `ping.txt` created with content `OK` (confirmed via `git status --short` →
  `?? ping.txt`).
- stdout: exactly `SISYPHX_WRITE_DONE\n`.

Confirms `--permission-mode bypass` is what unblocks unattended tool use.
(Devin's own Test 4 response suggested `--permission-mode dangerous` — per
`devin --help`, `normal`/`dangerous`/`bypass` are the three valid values for
this flag; `dangerous` and `bypass` appear to be aliases for full
auto-approval. We standardize on `bypass` since it's the name documented in
`essential-commands.mdx`. Not yet tested whether `dangerous` behaves
identically — low priority, can confirm later if it matters.)

## Implications for the loop (Phase 1) and contract doc (CHUNK-007)

1. **Every loop iteration that needs to write files or run commands must pass
   `--permission-mode bypass`** (or use `--sandbox --permission-mode
   autonomous`, per CHUNK-004). Without it, the agent will correctly and
   safely refuse to do anything, every single time — not a bug, but it means
   the "default" invocation for Phase 1 cannot be the CLI's own default mode.
2. **Exit code is not a success signal.** It only ever tells us "the process
   ran to completion (0), hit a runtime error (1), or was called incorrectly
   (2)." Whether the *task* succeeded is answered only by SisyphX's own
   verification step — never by the CLI's exit code or its own text claims.
   (This also motivates CHUNK-006's structured status line: even that is a
   self-report and must be treated as a hint, not evidence.)
3. **No hang risk from permission prompts specifically** — good news, but a
   subprocess-level timeout (CHUNK-003) is still required as a backstop against
   genuinely long-running or runaway tool use once bypass mode is enabled and
   the agent can actually execute arbitrary commands.
4. Error messages are informative enough (`Unknown model: ...`, `Failed to read
   prompt file ...`) that the loop can surface them directly in its run log
   without needing to parse/reinterpret them.

## Raw artifacts

- `test1_stdout.txt` / `test1_stderr.txt`
- `test2_stdout.txt` / `test2_stderr.txt`
- `test3a_stdout.txt` / `test3a_stderr.txt` (missing file)
- `test3b_stdout.txt` / `test3b_stderr.txt` (bad model)
- `test3c_stdout.txt` / `test3c_stderr.txt` (bad flag)
- `test4_stdout.txt` / `test4_stderr.txt` (Normal mode, declined)
- `test5_stdout.txt` / `test5_stderr.txt` (bypass mode, succeeded)
