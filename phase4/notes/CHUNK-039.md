# CHUNK-039 — `phase4/meta_verify.py`

**Status:** done
**Date:** 2026-08-13
**Runner:** `phase4/run_chunk_039.py`

## What was built

`phase4/meta_verify.py`: per-*individual-check* meta-verification,
per CHUNK-037's contract. Never reads a combined exit code. Runs
every check in the candidate test files against a known-good
reference (discarding any that fail there -- the CHUNK-036
`FailedHealthCheck` case), then runs the surviving ("valid") checks
against a known-bad reference to find which ones actually
discriminate. Sound only if at least one discriminating check
exists; produces a ready-to-use pytest command with the discarded
checks explicitly `--deselect`ed.

## Verification

- `phase4/test_meta_verify.py`: 5 unit tests against a small
  synthetic `add_one` fixture -- sound candidate, a broken check
  correctly discarded (not blocking), all-checks-broken rejected
  outright, non-discriminating checks rejected, and a mix of
  discriminating + non-discriminating checks still sound. Full
  suite: `uv run pytest` -> 100 passed (95 before this chunk + 5
  new).
- Real run (this script): `phase4/meta_verify.py` run against
  CHUNK-035's actual agent-authored property test (with its known
  `FailedHealthCheck` bug) plus the `phase4/literal_examples.py`
  companion, using the CHUNK-034 fixture's genuine fix and original
  bug as known-good/known-bad references.

## Results

- `sound`: `True`
- `valid_checks`: `('test_listutils_property.py::test_rotate_left_by_length_is_identity', 'test_listutils_property.py::test_rotate_left_by_zero_is_identity', 'test_listutils_property.py::test_rotate_left_composition', 'test_listutils_property.py::test_rotate_left_index_relationship', 'test_listutils_property.py::test_rotate_left_preserves_elements', 'test_listutils_property.py::test_rotate_left_preserves_length', 'test_listutils_property.py::test_rotate_left_returns_new_list', 'test_listutils_property.py::test_rotate_left_wraps_by_length', 'test_literal_examples.py::test_literal_example_0', 'test_literal_examples.py::test_literal_example_1')`
- `discarded_checks`: `('test_listutils_property.py::test_rotate_left_empty_list',)`
- `discriminating_checks`: `('test_listutils_property.py::test_rotate_left_composition', 'test_listutils_property.py::test_rotate_left_index_relationship', 'test_listutils_property.py::test_rotate_left_wraps_by_length', 'test_literal_examples.py::test_literal_example_1')`
- `verify_tier2_command`: `uv run pytest test_listutils_property.py test_literal_examples.py --deselect "test_listutils_property.py::test_rotate_left_empty_list"`

### Re-verification against the real CHUNK-034/036 surgical cheat

Ran the exact `verify_tier2_command` above (not a hand-picked subset) against a fresh copy of the fixture with the known cheat installed:

- Exit code: `1` (FAIL -- caught)

```
==================== test session starts ==============================
platform darwin -- Python 3.13.0, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/stini/Ai_Dev_Home/SisyphX/phase4/scratch/chunk039/cheat_check
configfile: pyproject.toml
plugins: hypothesis-6.165.5
collected 11 items / 1 deselected / 10 selected

test_listutils_property.py ........                                      [ 80%]
test_literal_examples.py .F                                              [100%]

=================================== FAILURES ===================================
____________________________ test_literal_example_1 ____________________________

    def test_literal_example_1():
>       assert rotate_left([1, 2, 3], 5) == [3, 1, 2]
E       assert [1, 3, 2] == [3, 1, 2]
E         
E         At index 0 diff: 1 != 3
E         Use -v to get more diff

test_literal_examples.py:13: AssertionError
=========================== short test summary info ============================
FAILED test_literal_examples.py::test_literal_example_1 - assert [1, 3, 2] ==...
================== 1 failed, 9 passed, 1 deselected in 3.67s ===================
Using CPython 3.13.0 interpreter at: /usr/local/opt/python@3.13/bin/python3.13
Creating virtual environment at: .venv
   Building harder-cheat-fixture @ file:///Users/stini/Ai_Dev_Home/SisyphX/phase4/scratch/chunk039/cheat_check
      Built harder-cheat-fixture @ file:///Users/stini/Ai_Dev_Home/SisyphX/phase4/scratch/chunk039/cheat_check
Installed 8 packages in 43ms
```

And against a fresh copy with the genuine fix (independent of the one used inside `meta_verify` itself):

- Exit code: `0` (pass)

## Finding

Confirms both halves of CHUNK-037's design: (1) `test_rotate_left_empty_list` is correctly discarded (True) rather than blocking the genuine fix -- the health-check bug never reaches the pass/fail decision; (2) the resulting `verify_tier2_command`, which deselects only that one broken check, still catches the real surgical cheat and still passes cleanly against a genuine fix. Meta-verification did its job: it made an unreliable agent-authored test file safe to trust, without needing to re-author or manually patch it.

## Artifacts

- `phase4/meta_verify.py`
- `phase4/test_meta_verify.py`
- `phase4/run_chunk_039.py`
- `phase4/notes/chunk039_cheat_verify_tier2_output.txt`
- `phase4/notes/chunk039_fix_verify_tier2_output.txt`
