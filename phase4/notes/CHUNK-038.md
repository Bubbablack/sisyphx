# CHUNK-038 — `phase4/test_author.py`

**Status:** done
**Date:** 2026-08-13
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.
**Runner:** `phase4/run_chunk_038.py`

## What was built

`phase4/test_author.py`: the real, promoted implementation of
CHUNK-035's throwaway spike script. Config-driven
(`author_property_test(repo, acceptance_criteria_path,
test_filename, timeout)`) -- not hardcoded to the CHUNK-034
fixture's `rotate_left` scenario, confirmed by a unit test using a
different acceptance-criteria filename and a different expected
output filename.

## Verification

- `phase4/test_test_author.py`: 7 unit tests with stubbed
  `subprocess.Popen` covering normal completion, no-file-written,
  timeout (SIGTERM then SIGKILL escalation, same convention as
  `phase1/loop.py::run_devin`), prompt-file contents, and the
  config-driven (non-hardcoded) claim. Full suite: `uv run pytest`
  -> 95 passed (88 before this chunk + 7 new).
- Real run (this script): same experimental setup as CHUNK-035 (a
  scratch repo containing only `acceptance_criteria.txt`), calling
  the real `phase4.test_author.author_property_test` instead of
  the throwaway spike script.

## Results

- Agent exit code: `0`
- Timed out: `False`
- Parsed status: `{"outcome": "done", "summary": "Created Hypothesis property tests for rotate_left contract."}`
- Test file written: `True`

### Authored test

```python
"""Property-based tests for rotate_left in listutils.py."""

from hypothesis import given, strategies as st

from listutils import rotate_left


@given(lst=st.lists(st.integers()), k=st.integers(min_value=0))
def test_rotate_left_contract(lst, k):
    """Check the formal contract: result[i] == lst[(i + k) % n]."""
    result = rotate_left(lst, k)
    n = len(lst)

    assert len(result) == n
    assert result == [lst[(i + k) % n] for i in range(n)]


@given(lst=st.lists(st.integers()), k=st.integers(min_value=0))
def test_rotate_left_is_pure_and_preserves_multiset(lst, k):
    """rotate_left must not mutate the input and must keep the same elements."""
    original = list(lst)
    result = rotate_left(lst, k)

    assert lst == original, "rotate_left must not mutate its input list"
    assert len(result) == len(original)
    assert sorted(result) == sorted(original)


@given(lst=st.lists(st.integers()))
def test_rotate_left_zero_is_identity(lst):
    """Rotating by zero positions returns an equal list."""
    assert rotate_left(lst, 0) == lst


@given(lst=st.lists(st.integers(), min_size=1), m=st.integers(min_value=0))
def test_rotate_left_wraps_by_full_length(lst, m):
    """Rotating by a multiple of the list length is equivalent to rotating by 0."""
    n = len(lst)
    assert rotate_left(lst, m * n) == lst
```

## Finding

The promoted module reproduces CHUNK-035's real result: given only
the acceptance criteria, the agent authored a property-test file
without ever seeing an implementation. (Whether this specific
authored test would catch the CHUNK-034 cheat is not re-verified
here -- that empirical question was already answered once for
CHUNK-035's authored test in CHUNK-036/037, and CHUNK-039's
meta-verification step is what will make that judgment
systematically going forward, not a one-off re-check per authoring
run.)

## Artifacts

- `phase4/test_author.py`
- `phase4/test_test_author.py`
- `phase4/run_chunk_038.py`
- `phase4/notes/chunk038_agent_stdout.txt`
- `phase4/notes/chunk038_agent_stderr.txt`
- `phase4/notes/chunk038_authored_test_listutils_property.py` (if written)
