"""Tests for query-side throughput literal embedding (design decision 18).

The query timer carries the literal numeric value of
``QueryConfig.throughput`` in the timer body — NO JMeter variable
wrapping — so per-query overrides do not require a UDV.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from config_parser.models import QueryConfig
from jmx_skeleton_generator.generators.query_groups import (
    generate_query_thread_groups,
)


def _make_qc(query: str = "SELECT * FROM db.t WHERE col = ?", throughput: float = 4.0) -> QueryConfig:
    return QueryConfig(query=query, throughput=throughput, num_threads=1)


def _render_xml(results) -> str:
    return "".join(ET.tostring(e, encoding="unicode") for e in results)


def _timer(results):
    return [e for e in results if e.tag.endswith("ConstantThroughputTimer")]


def _timer_throughput_text(timer):
    return next(
        p.text
        for p in timer.iter()
        if p.tag.endswith("stringProp") and p.attrib.get("name") == "throughput"
    )


class TestQueryTimerLiteral:
    def test_throughput_is_literal(self):
        results = generate_query_thread_groups([_make_qc(throughput=4.0)])
        timer = _timer(results)[0]
        assert _timer_throughput_text(timer) == "4"

    def test_zero_decimal_dropped_for_integer_values(self):
        results = generate_query_thread_groups([_make_qc(throughput=12.0)])
        timer = _timer(results)[0]
        assert _timer_throughput_text(timer) == "12"

    def test_small_floating_value_preserved(self):
        results = generate_query_thread_groups([_make_qc(throughput=0.016666667)])
        timer = _timer(results)[0]
        assert _timer_throughput_text(timer) == "0.016666667"

    def test_distinct_throughputs_produce_distinct_literals(self):
        cfg_a = _make_qc(throughput=4.0)
        cfg_b = _make_qc(throughput=12.0)
        results = generate_query_thread_groups([cfg_a, cfg_b])
        timers = _timer(results)
        assert len(timers) == 2
        assert _timer_throughput_text(timers[0]) == "4"
        assert _timer_throughput_text(timers[1]) == "12"

    def test_throughput_var_keyword_arg_removed(self):
        """The ``throughput_var`` keyword arg from earlier iterations is gone."""
        results = generate_query_thread_groups(
            [_make_qc(throughput=7.0)],
        )
        xml = _render_xml(results)
        assert "${read_throughput}" not in xml
        assert "${query_throughput}" not in xml

    def test_no_query_udv_variable_in_rendered_xml(self):
        results = generate_query_thread_groups([_make_qc(throughput=8.0)])
        xml = _render_xml(results)
        assert "${query_throughput}" not in xml
