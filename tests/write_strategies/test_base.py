"""Tests for the abstract :class:`write_strategies.WriteStrategy` base class."""

from __future__ import annotations

import pytest

from write_strategies.base import WriteStrategy, WriteStrategyError


class _Dummy(WriteStrategy):
    """Minimal concrete subclass used to exercise the base helper."""

    @property
    def mode_name(self) -> str:
        return "dummy"

    def requires_prepared_insert_template(self) -> bool:
        return False

    def generate_query(self, **context):
        return ""

    def get_sampler_type(self) -> str:
        return "JDBCSampler"

    def get_sampler_config(self) -> dict:
        return {"usePrepared": False, "extra": 7}

    def requires_param_setup(self) -> bool:
        return False

    def get_preprocessor_code(self, **context):
        return None

    def get_sampler_script(self):
        return None


class _Bad:
    """Does not subclass WriteStrategy — used to fail instantiation tests."""


class TestWriteStrategyABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            WriteStrategy()  # type: ignore[abstract]

    def test_dummy_is_a_write_strategy(self):
        assert isinstance(_Dummy(), WriteStrategy)


class TestGetConfigHelper:
    def test_returns_value_when_key_present(self):
        s = _Dummy()
        assert s.get_config("usePrepared") is False

    def test_returns_default_when_missing(self):
        s = _Dummy()
        assert s.get_config("missing", default="fallback") == "fallback"

    def test_returns_none_when_missing_and_no_default(self):
        s = _Dummy()
        assert s.get_config("missing") is None

    def test_non_dict_config_returns_default(self):
        class _BadCfg(WriteStrategy):
            @property
            def mode_name(self) -> str:
                return "bad"

            def requires_prepared_insert_template(self) -> bool:
                return False

            def generate_query(self, **context):
                return ""

            def get_sampler_type(self) -> str:
                return ""

            def get_sampler_config(self):  # not a dict
                return ["nope"]

            def requires_param_setup(self) -> bool:
                return False

            def get_preprocessor_code(self, **context):
                return None

            def get_sampler_script(self):
                return None

        s = _BadCfg()
        assert s.get_config("anything", default="x") == "x"


class TestWriteStrategyError:
    def test_is_exception(self):
        assert issubclass(WriteStrategyError, Exception)