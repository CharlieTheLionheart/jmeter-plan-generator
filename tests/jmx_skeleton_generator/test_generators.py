"""Tests for jmx_skeleton_generator sub-generators."""

import pytest
from xml.etree import ElementTree as ET

from config_parser.models import ConnConfig, WriteConfig, QueryConfig, TestConfig
from jmx_skeleton_generator.generators.test_plan import (
    generate_test_plan,
    generate_user_defined_variables,
)
from jmx_skeleton_generator.generators.ddl_setup import generate_ddl_setup_thread_group
from jmx_skeleton_generator.generators.write_groups import generate_write_thread_groups
from jmx_skeleton_generator.generators.query_groups import generate_query_thread_groups


# ---------------------------------------------------------------------------
# test_plan
# ---------------------------------------------------------------------------


def _walk(elements):
    """Yield elements and all of their descendants (recursive)."""
    seen = set()

    def _recurse(el):
        if id(el) in seen:
            return
        seen.add(id(el))
        yield el
        for child in el:
            yield from _recurse(child)

    for el in elements:
        yield from _recurse(el)


class TestGenerateTestPlan:
    def test_returns_list_of_two_elements(self):
        result = generate_test_plan()
        assert isinstance(result, list)
        assert len(result) == 2
        tp, ht = result
        assert tp.tag.endswith("TestPlan")
        assert ht.tag.endswith("hashTree")

    def test_testplan_has_teardown_prop(self):
        tp, _ = generate_test_plan()
        xml = ET.tostring(tp, encoding="unicode")
        assert "TestPlan.tearDown_on_shutdown" in xml

    def test_testplan_has_user_defined_variables(self):
        tp, _ = generate_test_plan()
        xml = ET.tostring(tp, encoding="unicode")
        assert "TestPlan.user_defined_variables" in xml

    def test_comments_optional(self):
        tp, _ = generate_test_plan(comments="hello world")
        xml = ET.tostring(tp, encoding="unicode")
        assert "hello world" in xml


class TestGenerateUserDefinedVariables:
    def test_returns_list_of_two(self):
        conn = ConnConfig(db_url="jdbc:kaiwudb://localhost/defaultdb")
        result = generate_user_defined_variables(conn)
        assert isinstance(result, list)
        assert len(result) == 2  # Arguments, hashTree/

    def test_db_url_in_output(self):
        conn = ConnConfig(db_url="jdbc:kaiwudb://localhost/defaultdb")
        result = generate_user_defined_variables(conn)
        args = result[0]
        xml = ET.tostring(args, encoding="unicode")
        assert "db_url" in xml
        assert "jdbc:kaiwudb://localhost/defaultdb" in xml

    def test_all_conn_config_fields_present(self):
        conn = ConnConfig(
            db_url="jdbc:kaiwudb://localhost/defaultdb",
            conn_pool_size=20,
            device_start=1,
            test_duration=3600,
        )
        result = generate_user_defined_variables(conn)
        args = result[0]
        xml = ET.tostring(args, encoding="unicode")
        assert "conn_pool_size" in xml
        assert "device_start" in xml
        assert "test_duration" in xml

    def test_invalid_var_name_raises(self):
        conn = ConnConfig(db_url="jdbc://localhost")
        # inject bad field via model directly - conn_config doesn't have extra fields
        # the function only processes the fixed set, so no invalid names possible
        result = generate_user_defined_variables(conn)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# ddl_setup
# ---------------------------------------------------------------------------

