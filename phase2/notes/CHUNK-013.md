# CHUNK-013 — Can a `PreToolUse`/`exec` hook block `git` commands in `--permission-mode bypass`?

**Status:** done  
**Date:** 2026-08-09  
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.  
**Guard:** `phase2/guard_git_commands.py`  

## Question

In `--permission-mode bypass`, does Devin still fire `PreToolUse` hooks for the `exec` tool? Specifically, can a hook block `git commit` and `git push` before they execute?

## Method

- Wrote `phase2/guard_git_commands.py` as a `PreToolUse`/`exec` hook that blocks any `exec` command matching `\bgit\s+(?:commit|push)\b` and allows everything else.
- Generated three scratch repos under `phase2/scratch/`:
  - `test_repo_control` — no git commands, only `echo`/`cat`.
  - `test_repo_commit` — runs `echo`, `git add -A`, `git commit`, `git push`.
  - `test_repo_push` — has an unpushed local commit and only runs `git push`.
- Each repo contains `.devin/hooks.v1.json` pointing to the absolute guard path.
- Ran, from each repo:
  ```bash
  devin --permission-mode bypass -p --prompt-file prompt.txt \
      > phase2/notes/test{01,02,03}_*_stdout.txt \
      2> phase2/notes/test{01,02,03}_*_stderr.txt
  ```
- Independently checked disk state and `git log` in each repo, and the bare remote `remote.git` for the push test.

## Results

### Test 1 — allowed non-git exec

- **Command:** `cd test_repo_control && devin --permission-mode bypass -p --prompt-file prompt.txt`
- **Exit code:** `0`
- **Stdout:** `Done. allowed.txt now contains allowed exec.` + `SISYPHX_STATUS: ...`
- **Disk after:** `allowed.txt` created, no new git commit.

### Test 2 — `git commit` blocked

- **Command:** `cd test_repo_commit && devin --permission-mode bypass -p --prompt-file prompt.txt`
- **Exit code:** `1`
- **Stderr (combined/stdout):** exactly `Error: A tool was rejected by the user`
- **Disk after:** `agent.txt` exists and is staged, but `git log` still only shows `Initial`. The `git commit` never executed.
- This confirms the hook allowed `git add -A` and only blocked `git commit`.

### Test 3 — `git push` blocked

- **Command:** `cd test_repo_push && devin --permission-mode bypass -p --prompt-file prompt.txt`
- **Exit code:** `1`
- **Stderr:** exactly `Error: A tool was rejected by the user`
- **Remote before:** `2f1e331 Initial`
- **Remote after:** still `2f1e331 Initial` — the unpushed commit `efba2d2` never reached the bare remote.
- **Local log:** still `efba2d2 unpushed commit` / `5061f7a Initial`.

## Findings

1. **Hooks absolutely fire in `--permission-mode bypass`.** A `PreToolUse`/`exec` hook can block `git commit` and `git push` before they run.
2. **The block signal is identical to CHUNK-005:** exit code `1`, output `Error: A tool was rejected by the user`, no agent narration, no status line.
3. **Other git subcommands and non-git exec still pass.** `git add -A` ran successfully in Test 2; `echo`/`cat` succeeded in Test 1.
4. **The block is a real prevent, not just an error message.** Independent `git log` and `git ls-remote` checks prove the blocked commands produced no side effects.

## Implications for the loop

- A `PreToolUse`/`exec` hook is a viable first line of defense against agent-authored commits (CHUNK-019).
- Because the block aborts the whole session, the loop cannot let the agent "try again" with the same prompt; it must escalate/replan.
- The guard can be fine-grained: allow benign git commands (`status`, `add`, `log`) while blocking `commit`/`push`.

## Artifacts

- `phase2/guard_git_commands.py`
- `phase2/scratch/test_repo_control/`
- `phase2/scratch/test_repo_commit/`
- `phase2/scratch/test_repo_push/`
- `phase2/scratch/remote.git` (bare remote)
- `phase2/notes/test01_control_stdout.txt`
- `phase2/notes/test02_commit_stderr.txt`
- `phase2/notes/test03_push_stderr.txt`
