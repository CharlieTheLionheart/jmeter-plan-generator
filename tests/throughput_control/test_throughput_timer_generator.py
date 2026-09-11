"""Tests for the throughput_control module.

Closes review.md §3 "Test Coverage" by exercising:

- write timer → bakes cfg ``WriteConfig.throughput`` literal (no UDV)
- query timer → bakes ``QueryConfig.throughput`` literal
- design decision: config-parser-level ``throughput > 0`` validation
- absence of the ``${write_throughput}`` UDV surface

Each test is short and self-contained.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
from pydantic import ValidationError

from config_parser.models import PrimaryTagColTypeConfig, QueryConfig, TsDbConfig, TsTableConfig, WriteConfig
from throughput_control import generate_query_timer, generate_write_timer


def _props_for(element: ET.Element) -> dict:
    """Extract the ``<stringProp name="X">VAL</stringProp>`` map from an element."""
    return {
        p.attrib["name"]: p.text
        for p in element.iter()
        if p.tag.endswith("stringProp")
    }


class TestWriteTimer:
    def test_root_tag_is_constant_throughput_timer(self):
        timer, _ = generate_write_timer(throughput=120.0)
        assert timer.tag.endswith("ConstantThroughputTimer")

    def test_throughput_is_literal_value(self):
        timer, _ = generate_write_timer(throughput=120.0)
        props = _props_for(timer)
        assert props["throughput"] == "120"

    def test_throughput_int_valued_float_renders_without_decimal(self):
        """``4.0`` → ``"4"`` (matches query timer convention)."""
        timer, _ = generate_write_timer(throughput=4.0)
        assert _props_for(timer)["throughput"] == "4"

    def test_throughput_small_floating_point_is_preserved(self):
        """``0.016666667`` is exact, not truncated."""
        timer, _ = generate_write_timer(throughput=0.016666667)
        assert _props_for(timer)["throughput"] == "0.016666667"

    def test_distinct_throughputs_emit_distinct_literals(self):
        a, _ = generate_write_timer(throughput=4.0)
        b, _ = generate_write_timer(throughput=12.0)
        assert _props_for(a)["throughput"] == "4"
        assert _props_for(b)["throughput"] == "12"

    def test_calcmode_is_zero(self):
        timer, _ = generate_write_timer(throughput=60.0)
        calc_mode = next(
            int(p.text)
            for p in timer.iter()
            if p.tag.endswith("intProp") and p.attrib.get("name") == "calcMode"
        )
        assert calc_mode == 0

    def test_write_timer_does_not_emit_udv_reference(self):
        """The write timer body never references ``${write_throughput}``.

        cfg ``WriteConfig.throughput`` is baked at generation time; the
        JMeter ``-Jwrite_throughput=N`` CLI override has no effect.
        """
        timer, _ = generate_write_timer(throughput=60.0)
        xml = ET.tostring(timer, encoding="unicode")
        assert "${write_throughput}" not in xml


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


class TestConfigParserValidation:
    def test_write_throughput_field_zero_rejected(self):
        with pytest.raises(ValidationError):
            WriteConfig(tbl_name="db.t", throughput=0, mode="direct")

    def test_write_throughput_field_negative_rejected(self):
        with pytest.raises(ValidationError):
            WriteConfig(tbl_name="db.t", throughput=-1, mode="direct")

    def test_write_throughput_field_positive_accepted(self):
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


class TestCrossCallConsistency:
    """cfg-write-throughput-literal (2026-09-11): both code paths that
    render a write-thread ``ConstantThroughputTimer`` must bake the
    same literal from the same ``WriteConfig.throughput`` value.

    The two paths are:

    - :func:`jmx_skeleton_generator.generators.write_groups.generate_write_thread_groups`
      (JDBC ``batch_prepared`` / ``direct`` paths)
    - :func:`jmx_skeleton_generator.generators.rest_write_groups.generate_rest_write_thread_group`
      (REST ``schemaless`` path)
    """

    def _extract_throughput_attr(self, elements) -> str:
        """Find the first ``ConstantThroughputTimer`` and return its
        ``throughput`` string-prop value.
        """
        from xml.etree import ElementTree as ET

        NS = "{http://jmeter.apache.org/}"
        for el in ET.fromstring("<root>" + "".join(
            ET.tostring(e, encoding="unicode") for e in elements
        ) + "</root>").iter():
            if el.tag.endswith("ConstantThroughputTimer"):
                for child in el:
                    if child.tag.endswith("stringProp") and child.get("name") == "throughput":
                        return child.text or ""
        raise AssertionError("no ConstantThroughputTimer found")

    def test_both_paths_emit_same_literal_for_same_cfg(self):
        """Same ``WriteConfig.throughput`` → same ConstantThroughputTimer literal."""
        from jmx_skeleton_generator.generators.rest_write_groups import (
            generate_rest_write_thread_group,
        )
        from jmx_skeleton_generator.generators.write_groups import (
            generate_write_thread_groups,
        )

        wc = WriteConfig(tbl_name="db_x.t", throughput=42.0, mode="direct")
        rest_cfg = {
            "write_url_path": "/restapi/influxdb",
            "default_db": "db_x",
            "https_mode": "tls",
            "ca_cert_path": "/etc/cert",
            "timezone": None,
        }
        ts_table = TsTableConfig(
            name="t",
            data_col_count=0,
            data_cols=[],
            primary_tag_count=1,
            primary_tags=[PrimaryTagColTypeConfig(col_type="varchar(64)", type_proportion=1.0)],
            regular_tag_count=0,
            regular_tags=[],
        )
        model = type("M", (), {
            "ts_dbs": [TsDbConfig(name="db_x", tables=[ts_table])],
        })()

        # JDBC write_groups path
        jdbc_elems = generate_write_thread_groups([wc], {}, model=model)

        # REST write_groups path
        rest_elems = generate_rest_write_thread_group(
            model,
            rest_api_config=rest_cfg,
            write_configs=[wc],
        )

        jdbc_val = self._extract_throughput_attr(jdbc_elems)
        rest_val = self._extract_throughput_attr(rest_elems)
        assert jdbc_val == "42", f"JDBC literal: {jdbc_val!r}"
        assert rest_val == "42", f"REST literal: {rest_val!r}"
        assert jdbc_val == rest_val