"""Tests for :class:`write_strategies.batch_insert_strategy.BatchInsertStrategy`."""

from __future__ import annotations

import pytest

from write_strategies import ResolvedTable, WriteRuntime, WriteStrategy, WriteStrategyError
from write_strategies.batch_insert_strategy import BatchInsertStrategy


def _table(fqn="iot_monitor.t_cnc", columns=("ts", "c1", "c2"), config=None):
    return ResolvedTable(fqn=fqn, columns=list(columns), table_config=config or {})


class TestBatchInsertContract:
    def test_inherits_write_strategy(self):
        assert issubclass(BatchInsertStrategy, WriteStrategy)

    def test_mode_name(self):
        assert BatchInsertStrategy().mode_name == "batch_insert"

    def test_does_not_require_prepared_template(self):
        assert BatchInsertStrategy().requires_prepared_insert_template() is False

    def test_sampler_type(self):
        assert BatchInsertStrategy().get_sampler_type() == "JDBCSampler"

    def test_sampler_config(self):
        assert BatchInsertStrategy().get_sampler_config() == {"usePrepared": False}

    def test_requires_param_setup(self):
        assert BatchInsertStrategy().requires_param_setup() is True

    def test_sampler_script_is_none(self):
        assert BatchInsertStrategy().get_sampler_script(_table()) is None


class TestBatchInsertGenerateQuery:
    def test_default_query_emits_batch_lines_rows(self):
        s = BatchInsertStrategy()
        sql = s.generate_query(
            _table(fqn="iot_monitor.t_cnc", columns=["ts", "c1", "c2"]),
            batch_lines=10,
        )
        assert sql.startswith("insert into iot_monitor.t_cnc (ts, c1, c2) values ")
        assert sql.count("(?, ?, ?)") == 10

    def test_tail_row_count(self):
        s = BatchInsertStrategy()
        sql = s.generate_query(
            _table(fqn="iot_monitor.t", columns=["c1"]),
            batch_lines=10,
            row_count=3,
        )
        # 3 tuples of "(?)" — total placeholder count still equals row_count * cols.
        assert sql.count("(?)") == 3
        assert sql.count("?") == 3

    def test_missing_batch_lines_raises(self):
        s = BatchInsertStrategy()
        with pytest.raises(WriteStrategyError):
            s.generate_query(_table(fqn="iot_monitor.t", columns=["c1"]), batch_lines=None)

    def test_zero_batch_lines_raises(self):
        s = BatchInsertStrategy()
        with pytest.raises(WriteStrategyError):
            s.generate_query(_table(fqn="iot_monitor.t", columns=["c1"]), batch_lines=0)

    def test_empty_columns_raises(self):
        s = BatchInsertStrategy()
        with pytest.raises(WriteStrategyError):
            s.generate_query(_table(fqn="iot_monitor.t", columns=[]), batch_lines=5)


class TestBatchInsertPreprocessorCode:
    def test_returns_groovy_for_full_batch(self):
        s = BatchInsertStrategy()
        script = s.get_preprocessor_code(
            _table(
                fqn="iot_monitor.t_cnc",
                columns=["ts", "ptag_int8_1", "col_int8_1"],
                config={
                    "db": "iot_monitor",
                    "table": "t_cnc",
                    "columns": ["ts", "ptag_int8_1", "col_int8_1"],
                    "first_ptag_column": "ptag_int8_1",
                },
            ),
            batch_lines=10,
            runtime=WriteRuntime(device_per_thread=2),
        )
        assert isinstance(script, str)
        assert "calculateTimestamps" in script
        assert "calculateDeviceNumber" in script

    def test_missing_batch_lines_raises(self):
        s = BatchInsertStrategy()
        with pytest.raises(WriteStrategyError):
            s.get_preprocessor_code(
                _table(
                    config={
                        "db": "iot_monitor",
                        "table": "t",
                        "columns": ["ts", "c1"],
                        "first_ptag_column": "c1",
                    },
                ),
                batch_lines=None,
                runtime=WriteRuntime(device_per_thread=1),
            )

    def test_invalid_device_per_thread_raises(self):
        s = BatchInsertStrategy()
        with pytest.raises(WriteStrategyError):
            s.get_preprocessor_code(
                _table(
                    config={
                        "db": "iot_monitor",
                        "table": "t",
                        "columns": ["ts", "c1"],
                        "first_ptag_column": "c1",
                    },
                ),
                batch_lines=5,
                runtime=WriteRuntime(device_per_thread=0),
            )
