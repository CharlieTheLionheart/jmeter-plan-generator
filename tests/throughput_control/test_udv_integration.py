"""End-to-end UDV integration tests.

Verifies that :func:`generate_user_defined_variables` does NOT expose a
``write_throughput`` (or ``query_throughput``) UDV — write-thread
throughput is now baked into each ``ConstantThroughputTimer`` as a
literal from the per-table ``WriteConfig.throughput`` cfg field, and
query-thread throughput is baked into each query timer's literal. No
JMeter UDV is involved for either side.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from config_parser.models import ConnConfig
from jmx_skeleton_generator.generators.test_plan import generate_user_defined_variables


def _udv_props(results) -> dict:
    """Extract ``Argument.name → Argument.value`` mapping from a UDV results list."""
    args_root = results[0]  # <Arguments>; results[1] is the trailing hashTree
    props = {}
    for el in args_root.iter():
        if el.tag.endswith("elementProp") and el.attrib.get("name"):
            name = el.find(".//*[@name='Argument.name']")
            value = el.find(".//*[@name='Argument.value']")
            if name is not None and value is not None and name.text:
                props[name.text] = value.text
    return props


def _udv_results():
    return generate_user_defined_variables(ConnConfig(db_url="jdbc://x"))


def _render_xml(results) -> str:
    return "".join(ET.tostring(e, encoding="unicode") for e in results)


class TestUdvWriteThroughput:
    def test_no_write_throughput_in_udv(self):
        """``write_throughput`` UDV is removed; throughput is per-table literal."""
        props = _udv_props(_udv_results())
        assert "write_throughput" not in props

    def test_no_query_throughput_in_udv(self):
        """``query_throughput`` was never exposed (per-query literal from cfg)."""
        props = _udv_props(_udv_results())
        assert "query_throughput" not in props

    def test_write_throughput_udv_text_not_in_rendered_xml(self):
        """Defense-in-depth: scan the rendered XML for the deprecated UDV name."""
        xml = _render_xml(_udv_results())
        assert "write_throughput" not in xml