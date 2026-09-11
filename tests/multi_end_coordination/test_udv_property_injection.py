"""Tests for the multi-end UDV ${__P(...)} injection (design decision).

Closes multi-end-coordination review §1 by exercising:

- ``device_start`` UDV field becomes the literal string
  ``"${__P(device_start,1)}"`` (NOT a numeric literal such as ``"1"``).
- ``device_per_thread`` follows the same pattern.
- ``write_throughput`` is NOT a UDV — throughput is baked into each
  write ``ConstantThroughputTimer`` as the per-table
  ``WriteConfig.throughput`` cfg literal (no UDV indirection).
- The generated JMX contains no orchestration-output sampler / listener
  (multi-end tasks §3.2 reverse-direction test).
"""

from __future__ import annotations

import pytest
from xml.etree import ElementTree as ET

from config_parser.models import ConnConfig
from jmx_skeleton_generator.generators.test_plan import generate_user_defined_variables
from jmx_skeleton_generator.generators.write_groups import generate_write_thread_groups
from config_parser.models import WriteConfig


def _udv_props(results) -> dict:
    """Extract ``Argument.name → Argument.value`` from the UDV ``Arguments`` root."""
    args_root = results[0]
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


class TestDeviceStartUdv:
    def test_device_start_is_property_reference(self):
        props = _udv_props(_udv_results())
        assert props["device_start"] == "${__P(device_start,1)}"

    def test_device_per_thread_is_property_reference(self):
        props = _udv_props(_udv_results())
        assert props["device_per_thread"] == "${__P(device_per_thread,1)}"


class TestWriteThroughputAbsent:
    """write_throughput UDV is gone (cfg-write-throughput-literal, 2026-09-11).

    Per-table throughput is baked into the ``ConstantThroughputTimer``
    at generation time. ``-Jwrite_throughput=N`` no longer affects
    sampler tick rate; the operator edits ``cfg.write_config[].throughput``
    and re-runs ``python -m kwjdbc_svt.main``.
    """

    def test_write_throughput_not_in_udv(self):
        props = _udv_props(_udv_results())
        assert "write_throughput" not in props


class TestAllUdvsAdoptPropertySyntax:
    """F-15: every UDV default goes through ${__P(name,default)}."""

    @pytest.mark.parametrize(
        "udv_name",
        [
            # F-15: ALL UDVs (operational + credentials) exposed via
            # ``${__P(name,default)}`` so CI can re-point the smoke at
            # a different cluster / credentials via ``-J<name>=...``.
            "db_url", "db_username", "db_password",
            "conn_pool_size", "device_start", "device_per_thread",
            "test_duration",
        ],
    )
    def test_udv_uses_property_reference(self, udv_name: str):
        props = _udv_props(_udv_results())
        assert f"${{__P({udv_name}," in props[udv_name], (
            f"F-15: UDV '{udv_name}' must default through "
            f"${{__P(...)}} so -J{udv_name}=... CLI overrides work"
        )

    def test_credential_udv_uses_empty_default_when_yaml_empty(self):
        """``db_password`` with empty YAML default must be
        ``${__P(db_password,)}`` (empty default between commas), NOT
        ``${__P(db_password)}`` (no comma at all → default = ``"1"``).

        JMeter's ``__P`` function defaults to the literal ``"1"`` when
        no second arg is supplied; that would replace ``db_password``
        with ``"1"`` and trip cluster auth.
        """
        props = _udv_props(_udv_results())
        assert props["db_password"] == "${__P(db_password,)}", (
            "F-15: db_password default must be ${__P(db_password,)} "
            "(empty between commas), not ${__P(db_password)} ('1' default)"
        )

    def test_credential_udv_defaults_have_no_quote_wrapping(self):
        """String defaults are raw literals — NO single-quote wrapping.

        Earlier we wrapped defaults in ``'...'`` per Python ``!r``, which
        the JMeter ``__P`` function passed through verbatim as the
        literal three-or-more-char string with apostrophes (the JDBC
        driver then saw e.g. URL ``'jdbc:.../defaultdb'`` and rejected
        it). The reference at ``scenarios/shig/plans/plan.jmx`` uses
        the same raw form: ``${__P(user.db.url,jdbc:.../defaultdb)}``.
        """
        for name in ("db_url", "db_username", "db_password"):
            props = _udv_props(_udv_results())
            value = props[name]
            # No surrounding ' characters around the literal default.
            assert "'" not in value.split("(", 1)[1].rsplit(")", 1)[0], (
                f"{name} default has stray quote: {value!r}"
            )


class TestNoOrchestrationOutput:
    """Generated JMX must NOT contain a sampler / listener whose purpose is
    to communicate device_start to the orchestration layer — that
    responsibility lies with the caller pipeline (review §0).

    Reverse-direction assertion: a freshly-rendered write thread group
    JMX contains no element whose name suggests multi-end orchestration
    output (no BeanShellSampler labelled ``next_instance`` etc.).
    """

    def _scratch_jmx_xml(self) -> str:
        wc = WriteConfig(tbl_name="db.t", mode="prepare", num_threads=1)
        results = generate_write_thread_groups([wc], {})
        return "".join(ET.tostring(e, encoding="unicode") for e in results)

    def test_jmx_has_no_next_instance_sampler(self):
        xml = self._scratch_jmx_xml()
        assert "next_instance" not in xml
        assert "next_device_start" not in xml

    def test_jmx_has_no_beanshell_sampler(self):
        """JMX rendered via write_groups must contain only the documented
        sampler types: JDBCSampler + JSR223Sampler + JSR223PreProcessor."""
        xml = self._scratch_jmx_xml()
        assert "BeanShellSampler" not in xml

    def test_jmx_has_no_sample_log_orchestration(self):
        xml = self._scratch_jmx_xml()
        assert "SampleLog" not in xml or "device_start" not in xml
