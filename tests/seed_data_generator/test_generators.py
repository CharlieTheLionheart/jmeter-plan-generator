"""Tests for value generators."""

from __future__ import annotations

import random

import pytest
from hypothesis import given, strategies

from seed_data_generator.adapter import classify_val_range
from seed_data_generator.generators import SeedGenError, generate_column_values


class TestIntegerGenerators:
    def test_lower_bound(self):
        domain = classify_val_range("int8", ">=1")
        values = generate_column_values(domain, 100, nullable=False, null_rate=0.0)
        assert len(values) == 100
        assert all(isinstance(v, int) and v >= 1 for v in values)

    def test_upper_bound(self):
        domain = classify_val_range("int8", "<=100")
        values = generate_column_values(domain, 100, nullable=False, null_rate=0.0)
        assert all(isinstance(v, int) and v <= 100 for v in values)

    def test_closed_interval(self):
        domain = classify_val_range("int8", "[1,100]")
        values = generate_column_values(domain, 100, nullable=False, null_rate=0.0)
        assert all(1 <= v <= 100 for v in values)

    def test_open_interval(self):
        domain = classify_val_range("int8", "(1,100)")
        values = generate_column_values(domain, 100, nullable=False, null_rate=0.0)
        assert all(2 <= v <= 99 for v in values)

    def test_single_value_interval(self):
        domain = classify_val_range("int8", "[1,1]")
        values = generate_column_values(domain, 10, nullable=False, null_rate=0.0)
        assert all(v == 1 for v in values)

    def test_zero_intersection(self):
        domain = classify_val_range("int8", ">=0")
        values = generate_column_values(domain, 20, nullable=False, null_rate=0.0)
        assert all(v >= 0 for v in values)


class TestFloatGenerators:
    def test_float_lower_bound(self):
        domain = classify_val_range("float8", ">=0.0")
        values = generate_column_values(domain, 100, nullable=False, null_rate=0.0)
        assert all(isinstance(v, float) and v >= 0.0 for v in values)

    def test_float_closed_interval(self):
        domain = classify_val_range("float8", "[0.0,1.0]")
        values = generate_column_values(domain, 100, nullable=False, null_rate=0.0)
        assert all(0.0 <= v <= 1.0 for v in values)


class TestEnumAndRegex:
    def test_enum_cycles(self):
        domain = classify_val_range("varchar(16)", "enum:A,B,C")
        values = generate_column_values(domain, 7, nullable=False, null_rate=0.0)
        assert values == ["A", "B", "C", "A", "B", "C", "A"]

    def test_regex_matches_pattern(self):
        domain = classify_val_range("varchar(16)", "^[a-z]{3,6}$")
        values = generate_column_values(domain, 50, nullable=False, null_rate=0.0)
        assert all(isinstance(v, str) and v.isalpha() and v.islower() for v in values)
        assert all(3 <= len(v) <= 6 for v in values)


class TestNullHandling:
    def test_null_count_floor(self):
        domain = classify_val_range("int8", "[1,100]")
        values = generate_column_values(domain, 10, nullable=True, null_rate=0.3)
        assert values.count(None) == 3

    def test_null_rate_zero(self):
        domain = classify_val_range("int8", "[1,100]")
        values = generate_column_values(domain, 10, nullable=True, null_rate=0.0)
        assert None not in values

    def test_nullable_false(self):
        domain = classify_val_range("int8", "[1,100]")
        values = generate_column_values(domain, 10, nullable=False, null_rate=1.0)
        assert None not in values

    def test_invalid_null_rate(self):
        domain = classify_val_range("int8", "[1,100]")
        with pytest.raises(SeedGenError):
            generate_column_values(domain, 10, nullable=True, null_rate=1.5)

    def test_invalid_seed_num(self):
        domain = classify_val_range("int8", "[1,100]")
        with pytest.raises(SeedGenError, match="seed_num must be positive"):
            generate_column_values(domain, 0, nullable=False, null_rate=0.0)


# Property-based smoke tests for numeric domains.
@given(strategies.integers(min_value=1, max_value=1000))
def test_integer_closed_interval_property(seed_num):
    random.seed(seed_num)
    domain = classify_val_range("int8", "[10,20]")
    values = generate_column_values(domain, seed_num, nullable=False, null_rate=0.0)
    assert len(values) == seed_num
    assert all(10 <= v <= 20 for v in values)


@given(strategies.integers(min_value=1, max_value=500))
def test_null_count_never_exceeds_proportion(seed_num):
    random.seed(seed_num)
    domain = classify_val_range("int8", "[0,100]")
    values = generate_column_values(domain, seed_num, nullable=True, null_rate=0.31)
    assert values.count(None) <= int(0.31 * seed_num) + 1
