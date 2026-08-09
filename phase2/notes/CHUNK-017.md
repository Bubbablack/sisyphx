# CHUNK-017 — `FailureSignature` hashing

**Status:** done  
**Date:** 2026-08-09  
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.

## What was built

- `phase2/failure_signature.py` — implements `FailureSignature` (kind,
  normalized text, 16-char SHA-256 hash).
- `phase2/test_failure_signature.py` — `pytest` suite using the real captured
  outputs from CHUNK-015 and CHUNK-014 logs.

## Design

### Classification (`classify_failure`)

Uses the detection rule from CHUNK-014:

- `agent_timed_out == true` → `agent-timeout`
- `agent_exit_code == 1` and `agent_stderr` contains `Error: A tool was rejected by the user` → `guard`
- `agent_exit_code == 0` and `verify_exit_code == 0` → `verify-pass`
- `agent_exit_code == 0` and `verify_exit_code == -1` → `verify-timeout`
- `agent_exit_code == 0` and `verify_exit_code != 0` → `verify-fail`
- anything else → `agent-error`

### Normalization (`normalize_verify_output`)

Implements the CHUNK-015 recipe:

1. Strip ANSI.
2. Replace repo/rootdir paths with `<REPO>` / `<ROOTDIR>`.
3. Replace the pytest platform/version header with placeholders.
4. Remove `uv` build/install noise.
5. Replace `in X.XXs` with `in <DURATION>s`.
6. Replace line numbers in tracebacks with `<LINE>`, keeping file names.
7. Replace `File "path", line N` tracebacks with `File "<basename>", line <LINE>`.
8. Replace system-library paths with `<PYLIB>`.
9. Collapse redundant whitespace.

### Hashing

The hash input is built per failure kind:

- `guard` / `agent-error`: `kind`, `agent_exit_code`, `agent_stderr`
- `agent-timeout` / `verify-timeout`: `kind`, source (`agent` vs `verify`)
- `verify-fail` / `verify-pass`: `kind`, normalized `verify_output`

This keeps agent-side failures stable regardless of unrelated verify output,
and keeps verify failures stable even when volatile parts of the output change.

## Test results

`uv run pytest` → **38 passed** (15 from phase1 tests + 23 from
`phase2/test_failure_signature.py`).

Key assertions:

- `pytest_a` and `pytest_b` produce the same `FailureSignature`.
- `import_a` and `import_b` produce the same signature.
- `timeout_a` and `timeout_b` produce the same signature.
- `guard_a` and `guard_b` produce the same signature.
- All six representative failure classes are distinct from each other.
- Real CHUNK-014 guard and timeout log entries are classified correctly.

## Files

- `phase2/failure_signature.py`
- `phase2/test_failure_signature.py`
- `phase2/__init__.py` (so the module is importable by pytest)
- `pyproject.toml` updated to include `phase2/test_failure_signature.py`

## Implications

- The loop can now replace byte-identical failure comparison with a stable
  `FailureSignature` (CHUNK-018).
- Different failure causes (guard, timeout, verify-fail) are separated before
  the recovery ladder is consulted.
