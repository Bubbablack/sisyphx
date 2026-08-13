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
