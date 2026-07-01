"""Tests for column_namer allocation algorithm."""

import pytest

from column_namer import allocate_columns


def test_exact_proportions():
    assert allocate_columns(100, [0.25, 0.25, 0.5]) == [25, 25, 50]


def test_fractional_proportions():
    result = allocate_columns(10, [0.33, 0.33, 0.34])
    assert sum(result) == 10
    # One of the first two should get the extra column because they have
    # the largest fractional parts (0.33 vs 0.34).
    assert sorted(result) == [3, 3, 4]


def test_zero_total():
    assert allocate_columns(0, [0.5, 0.5]) == []


def test_empty_proportions():
    assert allocate_columns(10, []) == []


def test_negative_proportion():
    with pytest.raises(ValueError, match="negative"):
        allocate_columns(10, [-0.1, 1.1])


def test_proportions_not_sum_to_one():
    with pytest.raises(ValueError, match="sum to 1.0"):
        allocate_columns(10, [0.5, 0.4])


def test_total_less_than_proportion_count():
    result = allocate_columns(2, [0.25, 0.25, 0.25, 0.25])
    assert sum(result) == 2
    assert all(c in (0, 1) for c in result)