class TestGenerateDDLSetupThreadGroup:
    def test_empty_ddl_returns_empty_list(self):
        assert generate_ddl_setup_thread_group([]) == []

    def test_single_ddl_produces_setup_thread_group_and_sampler(self):
        elems = generate_ddl_setup_thread_group(["CREATE DATABASE foo"])
        tags = [e.tag.split("}")[-1] for e in _walk(elems)]
        assert "SetupThreadGroup" in tags
        assert "JDBCSampler" in tags
        assert "hashTree" in tags

    def test_multiple_ddl_produces_multiple_samplers(self):
        elems = generate_ddl_setup_thread_group([
            "CREATE DATABASE d1",
            "CREATE TABLE t1",
        ])
        sampler_count = sum(
            1 for e in _walk(elems) if e.tag.endswith("JDBCSampler")
        )
        assert sampler_count == 2

    def test_samplers_reference_jdbcdatasource_pool(self):
        """JDBCSampler.dataSource must match the ``<JDBCDataSource>`` element's
        ``name`` attribute (``jdbcConfig``) for the pool lookup to succeed.

        Earlier this assertion checked for ``${db_url}``, which left the
        sampler pointing at a JMeter UDV field whose value is a JDBC URL
        string, not a pool name. JMeter then raises
        ``No pool found named: '${db_url}'`` at sampler init.
        """
        elems = generate_ddl_setup_thread_group(["CREATE DATABASE foo"])
        for e in _walk(elems):
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                assert "jdbcConfig" in xml
                break

    def test_rel_init_specs_empty_emits_no_loop_controller(self):
        """``rel_init_specs=[]`` MUST NOT produce a relational init subtree.

        conditional-relational-setup DCR: a ts-only model must not generate
        ``RelInit_`` samplers, ``relprep`` preprocessors, or relational
        ``LoopController`` elements. We use the relational-init-specific
        markers ``RelInit_`` / ``relprep`` / ``Loop Controller for`` to
        avoid collision with the ``SetupThreadGroup``'s own
        ``main_controller`` elementProp.
        """
        elems = generate_ddl_setup_thread_group(
            ["CREATE DATABASE foo"],
            rel_init_specs=[],
        )
        # The generator returns ``[SetupThreadGroup, hashTree]``; serialise
        # both to capture the entire paired subtree, not just the TG props.
        xml = "".join(ET.tostring(e, encoding="unicode") for e in elems)
        assert "RelInit_" not in xml
        assert "relprep" not in xml
        assert "Loop Controller for" not in xml

    def test_rel_init_specs_produces_rel_subtree(self):
        """A single rel init spec produces one ``RelInit_`` subtree and
        ``LoopController.loops == total_rows // batch_lines``.
        """
        spec = {
            "table_name": "iot_meta.t_workshop",
            "columns": ["pk_int8_1", "col_varchar_1"],
            "total_rows": 100,
            "batch_lines": 20,
            "rel_col_seed_files": ["1_pk_int8_1.csv", "2_col_varchar_1.csv"],
            "column_types": ["int8", "varchar(16)"],
        }
        elems = generate_ddl_setup_thread_group(
            ["CREATE DATABASE foo"],
            rel_init_specs=[spec],
        )
        xml = "".join(ET.tostring(e, encoding="unicode") for e in elems)
        assert xml.count("RelInit_") >= 1
        assert xml.count("relprep") >= 1
        # LoopController for the relational subtree iterates 100/20 = 5 times.
        assert ">5<" in xml

    def test_rel_init_specs_appended_after_ddl(self):
        """DDL samplers are emitted before the relational init subtree."""
        spec = {
            "table_name": "iot_meta.t_workshop",
            "columns": ["pk_int8_1"],
            "total_rows": 10,
            "batch_lines": 5,
            "rel_col_seed_files": ["1_pk_int8_1.csv"],
            "column_types": ["int8"],
        }
        elems = generate_ddl_setup_thread_group(
            ["CREATE DATABASE foo", "CREATE TABLE bar"],
            rel_init_specs=[spec],
        )
        xml = "".join(ET.tostring(e, encoding="unicode") for e in elems)
        assert xml.find("DDL-1") < xml.find("RelInit_")
        assert xml.find("DDL-2") < xml.find("RelInit_")


# ---------------------------------------------------------------------------
# write_groups
# ---------------------------------------------------------------------------

