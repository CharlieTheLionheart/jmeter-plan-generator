"""Tests for column name normalization and generation."""

import pytest

from column_namer import generate_column_names, normalize_type, prefix_for_group


def test_normalize_varchar():
    assert normalize_type("varchar(16)") == "varchar"


def test_normalize_decimal():
    assert normalize_type("decimal(10,2)") == "decimal"


def test_normalize_int8():
    assert normalize_type("int8") == "int8"


def test_normalize_array():
    assert normalize_type("float[]") == "float"


def test_normalize_whitespace():
    assert normalize_type("  VARCHAR(64)  ") == "varchar"


def test_prefix_for_known_groups():
    assert prefix_for_group("data_cols") == "col"
    assert prefix_for_group("primary_tags") == "ptag"
    assert prefix_for_group("regular_tags") == "rtag"
    assert prefix_for_group("primary_keys") == "pk"


def test_prefix_for_unknown_group():
    with pytest.raises(ValueError, match="unknown column group"):
        prefix_for_group("unknown")


def test_generate_data_col_names():
    assert generate_column_names("data_cols", "int8", 3) == [
        "col_int8_1",
        "col_int8_2",
        "col_int8_3",
    ]


def test_generate_primary_tag_names():
    assert generate_column_names("primary_tags", "varchar(10)", 2) == [
        "ptag_varchar_1",
        "ptag_varchar_2",
    ]


def test_generate_zero_count():
    assert generate_column_names("data_cols", "int8", 0) == []
