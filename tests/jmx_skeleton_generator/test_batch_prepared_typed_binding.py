"""Tests for F-1 sampler-side fix: batch_prepared uses typed setXxx binding.

Background: with CSV quotes stripped, cells become bare strings like
``"20"`` or ``"55.91"``. The old sampler did
``pstmt.setObject(colIdx + 1, value)`` for every non-null cell — the
KaiwuDB JDBC driver cannot infer ``INT8`` / ``FLOAT4`` from a String,
so the INSERT aborts with ``could not resolve "20" as INT8 type``.

The fix routes per-column JDBC types from the resolved model through
``vars.get("column_types")`` (a comma-separated list aligned with the
SQL INSERT column order) into the sampler's ``setXxx`` dispatch:

- numeric base types (``int*`` / ``tinyint`` / ``smallint`` /
  ``bigint``) → ``setLong``
- floating-point types (``float`` / ``float4`` / ``float8`` /
  ``double`` / ``real`` / ``numeric`` / ``decimal``) → ``setDouble``
- ``timestamp`` / ``timestamptz`` → ``setTimestamp``
- boolean → ``setBoolean``
- everything else → ``setString``

The batch_prepared path is the one with the failure in the smoke run;
the inline-SQL ``single_insert`` / ``batch_insert`` paths already
quote-format values themselves, so they are out of scope here.
"""

from __future__ import annotations

import re

import pytest

from jmx_skeleton_generator.generators import write_groups
from jmx_skeleton_generator.generators.write_groups import (
    BATCH_PREPARED_SAMPLER_SCRIPT,
)


class TestBatchPreparedSamplerScriptStructure:
    """Pin the structure of ``BATCH_PREPARED_SAMPLER_SCRIPT`` for the typed-binding fix."""

    def test_uses_column_types_udv(self):
        """Sampler must read the comma-separated ``column_types`` UDV."""
        assert "vars.get(\"column_types\")" in BATCH_PREPARED_SAMPLER_SCRIPT, (
            "sampler must consume column_types UDV — without it we "
            "can't dispatch to setInt/setDouble/setString"
        )

    def test_dispatches_on_type_list(self):
        """Sampler must split the UDV into a list to index by column index."""
        # We need to index by ``colIdx``, so the UDV must be split into
        # an array. Accept either ``.split(',')`` or equivalent.
        assert ".split(',')" in BATCH_PREPARED_SAMPLER_SCRIPT, (
            "sampler must split the column_types UDV into a list"
        )

    def test_uses_typed_setter_for_numeric(self):
        """Integer / bigint columns must call ``setLong`` (not ``setObject``)."""
        # The numeric branch should map to ``setLong`` so KaiwuDB
        # receives a ``long`` and doesn't have to infer the type.
        assert "setLong" in BATCH_PREPARED_SAMPLER_SCRIPT, (
            "sampler must call setLong for integer-typed columns — "
            "setObject(String) does not let the driver infer INT8"
        )

    def test_uses_typed_setter_for_floating(self):
        """float / float4 / float8 must call ``setDouble``."""
        assert "setDouble" in BATCH_PREPARED_SAMPLER_SCRIPT, (
            "sampler must call setDouble for float-typed columns"
        )

    def test_uses_typed_setter_for_timestamp(self):
        """timestamp / timestamptz columns must call ``setTimestamp``."""
        assert "setTimestamp" in BATCH_PREPARED_SAMPLER_SCRIPT, (
            "sampler must call setTimestamp for time-typed columns"
        )

    def test_falls_back_to_set_string(self):
        """VARCHAR / unknown types fall back to ``setString``."""
        assert "setString" in BATCH_PREPARED_SAMPLER_SCRIPT, (
            "sampler must fall back to setString for non-numeric, "
            "non-timestamp columns (varchar, etc.)"
        )

    def test_does_not_call_set_object(self):
        """The sampler must NOT use ``setObject`` for typed columns.

        ``setObject(String)`` is the original bug — KaiwuDB can't
        resolve INT8/FLOAT4 from a string. The new dispatch must use
        explicit ``setXxx`` per JDBC type.
        """
        assert "setObject" not in BATCH_PREPARED_SAMPLER_SCRIPT, (
            "sampler must not use setObject — that was the source of "
            "the 'could not resolve \"20\" as INT8 type' failures"
        )


