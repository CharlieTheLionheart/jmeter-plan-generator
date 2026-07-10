"""Tests for :class:`write_strategies.batch_prepared_strategy.BatchPreparedStatementStrategy`."""

from __future__ import annotations

import pytest

from write_strategies import ResolvedTable, WriteRuntime, WriteStrategy, WriteStrategyError
from write_strategies.batch_prepared_strategy import (
    DEFAULT_BATCH_SIZE_MAX,
    DEFAULT_CONNECTION_TIMEOUT_MS,
    BatchPreparedStatementStrategy,
)


_TEMPLATE = "insert into iot_monitor.t_cnc (ts, ptag_int8_1) values (?, ?)"


def _table(fqn="iot_monitor.t_cnc", columns=("ts", "ptag_int8_1")):
    return ResolvedTable(fqn=fqn, columns=list(columns))


class TestBatchPreparedContract:
    def test_inherits_write_strategy(self):
        assert issubclass(BatchPreparedStatementStrategy, WriteStrategy)

    def test_mode_name(self):
        assert BatchPreparedStatementStrategy().mode_name == "batch_prepared"

    def test_requires_prepared_template(self):
        assert (
            BatchPreparedStatementStrategy().requires_prepared_insert_template()
            is True
        )

    def test_sampler_type(self):
        assert (
            BatchPreparedStatementStrategy().get_sampler_type() == "JSR223Sampler"
        )

    def test_sampler_config_includes_groovy_language_and_caps(self):
        cfg = BatchPreparedStatementStrategy().get_sampler_config()
        assert cfg["scriptLanguage"] == "groovy"
        assert cfg["batchSizeMax"] == DEFAULT_BATCH_SIZE_MAX
        assert cfg["connectionTimeoutMs"] == DEFAULT_CONNECTION_TIMEOUT_MS

    def test_custom_batch_caps_appear_in_config(self):
        cfg = BatchPreparedStatementStrategy(
            batch_size_max=500,
            connection_timeout_ms=10_000,
        ).get_sampler_config()
        assert cfg["batchSizeMax"] == 500
        assert cfg["connectionTimeoutMs"] == 10_000

    def test_requires_param_setup(self):
        assert BatchPreparedStatementStrategy().requires_param_setup() is True


class TestBatchPreparedGenerateQuery:
    def test_returns_supplied_template(self):
        s = BatchPreparedStatementStrategy()
        assert s.generate_query(_table(), insert_template=_TEMPLATE) == _TEMPLATE

    def test_none_template_raises(self):
        s = BatchPreparedStatementStrategy()
        with pytest.raises(WriteStrategyError):
            s.generate_query(_table())


class TestBatchPreparedSamplerScript:
    def test_returns_groovy_body_with_caps(self):
        s = BatchPreparedStatementStrategy(
            batch_size_max=500,
            connection_timeout_ms=10_000,
        )
        script = s.get_sampler_script(_table())
        assert isinstance(script, str)
        assert "executeBatch" in script
        assert "rollback" in script
        assert "500" in script
        assert "10000" in script
        assert "calculateDeviceNumber" in script

    def test_empty_fqn_raises(self):
        s = BatchPreparedStatementStrategy()
        with pytest.raises(WriteStrategyError):
            s.get_sampler_script(_table(fqn=""))


class TestBatchPreparedPreprocessorCode:
    def test_returns_none(self):
        s = BatchPreparedStatementStrategy()
        assert (
            s.get_preprocessor_code(
                _table(), batch_lines=1, runtime=WriteRuntime()
            )
            is None
        )


class TestBatchPreparedBoundaryValidation:
    def test_zero_batch_size_max_rejected(self):
        with pytest.raises(WriteStrategyError):
            BatchPreparedStatementStrategy(batch_size_max=0)

    def test_negative_connection_timeout_rejected(self):
        with pytest.raises(WriteStrategyError):
            BatchPreparedStatementStrategy(connection_timeout_ms=-1)
