# Devin CLI Contract for SisyphX's Loop

**Status:** final for Phase 1
**Date:** 2026-08-08
**Devin CLI version tested:** 3000.2.17 (2c489dfc)
**Supersedes:** all speculation in `PLAN.md`'s original design decisions —
this document is the empirically-confirmed source of truth. Individual test
transcripts live in `phase0/notes/CHUNK-00{1,2,3,4,5,6}.md`.

This is what `loop.py` (Phase 1, starting at CHUNK-009) implements against.

---

## 1. Invocation template

```bash
devin --permission-mode bypass -p --prompt-file <chunk_prompt.txt>
```

Run with `cwd` set to the target workspace. No other flags by default.

- **`-p`** — non-interactive, single-turn, prints response, exits. This is
  the only mode the loop uses (CHUNK-001).
- **`--prompt-file`** — always used instead of an inline string, so prompts
  can be arbitrarily long/multi-line without shell-quoting issues
  (CHUNK-001).
- **`--permission-mode bypass`** — required. Without it, any tool call
  needing approval (any write, any exec) is gracefully self-declined by
  Devin and the CLI still exits 0 having done nothing (CHUNK-001). We
  evaluated `--sandbox --permission-mode autonomous` as a safer alternative
  and **rejected it for Phase 1** (CHUNK-004): it doesn't restrict sub-paths
  within a workspace anyway (whole workspace is writable by default
  regardless of `Write()` grants), it needs explicit `Exec()` allow rules
  just to run shell commands non-interactively, and its approval behavior
  was inconsistent across near-identical prompts in testing. Real safety
  comes from hooks (§3 below) and SisyphX's own independent post-hoc checks,
  not from the permission mode.
- **No `-c`/`-r`/`--continue`/`--resume`** — never pass these. Every
  invocation is automatically a fresh, independent session with no shared
  memory (CHUNK-002, confirmed both directions: independence by default,
  and that `-c` correctly restores memory when explicitly requested, so this
  is deliberate behavior, not a bug we're relying on accidentally).

## 2. Exit codes and what they actually mean

| Exit code | Meaning | Does NOT mean |
|---|---|---|
| 0 | The CLI process ran to completion | **Never** "the task succeeded" — confirmed by CHUNK-001 Test 4, where the agent did nothing and still exited 0 |
| 1 | Runtime/semantic error (bad model, bad prompt file, hook-blocked action, ...) | — |
| 2 | CLI usage error (bad flag) — shouldn't happen once the loop's invocation is fixed | — |

**The exit code, and the agent's own text response, are never evidence of
task success.** Only SisyphX's own independent verification command (run
separately, immediately after, per Phase 1's design) decides pass/fail. This
principle is the throughline of every single finding in this phase.

## 3. Guards: `.devin/hooks.v1.json`, generated per attempt

Real path/command enforcement is a `PreToolUse` hook, written by the loop
before each attempt from the chunk's `permitted_paths` /
`prohibited_changes`, **not** a static file:

```json
{
  "PreToolUse": [
    {
      "matcher": "^(write|edit)$",
      "hooks": [{ "type": "command", "command": "python3 <path-to-guard>/guard_permitted_paths.py" }]
    },
    {
      "matcher": "exec",
      "hooks": [{ "type": "command", "command": "python3 <path-to-guard>/guard_destructive_git.py" }]
    }
  ]
}
```

Confirmed schema the guard scripts receive on stdin (CHUNK-005; not fully
documented upstream for `write`/`edit`):

| `tool_name` | `tool_input` fields |
|---|---|
| `write` | `file_path` (absolute), `content` |
| `edit` | `file_path` (absolute), `old_string`, `new_string` |
| `exec` | `command` |
| `read` | `file_path` (absolute) |

A guard blocks by printing `{"decision": "block", "reason": "..."}` and
exiting 2.

**Critical behavior: a hook block terminates the entire session
immediately** — exit code 1, output is exactly the single line `Error: A
tool was rejected by the user`, with **zero agent narration**, even about
steps that completed earlier in the same turn (CHUNK-005). This is a clean,
decisive signal (`loop.py` can detect it precisely), but:

- Whatever the agent already did earlier in the same turn is already on
  disk/committed — a hook abort doesn't undo prior progress within the turn.
- The loop gets no explanation from the agent about what led to the block —
  only the guard's own logged reason (if the loop captures the hook's own
  stdout/log separately) and the workspace diff are ground truth.
