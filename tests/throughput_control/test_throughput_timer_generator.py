"""Tests for the throughput_control module.

Closes review.md §3 "Test Coverage" by exercising:

- design decision 18 (write → UDV, query → literal)
- design decision: config-parser-level `throughput > 0` validation
- absence of the `${query_throughput}` UDV surface

Each test is short and self-contained; for end-to-end UDV injection
plus ``write_throughput=120`` default see
:mod:`tests.throughput_control.test_udv_integration`.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
from pydantic import ValidationError

from config_parser.models import QueryConfig, WriteConfig
from throughput_control import (
    DEFAULT_WRITE_THROUGHPUT,
    generate_query_timer,
    generate_write_timer,
)


def _props_for(element: ET.Element) -> dict:
    """Extract the ``<stringProp name="X">VAL</stringProp>`` map from an element."""
    return {
        p.attrib["name"]: p.text
        for p in element.iter()
        if p.tag.endswith("stringProp")
    }


class TestWriteTimer:
    def test_root_tag_is_constant_throughput_timer(self):
        timer, _ = generate_write_timer()
        assert timer.tag.endswith("ConstantThroughputTimer")

    def test_throughput_is_write_udv_variable(self):
        timer, _ = generate_write_timer()
        props = _props_for(timer)
        assert props["throughput"] == "${write_throughput}"

    def test_calcmode_is_zero(self):
        timer, _ = generate_write_timer()
        calc_mode = next(
            int(p.text)
            for p in timer.iter()
            if p.tag.endswith("intProp") and p.attrib.get("name") == "calcMode"
        )
        assert calc_mode == 0


class TestQueryTimer:
    def test_throughput_is_literal(self):
        timer, _ = generate_query_timer(4.0)
        props = _props_for(timer)
        assert props["throughput"] == "4"

    def test_distinct_throughputs_emit_distinct_literals(self):
        a, _ = generate_query_timer(4.0)
        b, _ = generate_query_timer(12.0)
        assert _props_for(a)["throughput"] == "4"
        assert _props_for(b)["throughput"] == "12"

    def test_small_floating_point_is_preserved(self):
        """Tasks §7.5: 0.016666667 (1 per minute) is exact, not truncated."""
        timer, _ = generate_query_timer(0.016666667)
        assert _props_for(timer)["throughput"] == "0.016666667"

    def test_calcmode_is_zero(self):
        timer, _ = generate_query_timer(60.0)
        calc_mode = next(
            int(p.text)
            for p in timer.iter()
            if p.tag.endswith("intProp") and p.attrib.get("name") == "calcMode"
        )
        assert calc_mode == 0

    def test_no_query_udv_variable_emitted(self):
        """The query timer body never references ``${query_throughput}``."""
        timer, _ = generate_query_timer(7.5)
        xml = ET.tostring(timer, encoding="unicode")
        assert "${query_throughput}" not in xml


class TestDefaultValue:
    def test_default_write_throughput_constant(self):
        assert DEFAULT_WRITE_THROUGHPUT == 120.0


class TestConfigParserValidation:
    def test_write_throughput_zero_rejected(self):
        with pytest.raises(ValidationError):
            WriteConfig(tbl_name="db.t", throughput=0, mode="direct")

    def test_write_throughput_negative_rejected(self):
        with pytest.raises(ValidationError):
            WriteConfig(tbl_name="db.t", throughput=-1, mode="direct")

    def test_write_throughput_positive_accepted(self):
        cfg = WriteConfig(tbl_name="db.t", throughput=120, mode="direct")
        assert cfg.throughput == 120

    def test_query_throughput_zero_rejected(self):
        with pytest.raises(ValidationError):
            QueryConfig(query="SELECT 1", throughput=0)

    def test_query_throughput_negative_rejected(self):
        with pytest.raises(ValidationError):
            QueryConfig(query="SELECT 1", throughput=-3.5)

    def test_query_throughput_positive_accepted(self):
        cfg = QueryConfig(query="SELECT 1", throughput=4)
        assert cfg.throughput == 4
