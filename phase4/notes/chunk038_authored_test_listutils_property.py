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
