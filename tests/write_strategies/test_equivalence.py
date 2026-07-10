"""Equivalence tests: strategy outputs match the legacy direct_insert_write module.

Closes review.md §2 "重构前后输出等价性验证标准" and tasks.md §10.

For every shape that both code paths produce, the outputs must be byte-
identical. This guards the refactor (task 8.x) against silent drift and
gives a smoke-test path that exercises both implementations side-by-side.
"""

from __future__ import annotations

import pytest

from direct_insert_write.preprocessor_generator import generate_preprocessor_script
from direct_insert_write.sql_generator import (
    generate_batch_insert_sql,
    generate_single_insert_sql,
)
from write_strategies import ResolvedTable, WriteRuntime, get_strategy


def _table_config():
    return {
        "db": "iot_monitor",
        "table": "t_cnc",
        "columns": ["ts", "ptag_int8_1", "col_int8_1"],
        "first_ptag_column": "ptag_int8_1",
    }


def _columns():
    return ["ts", "ptag_int8_1", "col_int8_1"]


def _resolved():
    return ResolvedTable(
        fqn="iot_monitor.t_cnc",
        columns=_columns(),
        table_config=_table_config(),
    )


def _runtime():
    return WriteRuntime(
        device_per_thread=2, ms_step=1000, device_start=0, batch_seq_init=0
    )


class TestSingleInsertEquivalence:
    def test_generate_query_matches_legacy(self):
        s = get_strategy("single_insert")
        strategy_sql = s.generate_query(_resolved())
        legacy_sql = generate_single_insert_sql("iot_monitor.t_cnc", _columns())
        assert strategy_sql == legacy_sql

    def test_sampler_metadata_matches_jdbc_sampler_contract(self):
        s = get_strategy("single_insert")
        assert s.get_sampler_type() == "JDBCSampler"
        assert s.get_sampler_config() == {"usePrepared": False}

    def test_preprocessor_matches_legacy(self):
        s = get_strategy("single_insert")
        strategy_script = s.get_preprocessor_code(
            _resolved(), batch_lines=1, runtime=_runtime()
        )
        legacy_script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=2,
            ms_step=1000,
            device_start=0,
            batch_seq_init=0,
            batch_lines=1,
        )
        assert strategy_script == legacy_script


class TestBatchInsertEquivalence:
    def test_generate_query_matches_legacy(self):
        s = get_strategy("batch_insert")
        strategy_sql = s.generate_query(_resolved(), batch_lines=10)
        legacy_sql = generate_batch_insert_sql(
            "iot_monitor.t_cnc", _columns(), 10
        )
        assert strategy_sql == legacy_sql

    def test_generate_query_with_row_count_matches_legacy(self):
        s = get_strategy("batch_insert")
        strategy_sql = s.generate_query(
            _resolved(), batch_lines=10, row_count=4
        )
        legacy_sql = generate_batch_insert_sql(
            "iot_monitor.t_cnc", _columns(), 10, row_count=4
        )
        assert strategy_sql == legacy_sql

    def test_sampler_metadata_matches_jdbc_sampler_contract(self):
        s = get_strategy("batch_insert")
        assert s.get_sampler_type() == "JDBCSampler"
        assert s.get_sampler_config() == {"usePrepared": False}

    def test_preprocessor_matches_legacy(self):
        s = get_strategy("batch_insert")
        # Batch uses batch_lines > 1; preprocessor helper takes the kwarg.
        legacy_script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=2,
            ms_step=1000,
            device_start=0,
            batch_seq_init=0,
            batch_lines=5,
        )
        strategy_script = s.get_preprocessor_code(
            _resolved(), batch_lines=5, runtime=_runtime()
        )
        assert strategy_script == legacy_script


class TestStrategySmoke:
    """Smoke test that the registry path is the same as direct module imports."""

    @pytest.mark.parametrize(
        "mode,expected_class_name",
        [
            ("single_insert", "SingleInsertStrategy"),
            ("batch_insert", "BatchInsertStrategy"),
            ("single_prepared", "SinglePreparedStatementStrategy"),
            ("batch_prepared", "BatchPreparedStatementStrategy"),
            ("schemaless", "SchemalessWriteStrategy"),
        ],
    )
    def test_get_strategy_returns_expected(self, mode, expected_class_name):
        s = get_strategy(mode)
        assert s.__class__.__name__ == expected_class_name