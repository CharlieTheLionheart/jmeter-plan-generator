"""Tests for :class:`write_strategies.single_insert_strategy.SingleInsertStrategy`."""

from __future__ import annotations

import pytest

from write_strategies import ResolvedTable, WriteRuntime, WriteStrategy, WriteStrategyError
from write_strategies.single_insert_strategy import SingleInsertStrategy


def _table(fqn="iot_monitor.t_cnc", columns=("ts", "ptag_int8_1", "col_int8_1"), config=None):
    return ResolvedTable(fqn=fqn, columns=list(columns), table_config=config or {})


class TestSingleInsertContract:
    def test_inherits_write_strategy(self):
        assert issubclass(SingleInsertStrategy, WriteStrategy)

    def test_mode_name_returns_single_insert(self):
        s = SingleInsertStrategy()
        assert s.mode_name == "single_insert"

    def test_does_not_require_prepared_template(self):
        s = SingleInsertStrategy()
        assert s.requires_prepared_insert_template() is False

    def test_sampler_type_is_jdbc(self):
        s = SingleInsertStrategy()
        assert s.get_sampler_type() == "JDBCSampler"

    def test_sampler_config_uses_update_statement(self):
        s = SingleInsertStrategy()
        cfg = s.get_sampler_config()
        assert cfg == {"usePrepared": False}

    def test_requires_param_setup(self):
        s = SingleInsertStrategy()
        assert s.requires_param_setup() is True

    def test_get_sampler_script_is_none(self):
        s = SingleInsertStrategy()
        assert s.get_sampler_script(_table()) is None


class TestSingleInsertGenerateQuery:
    def test_default_query_format(self):
        s = SingleInsertStrategy()
        sql = s.generate_query(
            _table(fqn="iot_monitor.t_cnc", columns=["ts", "ptag_int8_1", "col_int8_1"])
        )
        assert sql == (
            "insert into iot_monitor.t_cnc "
            "(ts, ptag_int8_1, col_int8_1) values (?, ?, ?)"
        )

    def test_columns_are_lowercased(self):
        s = SingleInsertStrategy()
        sql = s.generate_query(_table(fqn="DB.T", columns=["A", "B"]))
        assert "insert into db.t" in sql
        assert "(a, b)" in sql

    def test_empty_columns_raises(self):
        s = SingleInsertStrategy()
        with pytest.raises(WriteStrategyError):
            s.generate_query(_table(fqn="iot_monitor.t", columns=[]))

    def test_unqualified_table_raises(self):
        s = SingleInsertStrategy()
        with pytest.raises(WriteStrategyError):
            s.generate_query(_table(fqn="t", columns=["c1"]))


class TestSingleInsertPreprocessorCode:
    def test_returns_groovy_string(self):
        s = SingleInsertStrategy()
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
            batch_lines=1,
            runtime=WriteRuntime(device_per_thread=2),
        )
        assert isinstance(script, str)
        # Groovy helper decls are camelCase (cf. utils/preprocessor_helpers.py).
        assert "calculateTimestamps" in script
        assert "calculateDeviceNumber" in script
        assert "cloneRows" in script

    def test_missing_table_config_keys_raises(self):
        s = SingleInsertStrategy()
        with pytest.raises(WriteStrategyError):
            s.get_preprocessor_code(
                _table(config={"db": "iot_monitor", "columns": ["c1"]}),
                batch_lines=1,
                runtime=WriteRuntime(device_per_thread=2),
            )

    def test_invalid_device_per_thread_raises(self):
        s = SingleInsertStrategy()
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
                batch_lines=1,
                runtime=WriteRuntime(device_per_thread=0),
            )
