# CHUNK-005 — Working `PreToolUse` hook

**Status:** done
**Date:** 2026-08-08
**Scripts:** `phase0/hook_debug.py`, `phase0/guard_permitted_paths.py`,
`phase0/guard_destructive_git.py`

## Method

### Step 1 — learn the real schema (debug hook)

A `PreToolUse` hook with an empty matcher (matches everything) logging raw
stdin JSON to `phase0/notes/hook_debug_log.jsonl`, exit 0 always (observe
only). Ran a prompt doing a `write` (new file), an `edit` (existing file), and
an `exec` (shell command).

**Real schema observed** (not fully documented for `write`/`edit` in the
docs, which only spelled out `exec`):

| `tool_name` | `tool_input` fields |
|---|---|
| `write` | `file_path` (absolute), `content` |
| `edit` | `file_path` (absolute), `old_string`, `new_string` |
| `exec` | `command` |
| `read` | `file_path` (absolute) |

Note `write` and `edit` are **separate** tool names (the permissions doc's
tool-name list only mentions `edit`, not `write` — the hooks matcher needs
both, e.g. `"^(write|edit)$"`).

### Step 2 — real guards

- `guard_permitted_paths.py`: blocks `write`/`edit` whose `file_path` isn't
  under a hardcoded `allowed_src/` prefix (demo stand-in for a chunk's real
  `permitted_paths`).
- `guard_destructive_git.py`: blocks `exec` commands matching destructive
  patterns (`git push --force`, `git reset --hard`, `git clean -f*`, `rm -rf`,
  `git branch -D`), per spec section 12.

Both print `{"decision": "block", "reason": "..."}` and exit 2 on violation,
exit 0 otherwise.

### Test 13 — one session, four attempts

Asked Devin (bypass mode) to attempt, in order: (1) write inside
`allowed_src/` [should succeed], (2) write at the workspace root, outside
`allowed_src/` [should be blocked], (3) `git reset --hard HEAD` [should be
blocked], (4) `git status` [should succeed] — and to keep going regardless of
outcome, reporting SUCCESS/BLOCKED for each.

**It did not get to report anything.** The whole session aborted:

- Exit code: **1**
- Full output (stdout+stderr combined): exactly `Error: A tool was rejected
  by the user` — **one line, nothing else**. No partial narration, no
  agent-authored explanation of what it had done so far.

Independently verified on disk:

| Check | Result |
|---|---|
| `allowed_src/ok.txt` | exists, contains `OK_ALLOWED` — step 1 **succeeded** before the abort |
| `blocked_write.txt` | does not exist — step 2 correctly **never happened** |
| `git status` on `README.md` | still shows `M` (modified, uncommitted) — proof `git reset --hard HEAD` did **not** run (that command would have reverted this modification if it had executed) |
| steps 3/4 | never reached — session terminated at the first block (step 2) |

## Key finding: a hook block aborts the whole turn, not just that one action

This is different from a normal tool error, which the agent can typically
see and work around. **In non-interactive `-p` mode, a `PreToolUse` hook
returning `"decision": "block"` (exit 2) is treated the same as a human
interactively rejecting the action — and the entire CLI invocation
terminates immediately** with exit code 1 and the generic message `Error: A
tool was rejected by the user`. Whatever the agent had already done earlier
in the same turn stays done (step 1's write persisted), but there is no
final response, no self-report, and no chance for the agent to adapt and
continue with unaffected remaining work.

## Implications for the loop and recovery design

1. **This is actually a clean, decisive signal, not a messy one.** Exit code
   1 + the literal substring `"A tool was rejected by the user"` is
   unambiguous and easy for `loop.py` to detect as its own distinct outcome
   category — different from a normal non-zero exit (runtime error) or exit 0
   with a failing verification.
2. **A guard violation should not just trigger a plain retry.** Recovery
   should treat "hook blocked an action" as a more serious signal than an
   ordinary test failure — the agent attempted something explicitly
   disallowed. Re-running the identical prompt risks hitting the same guard
   again for the same reason. This belongs further down the recovery ladder
   (investigation / replan) rather than "one targeted retry."
3. **The agent gets zero narration in this failure mode** — reinforces (yet
   again) that SisyphX cannot rely on the agent's own text output as
   evidence of anything when this path triggers. The workspace diff and git
   state are the only ground truth.
4. **The guard worked exactly as intended otherwise**: the allowed write
   went through with no friction, the disallowed write never touched disk,
   and the destructive git command never ran (confirmed via its absence of
   side-effect, not just absence of output).
5. Real SisyphX guards will be **generated per-chunk** from
   `ImplementationChunk.permitted_paths`/`prohibited_changes` (and a shared,
   reviewed destructive-command policy) into a `.devin/hooks.v1.json` written
   before each attempt — not hand-maintained like this spike's hardcoded
   prefix list.

## Raw artifacts

- `hook_debug_log.jsonl` (schema discovery)
- `test12_stdout.txt` (debug pass, all 3 actions succeeded, no guards active)
- `test13_stdout.txt` (guard pass — one line, session aborted)