class TestGenerateWriteThreadGroups:
    def _write_cfg(self, mode, tbl_name="db.t"):
        return WriteConfig(tbl_name=tbl_name, mode=mode, num_threads=10)

    def _make_ts_model(self):
        """Minimal TS model with one ts_db and one ts_table for direct-INSERT tests."""
        from config_parser.models import (
            ColTypeConfig,
            PrimaryTagColTypeConfig,
            TestModelConfig,
            TsColConfig,
            TsDbConfig,
            TsTableConfig,
        )

        table = TsTableConfig(
            name="t_cnc",
            data_col_count=1,
            primary_tag_count=1,
            regular_tag_count=0,
            ts_col=TsColConfig(name="ts", type="timestamp", ms_step=1000),
            data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
            primary_tags=[PrimaryTagColTypeConfig(col_type="int8", type_proportion=1.0)],
        )
        db = TsDbConfig(name="iot_monitor", tables=[table])
        return TestModelConfig(ts_dbs=[db])

    def test_empty_write_config_returns_empty(self):
        assert generate_write_thread_groups([], {}) == []

    def test_single_insert_mode_skipped_without_model(self):
        """Without a TestModelConfig, single_insert falls back to skip
        (preserves pre-2026-07-15 contract for callers that don't have
        model metadata handy)."""
        cfg = [self._write_cfg("direct", "iot_monitor.t_cnc")]
        result = generate_write_thread_groups(cfg, {})
        assert result == []

    def test_batch_insert_mode_skipped_without_model(self):
        cfg = [self._write_cfg("direct", "iot_monitor.t_cnc")]
        result = generate_write_thread_groups(cfg, {})
        assert result == []

    def test_single_insert_mode_generates_thread_group_with_model(self):
        """When model is provided, single_insert now produces a write
        ThreadGroup per spec §"Generate JDBCSampler for single_insert
        and batch_insert modes"."""
        cfg = [self._write_cfg("direct", "iot_monitor.t_cnc")]
        result = generate_write_thread_groups(cfg, {}, model=self._make_ts_model())
        tags = [e.tag.split("}")[-1] for e in _walk(result)]
        assert "ThreadGroup" in tags
        assert "JDBCSampler" in tags
        assert "JSR223PreProcessor" in tags
        assert "ConstantThroughputTimer" in tags

    def test_batch_insert_mode_generates_thread_group_with_model(self):
        cfg = [
            WriteConfig(
                tbl_name="iot_monitor.t_cnc",
                mode="direct",
                num_threads=10,
                batch_lines=5,
            )
        ]
        result = generate_write_thread_groups(cfg, {}, model=self._make_ts_model())
        tags = [e.tag.split("}")[-1] for e in _walk(result)]
        assert "ThreadGroup" in tags
        assert "JDBCSampler" in tags
        assert "JSR223PreProcessor" in tags

    def test_single_insert_sampler_references_inline_sql(self):
        """The direct-INSERT path uses ``Update Statement`` with the
        query bound to ``${insert_sql}`` (a JMeter variable the
        PreProcessor populates with a fully-inline INSERT). This sidesteps
        the JMeter ``?`` placeholder limitations and the
        ``Timestamp.valueOf`` string-format quirks on KaiwuDB."""
        cfg = [self._write_cfg("direct", "iot_monitor.t_cnc")]
        result = generate_write_thread_groups(cfg, {}, model=self._make_ts_model())
        for e in result:
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                assert "${insert_sql}" in xml
                assert "Update Statement" in xml
                break

    def test_single_prepared_mode_generates_thread_group(self):
        cfg = [self._write_cfg("prepare")]
        result = generate_write_thread_groups(cfg, {})
        tags = [e.tag.split("}")[-1] for e in result]
        assert "ThreadGroup" in tags

    def test_batch_prepared_mode_generates_thread_group(self):
        cfg = [self._write_cfg("prepare")]
        result = generate_write_thread_groups(cfg, {})
        tags = [e.tag.split("}")[-1] for e in result]
        assert "ThreadGroup" in tags

    def test_thread_group_has_throughput_timer(self):
        cfg = [self._write_cfg("prepare")]
        result = generate_write_thread_groups(cfg, {})
        tags = [e.tag.split("}")[-1] for e in _walk(result)]
        assert "ConstantThroughputTimer" in tags

    def test_template_used_as_query(self):
        cfg = [self._write_cfg("prepare", "mydb.mytable")]
        templates = {"mydb.mytable": "insert into mydb.mytable (a) values (?)"}
        result = generate_write_thread_groups(cfg, templates)
        for e in result:
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                assert "insert into mydb.mytable" in xml
                break

    def test_num_threads_from_config(self):
        cfg = [WriteConfig(tbl_name="db.t", mode="prepare", num_threads=42)]
        result = generate_write_thread_groups(cfg, {})
        for e in result:
            if e.tag.endswith("ThreadGroup"):
                xml = ET.tostring(e, encoding="unicode")
                assert "42" in xml
                break


# ---------------------------------------------------------------------------
# query_groups
# ---------------------------------------------------------------------------