class TestBatchPreparedWriteUdvPlumbsColumnTypes:
    """The per-thread ``<Arguments>`` UDV must carry ``column_types`` for batch_prepared."""

    def test_write_udv_accepts_column_types_field(self):
        """``_build_write_udv`` must accept and emit ``column_types``."""
        import inspect
        sig = inspect.signature(write_groups._build_write_udv)
        assert "column_types" in sig.parameters, (
            "_build_write_udv must accept column_types so the sampler "
            "can dispatch to typed setXxx"
        )

    def test_write_udv_emits_column_types_in_jmx(self):
        """A JSR223-style UDV must surface ``column_types`` as a JMeter UDV element.

        Without this, the sampler has no way to discover the type
        list at runtime — vars.get(\"column_types\") returns null and
        the typed-binding dispatch falls back to ``setString``.
        """
        from jmx_skeleton_generator.generators.write_groups import (
            _build_write_udv,
        )
        from config_parser.models import WriteConfig

        wc = WriteConfig(
            tbl_name="iot_monitor.t_cnc",
            throughput=60.0,
            mode="batch_prepared",
            batch_lines=5,
            device_per_thread=2,
            num_threads=4,
        )
        column_types = ["timestamp", "int8", "float4", "varchar(32)", "varchar(32)"]
        element, _ = _build_write_udv(
            wc,
            insert_sql="insert into iot_monitor.t_cnc (ts, col_int8_1, col_float4_1, ptag_varchar_1, rtag_varchar_1) values (?, ?, ?, ?, ?)",
            ms_step=1000,
            first_ptag="ptag_varchar_1",
            column_types=column_types,
        )
        # The element should contain a stringProp with the joined type list.
        from xml.etree import ElementTree as ET
        serialized = ET.tostring(element, encoding="unicode")
        # JMeter Argument.value stringProp carries the UDV value.
        assert "int8" in serialized and "float4" in serialized, (
            f"UDV must surface column_types for the sampler to dispatch; got:\n{serialized}"
        )


class TestBatchPreparedThreadGroupResolvesColumnTypes:
    """End-to-end: ``generate_write_thread_groups`` resolves column types from model."""

    def test_batch_prepared_thread_group_carries_column_types(self):
        """When a model is supplied, batch_prepared branch should resolve column types."""
        from config_parser.models import (
            ColTypeConfig,
            PrimaryTagColTypeConfig,
            TestModelConfig,
            TsDbConfig,
            TsTableConfig,
            TsColConfig,
            WriteConfig,
        )
        from jmx_skeleton_generator.generators.write_groups import (
            generate_write_thread_groups,
        )

        # Mirror the smoke fixture: 1 varchar ptag, 1 enum rtag, 2 data cols
        # (int8 + float4). Counts must match the actual list lengths per
        # TsTableConfig R-PAR-004 validator.
        ts_col = TsColConfig(name="ts", type="timestamp", ms_step=1000)
        ts_table = TsTableConfig(
            name="t_cnc",
            ts_col=ts_col,
            primary_tag_count=1,
            regular_tag_count=1,
            data_col_count=2,
            primary_tags=[
                PrimaryTagColTypeConfig(col_type="varchar(32)", type_proportion=1.0),
            ],
            regular_tags=[
                ColTypeConfig(col_type="varchar(32)", type_proportion=1.0),
            ],
            data_cols=[
                ColTypeConfig(col_type="int8", type_proportion=0.5),
                ColTypeConfig(col_type="float4", type_proportion=0.5),
            ],
        )
        ts_db = TsDbConfig(name="iot_monitor", tables=[ts_table])
        model = TestModelConfig(ts_dbs=[ts_db])
        wc = WriteConfig(
            tbl_name="iot_monitor.t_cnc",
            throughput=60.0,
            mode="batch_prepared",
            batch_lines=5,
            device_per_thread=2,
            num_threads=4,
        )

        elements = generate_write_thread_groups(
            [wc],
            prepared_templates={"iot_monitor.t_cnc": "-- placeholder --"},
            model=model,
        )
        # Serialize and confirm column_types UDV is emitted.
        from xml.etree import ElementTree as ET
        serialized = "".join(ET.tostring(e, encoding="unicode") for e in elements)
        assert "column_types" in serialized, (
            "column_types UDV must be emitted in the batch_prepared "
            "ThreadGroup — otherwise the sampler cannot dispatch"
        )
        # And the typed-binding dispatch tokens must appear in the sampler script.
        assert "setLong" in serialized and "setDouble" in serialized, (
            "sampler script must contain typed binding dispatch "
            "(setLong + setDouble) for INT8/FLOAT4 columns"
        )