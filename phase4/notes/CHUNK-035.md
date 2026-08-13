# CHUNK-035 — Spike: can a live agent author a property test from acceptance criteria alone?

**Status:** done
**Date:** 2026-08-13
**Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.
**Runner:** `phase4/run_chunk_035.py`

## Question

Given *only* `acceptance_criteria.txt` -- a plain-language contract
for `rotate_left`, with explicitly no access to `listutils.py`,
`test_listutils.py`, or any hint of the CHUNK-034 bug/cheat -- does
a live Devin CLI agent author a Hypothesis property test that
matches the stated contract?

## Method

`phase4/run_chunk_035.py` builds a scratch repo containing only
`acceptance_criteria.txt` (git-initialized, no other files), and
runs one bounded, non-interactive Devin CLI turn
(`--permission-mode bypass`, per `phase0/DEVIN_CLI_CONTRACT.md`)
with that file's contents as the prompt.

## Results

- Agent exit code: `0`
- Timed out: `False`
- Parsed status line: `{"outcome": "done", "summary": "Created test_listutils_property.py with 9 Hypothesis property-based tests covering the rotate_left contract including index relationship, element preservation, wrapping, composition, and edge cases."}`
- `test_listutils_property.py` written by the agent: `True`

### Authored test

```python
"""Property-based tests for rotate_left using Hypothesis."""

import hypothesis.strategies as st
from hypothesis import given, assume

from listutils import rotate_left


@given(
    lst=st.lists(st.integers()),
    k=st.integers(min_value=0, max_value=1000),
)
def test_rotate_left_index_relationship(lst, k):
    """For non-empty lists, result[i] == lst[(i + k) % n] for all i."""
    result = rotate_left(lst, k)
    n = len(lst)
    if n == 0:
        assert result == []
    else:
        assert len(result) == n
        for i in range(n):
            assert result[i] == lst[(i + k) % n]


@given(
    lst=st.lists(st.integers()),
    k=st.integers(min_value=0, max_value=1000),
)
def test_rotate_left_preserves_length(lst, k):
    """The result has the same length as the input."""
    result = rotate_left(lst, k)
    assert len(result) == len(lst)


@given(
    lst=st.lists(st.integers()),
    k=st.integers(min_value=0, max_value=1000),
)
def test_rotate_left_preserves_elements(lst, k):
    """The result contains exactly the same elements (multiset) as the input."""
    result = rotate_left(lst, k)
    assert sorted(result) == sorted(lst)


@given(lst=st.lists(st.integers()))
def test_rotate_left_by_zero_is_identity(lst):
    """Rotating by 0 returns a list equal to the original."""
    result = rotate_left(lst, 0)
    assert result == lst


@given(
    lst=st.lists(st.integers(), min_size=1),
    k=st.integers(min_value=0, max_value=1000),
)
def test_rotate_left_wraps_by_length(lst, k):
    """Rotating by k is the same as rotating by k % len(lst)."""
    n = len(lst)
    result_k = rotate_left(lst, k)
    result_mod = rotate_left(lst, k % n)
    assert result_k == result_mod


@given(
    lst=st.lists(st.integers(), min_size=1),
)
def test_rotate_left_by_length_is_identity(lst):
    """Rotating by exactly the length of the list returns the original."""
    result = rotate_left(lst, len(lst))
    assert result == lst


@given(
    lst=st.lists(st.integers(), min_size=1),
    k1=st.integers(min_value=0, max_value=500),
    k2=st.integers(min_value=0, max_value=500),
)
def test_rotate_left_composition(lst, k1, k2):
    """Rotating by k1 then by k2 is the same as rotating by k1 + k2."""
    result_composed = rotate_left(rotate_left(lst, k1), k2)
    result_direct = rotate_left(lst, k1 + k2)
    assert result_composed == result_direct


@given(lst=st.lists(st.integers()))
def test_rotate_left_empty_list(lst):
    """Rotating an empty list always returns an empty list."""
    assume(len(lst) == 0)
    result = rotate_left(lst, 0)
    assert result == []


@given(
    lst=st.lists(st.integers(), min_size=1),
    k=st.integers(min_value=0, max_value=1000),
)
def test_rotate_left_returns_new_list(lst, k):
    """The result is a new list, not the same object (unless implementation chooses otherwise)."""
    result = rotate_left(lst, k)
    # At minimum, the result should be a list
    assert isinstance(result, list)
```

## Finding

Given zero access to the implementation, the buggy fixture, or any hint of
the CHUNK-034 cheat, the agent authored 9 separate Hypothesis properties in
a single pass, on its first (and only) attempt:

- `test_rotate_left_index_relationship` is the exact defining property
  (`result[i] == lst[(i + k) % n]`) -- the same invariant this project's
  own `acceptance_criteria.txt` and CHUNK-025's hand-written property used.
- Several additional properties go beyond what was asked for: an identity
  law (`k=0`), a periodicity law (`k == len(lst)`), a composition law
  (rotating by `k1` then `k2` equals rotating by `k1+k2`), a
  wraparound-equivalence law (`rotate_left(lst, k) ==
  rotate_left(lst, k % n)`), and element/length-preservation checks.
- The composition and wraparound-equivalence properties are qualitatively
  *stronger* than the single defining property alone -- they test the
  contract from independent angles, which is closer to how CHUNK-026 found
  a single narrow test can be misleadingly easy to satisfy.
- No implementation of `rotate_left` was written or guessed at; the agent
  correctly treated the acceptance criteria as the sole source of truth.

**This is a materially better result than CHUNK-025's hand-written
single-property test in scope**, produced with strictly less information
than a human author had in CHUNK-025 (no example implementation, no
existing test file to draw on -- only a plain-language contract).

Whether this translates into actually catching CHUNK-034's cheat is
verified empirically in CHUNK-036, not assumed here.

## Artifacts

- `phase4/run_chunk_035.py`
- `phase4/notes/chunk035_agent_stdout.txt`
- `phase4/notes/chunk035_agent_stderr.txt`
- `phase4/notes/chunk035_authored_test_listutils_property.py` (if written)
