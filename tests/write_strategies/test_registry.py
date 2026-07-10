"""Tests for :mod:`write_strategies.registry`."""

from __future__ import annotations

import pytest

from write_strategies import (
    STRATEGY_REGISTRY,
    get_strategy,
    register_strategy,
    supported_modes,
)
from write_strategies.base import WriteStrategy
from write_strategies.batch_insert_strategy import BatchInsertStrategy
from write_strategies.batch_prepared_strategy import BatchPreparedStatementStrategy
from write_strategies.registry import UnknownWriteModeError
from write_strategies.schemaless_strategy import SchemalessWriteStrategy
from write_strategies.single_insert_strategy import SingleInsertStrategy
from write_strategies.single_prepared_strategy import SinglePreparedStatementStrategy


_EXPECTED_MODES = {
    "single_insert": SingleInsertStrategy,
    "batch_insert": BatchInsertStrategy,
    "single_prepared": SinglePreparedStatementStrategy,
    "batch_prepared": BatchPreparedStatementStrategy,
    "schemaless": SchemalessWriteStrategy,
}


class TestRegistryContents:
    def test_all_five_modes_registered(self):
        for mode, cls in _EXPECTED_MODES.items():
            assert mode in STRATEGY_REGISTRY, f"missing mode {mode}"
            assert STRATEGY_REGISTRY[mode] is cls

    def test_supported_modes_returns_sorted_list(self):
        modes = supported_modes()
        assert modes == sorted(modes)
        assert set(modes) == set(_EXPECTED_MODES.keys())


class TestGetStrategy:
    def test_returns_correct_class(self):
        for mode, cls in _EXPECTED_MODES.items():
            instance = get_strategy(mode)
            assert isinstance(instance, cls)

    @pytest.mark.parametrize(
        "mode", ["single_insert", "batch_insert", "single_prepared", "batch_prepared"]
    )
    def test_known_modes_produce_write_strategy(self, mode):
        assert isinstance(get_strategy(mode), WriteStrategy)

    def test_unknown_mode_raises_value_error(self):
        with pytest.raises(ValueError):
            get_strategy("unknown_mode")

    def test_unknown_mode_error_lists_supported_modes(self):
        with pytest.raises(UnknownWriteModeError) as exc:
            get_strategy("nope")
        msg = str(exc.value)
        for mode in _EXPECTED_MODES.keys():
            assert mode in msg

    def test_non_string_mode_raises_value_error(self):
        with pytest.raises(ValueError):
            get_strategy(123)  # type: ignore[arg-type]


class TestRegisterStrategy:
    def test_register_new_strategy(self):
        class _Custom(WriteStrategy):
            @property
            def mode_name(self):
                return "custom_test_mode"

            def requires_prepared_insert_template(self):
                return False

            def generate_query(self, **context):
                return ""

            def get_sampler_type(self):
                return "JDBCSampler"

            def get_sampler_config(self):
                return {}

            def requires_param_setup(self):
                return False

            def get_preprocessor_code(self, **context):
                return None

            def get_sampler_script(self):
                return None

        register_strategy("custom_test_mode", _Custom)
        try:
            assert get_strategy("custom_test_mode").mode_name == "custom_test_mode"
        finally:
            # Clean up the global registry to keep tests hermetic.
            STRATEGY_REGISTRY.pop("custom_test_mode", None)

    def test_register_with_empty_mode_rejected(self):
        with pytest.raises(Exception):
            register_strategy("", SingleInsertStrategy)

    def test_register_with_non_subclass_rejected(self):
        class _NotAStrategy:
            pass

        with pytest.raises(Exception):
            register_strategy("invalid", _NotAStrategy)  # type: ignore[arg-type]