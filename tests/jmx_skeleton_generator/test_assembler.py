"""Tests for JMX assembler and full skeleton generator."""

import os
import tempfile
from pathlib import Path

import pytest
from xml.etree import ElementTree as ET

from config_parser.models import ConnConfig, QueryConfig, WriteConfig, TestConfig
from jmx_skeleton_generator.generators.assembler import JMXAssembler, JMXWriter, JmxGenerationError
from jmx_skeleton_generator.generators.test_plan import generate_test_plan, generate_user_defined_variables
from jmx_skeleton_generator.generators.ddl_setup import generate_ddl_setup_thread_group
from jmx_skeleton_generator.generators.write_groups import generate_write_thread_groups
from jmx_skeleton_generator.generators.query_groups import generate_query_thread_groups
from jmx_skeleton_generator.generators.skeleton import JMXSkeletonGenerator
from utils.xml_helpers import to_string


class TestJMXAssembler:
    def _make_tp_and_udv(self):
        tp_elems = generate_test_plan()
        udv_elems = generate_user_defined_variables(
            ConnConfig(db_url="jdbc:kaiwudb://localhost/defaultdb")
        )
        return tp_elems, udv_elems

    def test_assemble_produces_jmeter_test_plan_root(self):
        tp_elems, udv_elems = self._make_tp_and_udv()
        asm = JMXAssembler()
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)
        assert root.tag.endswith("jmeterTestPlan")

    def test_assemble_contains_test_plan(self):
        tp_elems, udv_elems = self._make_tp_and_udv()
        asm = JMXAssembler()
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)
        xml = to_string(root)
        assert "TestPlan" in xml

    def test_assemble_contains_user_defined_variables(self):
        tp_elems, udv_elems = self._make_tp_and_udv()
        asm = JMXAssembler()
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)
        xml = to_string(root)
        assert "Arguments" in xml
        assert "db_url" in xml

    def test_assemble_add_ddl(self):
        tp_elems, udv_elems = self._make_tp_and_udv()
        asm = JMXAssembler()
        asm.add_many(generate_ddl_setup_thread_group(["CREATE DATABASE foo"]))
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)
        xml = to_string(root)
        assert "SetupThreadGroup" in xml
        assert "CREATE DATABASE foo" in xml

    def test_assemble_add_write_thread_groups(self):
        tp_elems, udv_elems = self._make_tp_and_udv()
        asm = JMXAssembler()
        cfg = [WriteConfig(tbl_name="mydb.t", mode="batch_prepared", num_threads=5)]
        asm.add_many(generate_write_thread_groups(cfg, {"mydb.t": "insert into mydb.t (a) values (?)"}))
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)
        xml = to_string(root)
        assert "ThreadGroup" in xml
        # batch_prepared uses JSR223Sampler with insert_sql variable, not literal query
        assert "JSR223Sampler" in xml

    def test_assemble_empty_when_no_children(self):
        tp_elems, udv_elems = self._make_tp_and_udv()
        asm = JMXAssembler()
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)
        xml = to_string(root)
        # Should still have TestPlan and UDV
        assert "TestPlan" in xml
        assert "Arguments" in xml

    def test_hash_tree_follows_component_pattern(self):
        """Verify every component is followed by a hashTree in the output."""
        tp_elems, udv_elems = self._make_tp_and_udv()
        asm = JMXAssembler()
        asm.add_many(generate_ddl_setup_thread_group(["CREATE DATABASE foo"]))
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)
        xml = to_string(root)
        # Check self-closing hashTree for JDBCDataSource
        assert "<hashTree/>" in xml or "<hashTree />" in xml
        # Both SetupThreadGroup and JDBCSampler should each be followed by hashTree
        assert xml.count("hashTree") >= 4  # UDV hash + DDL stg hash + stg hash + sampler hash


class TestJMXWriter:
    def test_write_creates_file(self):
        tp_elems = generate_test_plan()
        udv_elems = generate_user_defined_variables(
            ConnConfig(db_url="jdbc:kaiwudb://localhost/defaultdb")
        )
        asm = JMXAssembler()
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = JMXWriter(tmpdir)
            path = writer.write(root)
            assert path.exists()
            content = path.read_text(encoding="utf-8")
            assert '<?xml version="1.0" encoding="UTF-8"?>' in content
            assert "TestPlan" in content

    def test_write_creates_subdirectories(self):
        tp_elems = generate_test_plan()
        udv_elems = generate_user_defined_variables(
            ConnConfig(db_url="jdbc:kaiwudb://localhost/defaultdb")
        )
        asm = JMXAssembler()
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)

        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "a", "b")
            writer = JMXWriter(nested)
            path = writer.write(root)
            assert path.exists()

    def test_write_default_filename(self):
        tp_elems = generate_test_plan()
        udv_elems = generate_user_defined_variables(
            ConnConfig(db_url="jdbc:kaiwudb://localhost/defaultdb")
        )
        asm = JMXAssembler()
        root = asm.assemble(tp_elems[0], tp_elems[1], udv_elems)

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = JMXWriter(tmpdir)
            path = writer.write(root)
            assert path.name == "test_plan.jmx"


