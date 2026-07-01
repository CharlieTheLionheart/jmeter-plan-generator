"""Tests for ColumnNameGenerator."""

from config_parser.models import ColTypeConfig, RelTableConfig
from ddl_generator import ColumnNameGenerator


def _table() -> RelTableConfig:
    return RelTableConfig(
        name="t",
        primary_key_count=1,
        data_col_count=1,
        primary_keys=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
        data_cols=[ColTypeConfig(col_type="varchar(16)", type_proportion=1.0)],
    )


def test_generate_primary_key():
    gen = ColumnNameGenerator(_table())
    assert gen.generate_primary_keys("int8", 1) == ["pk_int8_1"]


def test_generate_data_col_strips_length():
    gen = ColumnNameGenerator(_table())
    assert gen.generate_data_cols("varchar(16)", 1) == ["col_varchar_1"]


def test_generate_primary_tag():
    gen = ColumnNameGenerator(_table())
    assert gen.generate_primary_tags("int8", 2) == ["ptag_int8_1", "ptag_int8_2"]


def test_generate_regular_tag():
    gen = ColumnNameGenerator(_table())
    assert gen.generate_regular_tags("varchar(10)", 1) == ["rtag_varchar_1"]


def test_sequence_increments_independently():
    gen = ColumnNameGenerator(_table())
    assert gen.generate_data_cols("int8", 3) == [
        "col_int8_1",
        "col_int8_2",
        "col_int8_3",
    ]
    assert gen.generate_data_cols("varchar(8)", 2) == [
        "col_varchar_1",
        "col_varchar_2",
    ]
