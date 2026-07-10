"""Caller-side None-handling tests.

Closes review.md §3 "测试覆盖" gap:
- single_insert / batch_insert ``get_sampler_script()`` returns ``None``.
- Writers must skip JSR223 factory calls when the strategy script is None.

The ``WriteStrategy`` contract marks the returned value as ``Optional[str]``;
callers that build JMX elements must treat ``None`` as "don't emit a
JSR223Sampler body".
"""

from __future__ import annotations

from unittest.mock import patch

from config_parser.models import WriteConfig
from jmx_skeleton_generator.generators import write_groups
from write_strategies import ResolvedTable
from write_strategies.batch_insert_strategy import BatchInsertStrategy
from write_strategies.single_insert_strategy import SingleInsertStrategy


class TestSamplerScriptReturnsNone:
    def test_single_insert_returns_none(self):
        s = SingleInsertStrategy()
        assert (
            s.get_sampler_script(ResolvedTable(fqn="db.t", columns=["c1"])) is None
        )

    def test_batch_insert_returns_none(self):
        s = BatchInsertStrategy()
        assert (
            s.get_sampler_script(ResolvedTable(fqn="db.t", columns=["c1"])) is None
        )


class TestCallerSkipsGroovyEmission:
    """When a write config's mode maps to a strategy whose sampler script is
    None (single_insert / batch_insert / single_prepared), the JMX builder
    must not invoke the JSR223 factory.

    The contract under test is in :func:`write_groups.generate_write_thread_groups`:
    only ``single_prepared`` / ``batch_prepared`` flow through the builder;
    the rest are skipped at the top of the loop.
    """

    def test_caller_skips_groovy_emission_when_none(self):
        wc = WriteConfig(
            tbl_name="iot_monitor.t_cnc",
            mode="single_insert",
            batch_lines=1,
        )
        with patch(
            "jmx_skeleton_generator.generators.write_groups.jsr223_sampler_element"
        ) as jsr223_factory:
            results = write_groups.generate_write_thread_groups(
                write_config=[wc],
                prepared_templates={},
            )
        # single_insert is filtered out at write_groups.py:120; no samplers emitted.
        assert results == []
        jsr223_factory.assert_not_called()
