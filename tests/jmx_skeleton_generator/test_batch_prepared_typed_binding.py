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
    _build_batch_prepared_sampler_body,
)


@pytest.fixture
def sampler_script() -> str:
    """A representative batch_prepared sampler body for structure tests.

    The sampler script is now per-Table-generated (F-3 UDV-pollution
    fix): ``table_name``, ``insert_sql`` and ``column_types`` are
    baked in by the generator. We pick a representative set of
    column types so the structural assertions below stay meaningful.
    """
    return _build_batch_prepared_sampler_body(
        table_name="iot_monitor.t_cnc",
        insert_sql=(
            "insert into iot_monitor.t_cnc (ts, col_int8_1, col_float4_1, "
            "ptag_varchar_1, rtag_varchar_1) values (?, ?, ?, ?, ?)"
        ),
        column_types=["timestamp", "int8", "float4", "varchar(32)", "varchar(32)"],
    )


class TestBatchPreparedSamplerScriptStructure:
    """Pin the structure of the batch_prepared sampler for the typed-binding fix."""

    def test_carries_baked_column_types(self, sampler_script: str):
        """Sampler must carry the comma-separated ``column_types`` baked in.

        F-3 (2026-07-20): reading ``column_types`` from a per-thread UDV
        was unsafe because the UDV scope is the test plan, not the
        thread group. The generator now bakes the types into the script.
        """
        assert "float4" in sampler_script, (
            "sampler must carry column_types baked in (F-3 UDV-pollution fix)"
        )

    def test_dispatches_on_type_list(self, sampler_script: str):
        """Sampler must split the type list to index by column index."""
        assert ".split(',')" in sampler_script, (
            "sampler must split the column_types list"
        )

    def test_uses_typed_setter_for_numeric(self, sampler_script: str):
        """Integer / bigint columns must call ``setLong`` (not ``setObject``)."""
        assert "setLong" in sampler_script, (
            "sampler must call setLong for integer-typed columns — "
            "setObject(String) does not let the driver infer INT8"
        )

    def test_uses_typed_setter_for_floating(self, sampler_script: str):
        """float / float4 / float8 must call ``setDouble``."""
        assert "setDouble" in sampler_script, (
            "sampler must call setDouble for float-typed columns"
        )

    def test_uses_typed_setter_for_timestamp(self, sampler_script: str):
        """timestamp / timestamptz columns must call ``setTimestamp``."""
        assert "setTimestamp" in sampler_script, (
            "sampler must call setTimestamp for time-typed columns"
        )

    def test_falls_back_to_set_string(self, sampler_script: str):
        """VARCHAR / unknown types fall back to ``setString``."""
        assert "setString" in sampler_script, (
            "sampler must fall back to setString for non-numeric, "
            "non-timestamp columns (varchar, etc.)"
        )

    def test_null_uses_set_object(self, sampler_script: str):
        """Nullable cells must bind SQL NULL through ``setObject``."""
        assert "setObject(colIdx + 1, null)" in sampler_script, (
            "sampler must bind nullable cells with setObject(index, null)"
        )

    def test_does_not_call_set_object_for_non_null_values(self, sampler_script: str):
        """Non-null typed columns must not use generic ``setObject(value)``."""
        assert "setObject(colIdx + 1, value)" not in sampler_script, (
            "sampler must not use setObject(value) — that was the source of "
            "the 'could not resolve \"20\" as INT8 type' failures"
        )

    def test_large_insert_sql_is_split_into_safe_literals(self):
        """Groovy 单个字符串常量不得超过 class-file 65535 字节限制。"""
        columns = ", ".join(f"col_varchar_2000_{i}" for i in range(1, 4001))
        placeholders = ", ".join("?" for _ in range(4000))
        insert_sql = f"insert into db_sparse.t_cnc ({columns}) values ({placeholders})"

        script = _build_batch_prepared_sampler_body(
            table_name="db_sparse.t_cnc",
            insert_sql=insert_sql,
            column_types=["varchar(2000)"] * 4000,
        )

        assert "def insertSql = [" in script
        assert "].join('')" in script
        assert max(len(line) for line in script.splitlines()) < 60_000

    def test_bakes_table_name_literal(self, sampler_script: str):
        """tableName is baked into the script as a string literal (F-3 UDV fix).

        Earlier we tried ``ctx.getThreadGroup().getName()`` but that
        returns the testname (e.g. ``[Write] db_shig.t_cnc``) instead of
        the ThreadGroup's ``name`` attribute, so the substring-strip
        approach left a leading ``] ``. Baking the value at JMX
        generation time is simpler and matches the per-Table
        script-template pattern.
        """
        assert "iot_monitor.t_cnc" in sampler_script, (
            "sampler must carry the tableName baked in as a literal"
        )

    def test_bakes_insert_sql_literal(self, sampler_script: str):
        """F-3: insert_sql must be baked in, not read from a per-UDV.

        The pre-fix code did ``vars.get("insert_sql")`` which leaked
        across Write ThreadGroups: the second ThreadGroup's thread
        saw the first ThreadGroup's INSERT statement. Baking the
        literal in at JMX generation time removes the dependency.
        """
        assert "insert into iot_monitor.t_cnc" in sampler_script, (
            "sampler must carry insert_sql baked in as a literal (F-3)"
        )

    def test_no_vars_get_lookup_for_table_name(self, sampler_script: str):
        """F-3: ``vars.get("table_name")`` is forbidden — it returned
        the wrong ThreadGroup's value (UDV pollution).
        """
        assert 'vars.get("table_name")' not in sampler_script, (
            "sampler must not read table_name from vars — it leaks "
            "across Write ThreadGroups (F-3)"
        )

    def test_no_vars_get_lookup_for_insert_sql(self, sampler_script: str):
        """F-3: same constraint for insert_sql."""
        assert 'vars.get("insert_sql")' not in sampler_script, (
            "sampler must not read insert_sql from vars (F-3)"
        )

    def test_no_vars_get_lookup_for_column_types(self, sampler_script: str):
        """F-3: same constraint for column_types."""
        assert 'vars.get("column_types")' not in sampler_script, (
            "sampler must not read column_types from vars (F-3)"
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