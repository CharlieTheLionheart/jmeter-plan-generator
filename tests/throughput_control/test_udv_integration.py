"""End-to-end UDV integration tests (design decision: write UDV default 120).

Verifies that :func:`generate_user_defined_variables` injects the
``write_throughput`` UDV field with its default value ``120`` and
that ``query_throughput`` is NOT exposed in the UDV surface.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from config_parser.models import ConnConfig
from jmx_skeleton_generator.generators.test_plan import generate_user_defined_variables
from throughput_control import DEFAULT_WRITE_THROUGHPUT


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
    def test_default_injected_at_120(self):
        """F-15: write_throughput default is baked into ${__P(...,120)}."""
        props = _udv_props(_udv_results())
        assert props["write_throughput"] == f"${{__P(write_throughput,{int(DEFAULT_WRITE_THROUGHPUT)})}}"

    def test_module_default_constant_is_120(self):
        assert DEFAULT_WRITE_THROUGHPUT == 120.0

    def test_query_throughput_udv_not_exposed(self):
        props = _udv_props(_udv_results())
        assert "query_throughput" not in props

    def test_write_throughput_value_renders_as_property_reference(self):
        """F-15: write_throughput is a ``${__P(name,default)}`` reference.

        Previously this was a literal ``'120'`` and ``-Jwrite_throughput=N``
        was silently ignored. Now ``-Jwrite_throughput=240`` overrides
        the YAML default at JMeter CLI time.
        """
        props = _udv_props(_udv_results())
        assert "${__P(write_throughput,120)}" in props["write_throughput"]
        # No literal 120 / 120.0 / 120.5 — must be wrapped.
        assert props["write_throughput"].count("120") == 1
