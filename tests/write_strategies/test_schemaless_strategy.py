"""Tests for :class:`write_strategies.schemaless_strategy.SchemalessWriteStrategy`."""

from __future__ import annotations

import pytest

from write_strategies import ResolvedTable, WriteRuntime, WriteStrategy
from write_strategies.schemaless_strategy import SchemalessWriteStrategy


def _table():
    return ResolvedTable(fqn="iot_monitor.t", columns=["ts", "c1"])


class TestSchemalessContract:
    def test_inherits_write_strategy(self):
        assert issubclass(SchemalessWriteStrategy, WriteStrategy)

    def test_mode_name(self):
        assert SchemalessWriteStrategy().mode_name == "schemaless"

    def test_does_not_require_prepared_template(self):
        assert (
            SchemalessWriteStrategy().requires_prepared_insert_template() is False
        )

    def test_sampler_type(self):
        assert SchemalessWriteStrategy().get_sampler_type() == "JSR223Sampler"

    def test_sampler_config(self):
        assert SchemalessWriteStrategy().get_sampler_config() == {
            "scriptLanguage": "groovy"
        }

    def test_does_not_require_param_setup(self):
        assert SchemalessWriteStrategy().requires_param_setup() is False

    def test_generate_query_returns_empty(self):
        assert SchemalessWriteStrategy().generate_query(_table()) == ""

    def test_get_preprocessor_code_returns_none(self):
        assert (
            SchemalessWriteStrategy().get_preprocessor_code(
                _table(), batch_lines=1, runtime=WriteRuntime()
            )
            is None
        )


class TestSchemalessSamplerScript:
    def test_raises_not_implemented(self):
        s = SchemalessWriteStrategy()
        with pytest.raises(NotImplementedError) as exc:
            s.get_sampler_script(_table())
        assert "Schemaless write strategy is not yet implemented (T2)" in str(exc.value)