- Recovery must treat this as a **more serious failure category** than an
  ordinary verification failure — see §6.

Sandbox path/network containment (`--sandbox`) remains a candidate for
**Phase 2+ hardening** of the outer workspace boundary, once its
inconsistent approval behavior is either fixed upstream or worked around
with a fully-specified permission profile. Not a Phase 1 dependency.

## 4. Timeouts

No native `--timeout` flag exists (CHUNK-001). `loop.py` enforces its own,
using the **graceful pattern** (CHUNK-003):

```python
proc = subprocess.Popen(cmd, cwd=workspace, stdout=PIPE, stderr=PIPE, text=True)
try:
    stdout, stderr = proc.communicate(timeout=CHUNK_TIMEOUT_SECONDS)
except subprocess.TimeoutExpired:
    proc.terminate()          # SIGTERM
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()            # SIGKILL fallback
        proc.wait(timeout=5)
```

**Known, tested limitation: this reliably kills the `devin` process itself,
but never a shell command `devin` had already spawned via its own exec
tool** — confirmed three different ways (plain kill, process-group kill,
graceful SIGTERM). Devin puts spawned commands in their own process group
from the start; killing the parent just orphans them (reparented to
`launchd`). Mitigations:

- Pick a per-chunk timeout generous enough that hitting it is rare.
- Treat every timeout as an exceptional event: log loudly in
  `runs/log.jsonl`, flag that background processes *may* still be running
  and haven't been verified clean.
- A process-snapshot-diff safety net (`ps` before/after, kill anything new
  and now-orphaned) is deferred to Phase 2+, not blocking Phase 1.

Workspace state is **not corrupted** by a mid-task kill — files already
fully written stay intact; only the not-yet-attempted later steps simply
never happen (confirmed via repeated `slow.txt` content checks in CHUNK-003).

## 5. Structured status line (log annotation only)

Every chunk prompt ends with:

```
When you are finished (whether fully successful, partially successful, or
blocked), end your response with exactly one line in this exact format:
SISYPHX_STATUS: {"outcome": "done|blocked|partial", "summary": "<one short sentence>"}.
Use "done" only if fully successful, "blocked" if you could not proceed at
all, "partial" if you made some progress but did not finish.
```

Parsed by `status_parser.parse_status()` (CHUNK-006; 9/9 unit tests, 5/5 real
runs parsed correctly, including a correct `"blocked"` self-report on an
impossible task). **This is a hint for `runs/log.jsonl`, never a stop
condition** — stop conditions are verification pass / max iterations /
repeated failure signature only (per `PLAN.md` §4), determined by actually
running the project's verification command, not by anything the agent says
about itself.

## 6. Failure taxonomy for the loop (synthesized from all of Phase 0)

| Signal | What it means | Recovery weight |
|---|---|---|
| Exit 0, verification passes | Real success | Done |
| Exit 0, verification fails | Agent believes it's done (or self-reports `blocked`/`partial`) but isn't — the normal case | Standard retry ladder |
| Exit 1, `"A tool was rejected by the user"` | A guard fired — agent attempted something explicitly disallowed | More serious than a normal failure; same prompt will likely hit the same guard again — skip ahead on the recovery ladder rather than a plain retry |
| Exit 1, other message | Runtime error (bad model, bad prompt file, etc.) — shouldn't occur once the loop's own invocation is fixed; treat as a framework bug if it does | Investigate the loop itself, not the chunk |
| `TimeoutExpired` | Iteration killed after budget exceeded; background processes possibly leaked | Log loudly, verify workspace state, treat as exceptional |

## 7. What Phase 1 explicitly does NOT use (deferred, not forgotten)

- `--sandbox` (CHUNK-004 — inconsistent, not needed for the outer boundary
  that hooks already cover at the path level)
- Session resume `-c`/`-r` (not needed — loop never needs it, per CHUNK-002)
- `/loop` native slash command (untested whether it's even scriptable
  non-interactively; SisyphX needs its own loop regardless, for
  *independent* verification, which self-review can't provide)
