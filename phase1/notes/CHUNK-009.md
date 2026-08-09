# CHUNK-009 — `loop.py`: single iteration + stubbed-subprocess tests

**Status:** done  
**Date:** 2026-08-08  
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12, `uv`-managed pytest in the scratch target repo.

## What was built

`phase1/loop.py` — a minimal, single-file Ralph-style loop with no framework
scaffolding yet. It deliberately uses only `argparse`, `subprocess`, `json`,
`re`, `time`, `pathlib`, and `git`.

`phase1/test_loop.py` — unit tests for `loop.py`. All calls to the real `devin`
CLI are stubbed via `unittest.mock.patch` so the suite runs offline in a few
seconds. Git operations are tested against real throwaway `tmp_path` repos
because mocking git would just test the mock.

## Method

1. Wrote `loop.py` against the contract in `phase0/DEVIN_CLI_CONTRACT.md`:
   - `devin --permission-mode bypass -p --prompt-file <file>`
   - no `-c`/`-r` flags (fresh session every iteration)
   - `subprocess.Popen` + `communicate(timeout=...)` for bounded iterations
   - graceful `SIGTERM` → `SIGKILL` on agent timeout
   - independent verification via `subprocess.run(..., shell=True)` — never
     through the agent's own exec tool
   - structured `SISYPHX_STATUS` line requested in the prompt and regex-parsed
     from stdout
2. Wrote `test_loop.py` covering:
   - `parse_status` (JSON, bare word, last-match-wins, absent)
   - `build_prompt` (first iteration, previous failure inclusion, truncation)
   - `run_devin` (normal completion, SIGTERM, SIGKILL, prompt-file writing,
     command contract)
   - `git_commit_iteration` (commits when changed, no-op when clean)
   - `ensure_gitignored` (creates `.gitignore`, idempotent)
3. Created `phase1/target_repo/`:
   - tiny `calc.py` with a known bug (`return x` instead of `return x + 1`)
   - `test_calc.py` with `test_add_one` and `test_double`
   - `pyproject.toml` + `uv.lock` so `uv run pytest` is the verification command
4. Ran one real manual single-iteration of `loop.py` against `target_repo`.

## Results

### Unit tests

All 15 tests passed:

```
$ uv run pytest test_loop.py -v
... 15 passed in 2.28s
```

### Real single-iteration run

```
$ python3 loop.py --repo target_repo --task task_fix_calc.txt --verify "uv run pytest" --max-iterations 1 --agent-timeout 300
=== iteration 1/1 ===
    agent_exit=0 timed_out=False status={'outcome': 'done', ...} verify_exit=0 passed=True sha=7b6f78f2 committed=True
=== PASSED on iteration 1 ===
```

Independent verification (not trusting the loop's own report):

- `calc.py` diff: `return x` → `return x + 1` (minimal, correct)
- `test_calc.py` untouched
- Fresh `uv run pytest` in `target_repo` → **2 passed**
- Git log shows exactly two commits:
  - `966dc96 Initial state: calc.py has a bug, test_add_one fails`
  - `7b6f78f SisyphX loop iteration 1 [PASS]`

## Artifacts produced

- `phase1/loop.py`
- `phase1/test_loop.py`
- `phase1/target_repo/`
- `phase1/target_repo/.agent-state/runs/log.jsonl` (first real log)
- `phase1/target_repo/.agent-state/runs/001/{prompt,agent_stdout,agent_stderr,verify_output}.txt`

## Implications / learnings

1. The Phase 0 contract translates cleanly into ~250 lines of plain Python.
2. Stubbed-subprocess tests are fast and give confidence in command shape,
   timeout behavior, and prompt construction without calling the real CLI.
3. Real manual run confirmed the end-to-end wiring: Devin receives the prompt,
   edits `calc.py`, exits 0, loop runs `uv run pytest` independently, sees
   exit 0, and commits.
4. `SISYPHX_STATUS` parsing worked as expected. The agent's self-report
   (`outcome: done`, summary) is treated as a log annotation, not ground truth —
   the only pass/fail source is `verify_exit == 0`.

## Open question carried forward

- How do we prevent the agent from making its own `git commit` calls in
  `--permission-mode bypass`? Not a problem in a single passing iteration (the
  loop commits first and no further work happens), but it becomes visible in
  CHUNK-010's unsolvable run, where Devin creates an extra commit itself.
  Phase 2 needs a guard (git hook / role permission) here.
