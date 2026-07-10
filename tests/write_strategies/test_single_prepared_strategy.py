"""Tests for :class:`write_strategies.single_prepared_strategy.SinglePreparedStatementStrategy`."""

from __future__ import annotations

import pytest

from write_strategies import ResolvedTable, WriteRuntime, WriteStrategy, WriteStrategyError
from write_strategies.single_prepared_strategy import SinglePreparedStatementStrategy


_TEMPLATE = (
    "insert into iot_monitor.t_cnc (ts, ptag_int8_1, col_int8_1) values (?, ?, ?)"
)


def _table(fqn="iot_monitor.t_cnc", columns=("ts", "ptag_int8_1", "col_int8_1")):
    return ResolvedTable(fqn=fqn, columns=list(columns))


class TestSinglePreparedContract:
    def test_inherits_write_strategy(self):
        assert issubclass(SinglePreparedStatementStrategy, WriteStrategy)

    def test_mode_name(self):
        s = SinglePreparedStatementStrategy()
        assert s.mode_name == "single_prepared"

    def test_requires_prepared_template(self):
        assert (
            SinglePreparedStatementStrategy().requires_prepared_insert_template()
            is True
        )

    def test_sampler_type(self):
        assert SinglePreparedStatementStrategy().get_sampler_type() == "JDBCSampler"

    def test_sampler_config(self):
        assert SinglePreparedStatementStrategy().get_sampler_config() == {
            "usePrepared": True
        }

    def test_requires_param_setup(self):
        assert SinglePreparedStatementStrategy().requires_param_setup() is True

    def test_sampler_script_is_none(self):
        assert SinglePreparedStatementStrategy().get_sampler_script(_table()) is None


class TestSinglePreparedGenerateQuery:
    def test_returns_supplied_template(self):
        s = SinglePreparedStatementStrategy()
        sql = s.generate_query(_table(), insert_template=_TEMPLATE)
        assert sql == _TEMPLATE
        assert sql.count("?") == 3

    def test_none_template_raises(self):
        s = SinglePreparedStatementStrategy()
        with pytest.raises(WriteStrategyError):
            s.generate_query(_table())


class TestSinglePreparedPreprocessorCode:
    def test_returns_groovy_with_table(self):
        s = SinglePreparedStatementStrategy()
        script = s.get_preprocessor_code(
            _table(),
            batch_lines=1,
            runtime=WriteRuntime(device_per_thread=1),
        )
        assert isinstance(script, str)
        assert "iot_monitor.t_cnc" in script
        assert "calculateDeviceNumber" in script
