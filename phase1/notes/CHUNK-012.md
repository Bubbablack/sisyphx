# CHUNK-012 — Point the loop at SisyphX's own repo

**Status:** done  
**Date:** 2026-08-09  
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.

## What was built

A real self-hosted task: the loop ran against the SisyphX repository itself and
produced a verified, committed `pyproject.toml` with no hand-written code.

## Setup

1. Initialized `git` in the SisyphX root (it had not been a git repo before).
2. Created a root `.gitignore` ignoring:
   - build/runtime artifacts (`.agent-state/`, `.venv/`, `__pycache__/`, etc.)
   - the embedded scratch/demo repos (`phase0/scratch/`,
     `phase1/target_repo/`, `phase1/target_repo_unsolvable/`)
3. Made an initial hand-authored commit of the existing Phase 0 and Phase 1
   framework files.
4. Created `task_sisyphx_pyproject.txt` at the repo root.

## Method

Ran the Phase 1 loop against the repo root:

```
$ python3 phase1/loop.py \
    --repo . \
    --task task_sisyphx_pyproject.txt \
    --verify 'test -f pyproject.toml &&
              grep -E "^\s*name\s*=\s*\"sisyphx\"" pyproject.toml &&
              grep -E "^\s*version\s*=\s*\"0\.1\.0\"" pyproject.toml &&
              grep -q pytest pyproject.toml &&
              grep -q testpaths pyproject.toml &&
              uv run pytest -q' \
    --max-iterations 2 \
    --agent-timeout 300
```

The verification command enforces:
- `pyproject.toml` exists
- project name `sisyphx` and version `0.1.0`
- `pytest` is declared
- `testpaths` is configured
- `uv run pytest -q` passes

## Results

- **Iteration 1 passed.**
- `pyproject.toml` created by the agent:

```toml
[project]
name = "sisyphx"
version = "0.1.0"
description = "A Python-based control and reliability framework for AI coding agents."
requires-python = ">=3.11"

[dependency-groups]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["phase1/test_loop.py", "phase1/tests/test_run_log.py"]
```

- `uv.lock` generated.
- Loop committed: `1f12b02 SisyphX loop iteration 1 [PASS]`
- Independent verification from repo root:

```
$ uv run pytest -v
... 23 passed in 3.27s
```

The loop successfully made a verified, hand-code-free contribution to its own
project.

## Implications / learnings

1. **Self-hosting is possible at this primitive level.** The loop can improve
   SisyphX's own repo, not just disposable scratch repos.
2. **Verification for self-hosted tasks can be a composite shell command.** We
   did not need a full test suite in the root before this task; the agent
   created the metadata that *enables* a proper `uv run pytest` invocation.
3. **Input task files can get committed by `git add -A`.** The task file
   `task_sisyphx_pyproject.txt` was untracked and ended up in the commit. This
   is harmless for a first self-hosted run, but Phase 2 should either place
   task files in a dedicated, possibly gitignored, directory or make the
   commit logic ignore untracked input artifacts.
4. **Embedded demo repos need to be excluded from the outer repo.**
   `phase0/scratch/`, `phase1/target_repo/`, and
   `phase1/target_repo_unsolvable/` carry their own `.git` histories. The root
   `.gitignore` keeps the outer repo clean and prevents gitlink/submodule
   confusion.
5. **`testpaths` as file paths works but is unconventional.** The agent chose
   `testpaths = ["phase1/test_loop.py", "phase1/tests/test_run_log.py"]`
   rather than `testpaths = ["phase1"]`. Both produce 23 passing tests, but a
   future task may want to broaden `testpaths` to `phase1` so new tests are
   discovered automatically.
