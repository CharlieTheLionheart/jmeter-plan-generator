"""Tests for DDL generator error handling and boundary conditions."""

import pytest

from config_parser.models import ColTypeConfig, RelDbConfig, RelTableConfig, TsDbConfig, TsTableConfig, TestModelConfig
from ddl_generator import DDLGenerator
from ddl_generator.generator import DdlGenerationError


def test_reserved_keyword_identifier():
    model = TestModelConfig(
        rel_dbs=[RelDbConfig(name="select", tables=[RelTableConfig(
            name="t",
            primary_key_count=1,
            data_col_count=0,
            primary_keys=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
            data_cols=[],
        )])]
    )
    with pytest.raises(DdlGenerationError, match="reserved keyword"):
        DDLGenerator(model).generate()


def test_unknown_data_type():
    model = TestModelConfig(
        rel_dbs=[RelDbConfig(name="db", tables=[RelTableConfig(
            name="t",
            primary_key_count=1,
            data_col_count=0,
            primary_keys=[ColTypeConfig(col_type="unknown", type_proportion=1.0)],
            data_cols=[],
        )])]
    )
    with pytest.raises(DdlGenerationError, match="unsupported data type"):
        DDLGenerator(model).generate()


def test_table_with_no_columns():
    model = TestModelConfig(
        rel_dbs=[RelDbConfig(name="db", tables=[RelTableConfig(
            name="t",
            primary_key_count=0,
            data_col_count=0,
            primary_keys=[],
            data_cols=[],
        )])]
    )
    with pytest.raises(DdlGenerationError, match="no columns"):
        DDLGenerator(model).generate()


def test_ts_table_with_no_tags_or_data():
    model = TestModelConfig(
        ts_dbs=[TsDbConfig(name="db", tables=[TsTableConfig(
            name="t",
            data_col_count=0,
            primary_tag_count=0,
            regular_tag_count=0,
            data_cols=[],
            primary_tags=[],
            regular_tags=[],
        )])]
    )
    with pytest.raises(DdlGenerationError, match="no usable columns"):
        DDLGenerator(model).generate()