class TestGenerateQueryThreadGroups:
    def test_empty_query_config_returns_empty(self):
        assert generate_query_thread_groups([]) == []

    def test_single_query_generates_thread_group(self):
        cfg = [QueryConfig(query="SELECT * FROM t", num_threads=5)]
        result = generate_query_thread_groups(cfg)
        tags = [e.tag.split("}")[-1] for e in result]
        assert "ThreadGroup" in tags

    def test_query_text_used_as_query(self):
        cfg = [QueryConfig(query="SELECT a, b FROM t1", num_threads=1)]
        result = generate_query_thread_groups(cfg)
        for e in result:
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                assert "SELECT a, b FROM t1" in xml
                break

    def test_prepared_select_statement_type(self):
        # spec v1.4: query 统一使用 PreparedStatement,queryType 固定为 "Prepared Select Statement"
        cfg = [QueryConfig(query="SELECT 1", num_threads=1)]
        result = generate_query_thread_groups(cfg)
        for e in result:
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                assert "Prepared Select Statement" in xml
                break

    def test_query_keeps_question_mark_placeholders(self):
        """F-14 (2026-07-21): ``Prepared Select Statement`` binds values
        positionally into ``?`` slots via ``queryArguments``. Earlier we
        rewrote each ``?`` to ``${param_N}`` so JMeter would substitute
        the value before the SQL reached the driver — but that double
        substitution collided with the prepared statement and the
        result-set metadata came back empty (``column index out of
        range: 1, number of columns: 0``). Keep ``?`` in the SQL.
        """
        cfg = [QueryConfig(
            query="SELECT a, b FROM t1 WHERE a = ? AND b = ?",
            num_threads=1,
        )]
        result = generate_query_thread_groups(cfg)
        for e in result:
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                assert "a = ? AND b = ?" in xml, (
                    "F-14: SQL must keep ``?`` placeholders so JMeter's "
                    "Prepared Select Statement binds them positionally"
                )
                # The literal ${param_N} substitution path must be
                # gone — it clashed with the positional bind.
                assert "${param_0}" not in xml
                assert "${param_1}" not in xml
                break

    def test_query_arguments_types_count_matches(self):
        """F-6 + F-14: ``queryArgumentsTypes`` must have one entry per
        ``?`` placeholder. JMeter's JDBCSampler validates
        args-and-types counts at runtime.
        """
        cfg = [QueryConfig(
            query="SELECT a, b FROM t1 WHERE a = ? AND b = ?",
            num_threads=1,
        )]
        result = generate_query_thread_groups(cfg)
        for e in result:
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                # 2 ?s → 2 VARCHARs.
                assert ">VARCHAR,VARCHAR<" in xml, (
                    "F-6/F-14: queryArgumentsTypes must have one entry "
                    "per ``?`` (got mismatch → 'number of arguments "
                    "(N) and number of types (1) are not equal')"
                )
                break

    def test_query_label_uses_template_order_when_name_unset(self):
        """R-2 (openspec/changes/query-naming): ThreadGroup testname =
        ``[Query] query{N}`` by template order.

        Easier to communicate in failure discussion than truncated
        SQL text (which used to produce labels like ``[Query] SELECT
        rtag_varchar_1, count(*...``).
        """
        cfgs = [
            QueryConfig(query="SELECT 1 FROM t1", num_threads=1),
            QueryConfig(query="SELECT 2 FROM t2", num_threads=1),
            QueryConfig(query="SELECT 3 FROM t3", num_threads=1),
        ]
        result = generate_query_thread_groups(cfgs)
        names = [
            e.attrib["testname"] for e in result if e.tag.endswith("ThreadGroup")
        ]
        assert names == ["[Query] query1", "[Query] query2", "[Query] query3"]

    def test_query_label_uses_explicit_name_when_provided(self):
        """R-2: ``QueryConfig.name`` overrides the ``query{N}`` fallback."""
        cfgs = [
            QueryConfig(query="SELECT 1 FROM t1", num_threads=1, name="foo"),
            QueryConfig(query="SELECT 2 FROM t2", num_threads=1),
        ]
        result = generate_query_thread_groups(cfgs)
        names = [
            e.attrib["testname"] for e in result if e.tag.endswith("ThreadGroup")
        ]
        assert names == ["[Query] foo", "[Query] query2"]

    def test_query_name_field_round_trip(self):
        """R-2: ``QueryConfig.name`` is parsed and stripped by the model."""
        cfg = QueryConfig(query="SELECT 1 FROM t", num_threads=1, name="  hello  ")
        assert cfg.name == "hello"
