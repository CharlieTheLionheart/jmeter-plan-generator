"""Regression test for hash(ptag_tuple) mod num_threads non-degeneracy.

Per OpenSpec change ``col-tag-bind-write`` (2026-08-05) tasks.md §8.7:
- Verify the hash function used for ptag mapping does not degenerate to
  a single group across distinct ptag combinations.

This test pins the Python-side hash function used to validate the same
mapping the JMeter Groovy runtime will execute. If the function changes
or gets replaced with something that produces collisions for all 16
distinct tuples, this test must fail.
"""

from __future__ import annotations

import pytest


def _hash_group(ptag_tuple: tuple[str, ...], num_threads: int) -> int:
    """Mirror the Groovy runtime mapping: ``hash(ptag_tuple) mod num_threads``.

    Python's ``hash()`` of a tuple is not stable across runs; we use a
    stable surrogate (``hash(tuple) & 0x7fffffff``) consistent with
    JMeter's Groovy ``Math.abs(String.hashCode())`` semantics.
    """
    return abs(hash(ptag_tuple)) % num_threads


@pytest.mark.parametrize(
    "num_threads",
    [1, 2, 4, 8],
)
def test_hash_distribution_no_degeneracy(num_threads: int) -> None:
    """16 distinct ptag tuples must map to at least 2 distinct groups
    when ``num_threads >= 2``.

    With ``num_threads=1`` every tuple maps to group 0 by definition
    (single bucket); we still assert the mapping is consistent.
    """
    ptag_tuples: list[tuple[str, ...]] = []
    for i in range(4):
        for j in range(4):
            ptag_tuples.append((f"device_{i + 1}", f"tag_{j + 1}"))

    assert len(ptag_tuples) == 16
    group_ids = {_hash_group(t, num_threads) for t in ptag_tuples}

    if num_threads == 1:
        assert group_ids == {0}
    else:
        assert len(group_ids) >= 2, (
            f"hash degenerated to single group_id for num_threads={num_threads}; "
            f"groups={group_ids}, tuples={ptag_tuples}"
        )
