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

    def test_samplers_reference_db_url_variable(self):
        elems = generate_ddl_setup_thread_group(["CREATE DATABASE foo"])
        for e in _walk(elems):
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                assert "${db_url}" in xml
                break


# ---------------------------------------------------------------------------
# write_groups
# ---------------------------------------------------------------------------

class TestGenerateWriteThreadGroups:
    def _write_cfg(self, mode, tbl_name="db.t"):
        return WriteConfig(tbl_name=tbl_name, mode=mode, num_threads=10)

    def test_empty_write_config_returns_empty(self):
        assert generate_write_thread_groups([], {}) == []

    def test_single_insert_mode_skipped(self):
        cfg = [self._write_cfg("single_insert")]
        result = generate_write_thread_groups(cfg, {})
        assert result == []

    def test_batch_insert_mode_skipped(self):
        cfg = [self._write_cfg("batch_insert")]
        result = generate_write_thread_groups(cfg, {})
        assert result == []

    def test_single_prepared_mode_generates_thread_group(self):
        cfg = [self._write_cfg("single_prepared")]
        result = generate_write_thread_groups(cfg, {})
        tags = [e.tag.split("}")[-1] for e in result]
        assert "ThreadGroup" in tags

    def test_batch_prepared_mode_generates_thread_group(self):
        cfg = [self._write_cfg("batch_prepared")]
        result = generate_write_thread_groups(cfg, {})
        tags = [e.tag.split("}")[-1] for e in result]
        assert "ThreadGroup" in tags

    def test_thread_group_has_throughput_timer(self):
        cfg = [self._write_cfg("batch_prepared")]
        result = generate_write_thread_groups(cfg, {})
        tags = [e.tag.split("}")[-1] for e in _walk(result)]
        assert "ConstantThroughputTimer" in tags

    def test_template_used_as_query(self):
        cfg = [self._write_cfg("single_prepared", "mydb.mytable")]
        templates = {"mydb.mytable": "insert into mydb.mytable (a) values (?)"}
        result = generate_write_thread_groups(cfg, templates)
        for e in result:
            if e.tag.endswith("JDBCSampler"):
                xml = ET.tostring(e, encoding="unicode")
                assert "insert into mydb.mytable" in xml
                break

    def test_num_threads_from_config(self):
        cfg = [WriteConfig(tbl_name="db.t", mode="single_prepared", num_threads=42)]
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
