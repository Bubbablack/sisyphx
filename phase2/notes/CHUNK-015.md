# CHUNK-015 — Failure-output normalization study

**Status:** done  
**Date:** 2026-08-09  
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.  
**Runner:** `phase2/run_chunk_015.py`

## Goal

Identify volatile parts of verification output and propose a normalization
recipe so the same failure produces the same `FailureSignature` while
different failures remain distinct.

## Sources

- Real `verify_output` artifacts from earlier runs:
  - `phase2/scratch/chunk014/*/verify_output.txt` (guard, normal)
  - `.agent-state/runs/001/verify_output.txt` (SisyphX self-test)
- Fresh deliberate failures generated in `phase2/scratch/chunk015/`:
  - `pytest_fail` — `uv run pytest` on the `target_repo` bug.
  - `import_error` — `calc.py` imports a missing module.
  - `timeout` — `sleep 5` killed at 1s.
  - `guard` — empty verify output from a guard-aborted run.

## Volatile parts identified

- **Durations:** `in 0.05s`, `in 0.16s`, etc.
- **Absolute / project-relative workspace paths:** `rootdir:` and paths like
  `phase2/scratch/chunk015/pytest_a/test_calc.py` (rootdir is the SisyphX
  root, so the scratch subdir shows up in `ERROR collecting ...` lines).
- **Platform / Python / pytest / pluggy versions** in the pytest header.
- **`uv` build/install noise:** `Building ...`, `Built ...`, `Uninstalled ...`,
  `Installed ...`, plus the `file:///...` URLs and package install durations.
- **Line numbers** in tracebacks (`test_calc.py:5: AssertionError` and
  `File "calc.py", line 4`).
- **System-library paths** (`/usr/local/Cellar/.../importlib/__init__.py`).
- **Timestamps** are not present in these outputs but the recipe would strip
  `\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}` if they appear.

## Proposed normalization recipe

1. Strip ANSI escape sequences.
2. Replace the repo's absolute path and its path relative to the workspace root
   with `<REPO>`; replace the workspace root with `<ROOTDIR>`.
3. Replace the pytest platform/versions header with placeholders.
4. Remove `uv` build/install lines.
5. Replace durations `in X.XXs` with `in <DURATION>s`.
6. Replace line numbers in `file.py:5:` and `File "file", line 5` tracebacks
   with `<LINE>`, keeping the file name.
7. Replace system-library paths with `<PYLIB>`.
8. Collapse redundant whitespace.

The actual assertion values and error messages are intentionally preserved;
they are part of the failure identity.

## Demonstration

| Output | Exit | Raw hash | Normalized hash |
|---|---|---|---|
| pytest_a | — | 3a5d8ba7e7101ff5 | ee4d6250c785b7e8 |
| pytest_b | — | ee3da32048521044 | ee4d6250c785b7e8 |
| import_a | — | 0e4aa4484e79d863 | a012f20415586d22 |
| import_b | — | 440ab41308e55745 | a012f20415586d22 |
| timeout_a | — | 4576d47c45d41805 | 4586085b9449f286 |
| timeout_b | — | 4576d47c45d41805 | 4586085b9449f286 |
| guard_a | — | e3b0c44298fc1c14 | e3b0c44298fc1c14 |
| guard_b | — | e3b0c44298fc1c14 | e3b0c44298fc1c14 |
| sisyphx_selftest | — | 63525d833c9c8aa3 | e447215c126c5cca |
| chunk014_normal_a | — | 571d2c4427d38a19 | 475a0fec8ac0af9d |

### Same failure, two repetitions

- pytest_fail: ['pytest_a', 'pytest_b'] normalized hashes match = True
- import_error: ['import_a', 'import_b'] normalized hashes match = True
- timeout: ['timeout_a', 'timeout_b'] normalized hashes match = True
- guard: ['guard_a', 'guard_b'] normalized hashes match = True

### Different failures

- pytest_a vs import_a: different = True
- pytest_a vs timeout_a: different = True
- pytest_a vs guard_a: different = True
- pytest_a vs sisyphx_selftest: different = True
- pytest_a vs chunk014_normal_a: different = True
- import_a vs timeout_a: different = True
- import_a vs guard_a: different = True
- import_a vs sisyphx_selftest: different = True
- import_a vs chunk014_normal_a: different = True
- timeout_a vs guard_a: different = True
- timeout_a vs sisyphx_selftest: different = True
- timeout_a vs chunk014_normal_a: different = True
- guard_a vs sisyphx_selftest: different = True
- guard_a vs chunk014_normal_a: different = True
- sisyphx_selftest vs chunk014_normal_a: different = True

## Implications

- The normalization recipe is sufficient to make two runs of the same failure
  produce identical SHA-256 hashes, while different failure classes remain
  distinct.
- `FailureSignature` (CHUNK-017) should hash the normalized `verify_output`
  together with the agent failure kind (guard/normal/timeout) and the key
  loop-side signals (`agent_exit_code`, `agent_timed_out`, `agent_stderr`).
- Empty `verify_output` (e.g. guard or a `false` verify command) can still
  produce a stable signature by combining it with the agent-side signal.