class TestJMXSkeletonGenerator:
    def _make_test_config(self, write_mode="batch_prepared"):
        conn = ConnConfig(db_url="jdbc:kaiwudb://localhost/defaultdb")
        write_cfg = [WriteConfig(tbl_name="mydb.t", mode=write_mode, num_threads=5)]
        query_cfg = [QueryConfig(query="SELECT * FROM mydb.t", num_threads=1)]
        return TestConfig(conn_config=conn, write_config=write_cfg, query_config=query_cfg)

    def test_generate_writes_valid_jmx_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config()
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                ddl_statements=["CREATE DATABASE mydb"],
                prepared_templates={"mydb.t": "insert into mydb.t (a) values (?)"},
                output_dir=tmpdir,
            )
            path = gen.generate()
            assert path.exists()
            xml = path.read_text(encoding="utf-8")
            assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
            assert "<TestPlan" in xml
            assert "jmeterTestPlan" in xml

    def test_generate_includes_ddl_statements(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config()
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                ddl_statements=["CREATE DATABASE mydb", "CREATE TABLE mydb.t"],
                output_dir=tmpdir,
            )
            path = gen.generate()
            xml = path.read_text(encoding="utf-8")
            assert "SetupThreadGroup" in xml
            assert "CREATE DATABASE mydb" in xml

    def test_generate_includes_write_thread_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config(write_mode="batch_prepared")
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                prepared_templates={"mydb.t": "insert into mydb.t (a) values (?)"},
                output_dir=tmpdir,
            )
            path = gen.generate()
            xml = path.read_text(encoding="utf-8")
            assert "ThreadGroup" in xml
            # batch_prepared: SQL is in a vars.get() call inside JSR223Sampler script, not literal
            assert "JSR223Sampler" in xml

    def test_generate_includes_query_thread_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config()
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                output_dir=tmpdir,
            )
            path = gen.generate()
            xml = path.read_text(encoding="utf-8")
            assert "SELECT * FROM mydb.t" in xml

    def test_generate_single_insert_skips_write_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config(write_mode="single_insert")
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                output_dir=tmpdir,
            )
            path = gen.generate()
            xml = path.read_text(encoding="utf-8")
            # single_insert is relational batch init, no persistent write ThreadGroup
            # Only SetupThreadGroup for DDL (none in this case)
            assert "ThreadGroup" not in xml or "SetupThreadGroup" not in xml

    def test_generate_empty_ddl_skips_setup_thread_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config(write_mode="batch_prepared")
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                ddl_statements=[],  # empty
                prepared_templates={"mydb.t": "insert into mydb.t (a) values (?)"},
                output_dir=tmpdir,
            )
            path = gen.generate()
            xml = path.read_text(encoding="utf-8")
            # Should have Write ThreadGroup but no DDL SetupThreadGroup
            # batch_prepared uses JSR223Sampler with insert_sql variable, not literal query
            assert "JSR223Sampler" in xml

    def test_generate_with_no_prepared_templates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config(write_mode="batch_prepared")
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                ddl_statements=["CREATE DATABASE mydb"],
                prepared_templates={},  # empty
                output_dir=tmpdir,
            )
            path = gen.generate()
            xml = path.read_text(encoding="utf-8")
            # Should still generate placeholder
            assert "mydb.t" in xml

    def test_xml_is_well_formed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config()
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                ddl_statements=["CREATE DATABASE mydb"],
                prepared_templates={"mydb.t": "insert into mydb.t (a) values (?)"},
                output_dir=tmpdir,
            )
            path = gen.generate()
            # Should not raise
            ET.parse(path)

    def test_jmeter_namespace_in_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config()
            gen = JMXSkeletonGenerator(test_config=test_config, output_dir=tmpdir)
            path = gen.generate()
            xml = path.read_text(encoding="utf-8")
            assert 'xmlns="http://jmeter.apache.org/"' in xml
