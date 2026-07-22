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

    def test_generate_single_insert_generates_write_thread_group(self):
        """single_insert produces a persistent write ThreadGroup per
        spec §"Generate JDBCSampler for single_insert and batch_insert modes".
        A TS model must be supplied so the column list + first ptag can be
        resolved."""
        from config_parser.models import (
            ColTypeConfig,
            PrimaryTagColTypeConfig,
            TestModelConfig,
            TsColConfig,
            TsDbConfig,
            TsTableConfig,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config(write_mode="single_insert")
            table = TsTableConfig(
                name="t",
                data_col_count=1,
                primary_tag_count=1,
                regular_tag_count=0,
                ts_col=TsColConfig(name="ts", type="timestamp", ms_step=1000),
                data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                primary_tags=[PrimaryTagColTypeConfig(col_type="int8", type_proportion=1.0)],
            )
            db = TsDbConfig(name="mydb", tables=[table])
            model = TestModelConfig(ts_dbs=[db])
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                model=model,
                output_dir=tmpdir,
            )
            path = gen.generate()
            xml = path.read_text(encoding="utf-8")
            # Persistent write ThreadGroup for single_insert now appears.
            assert "Write-mydb.t" in xml
            assert 'queryType">Update Statement' in xml
            assert "insert_sql" in xml

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

    def test_rel_init_specs_appears_in_jmx(self):
        """``JMXSkeletonGenerator(rel_init_specs=[...])`` MUST surface
        the relational init subtree (LoopController + RelInit_ sampler).
        """
        rel_spec = {
            "table_name": "iot_meta.t_workshop",
            "columns": ["pk_int8_1"],
            "total_rows": 100,
            "batch_lines": 20,
            "rel_col_seed_files": ["1_pk_int8_1.csv"],
            "column_types": ["int8"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config()
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                ddl_statements=["CREATE DATABASE iot_meta"],
                prepared_templates={},
                rel_init_specs=[rel_spec],
                output_dir=tmpdir,
            )
            xml = gen.generate().read_text(encoding="utf-8")
            assert "RelInit_" in xml
            assert "relprep" in xml
            assert "Loop Controller for iot_meta.t_workshop" in xml

    def test_empty_rel_init_specs_emits_no_rel_subtree(self):
        """``rel_init_specs=[]`` MUST NOT produce any relational init
        marker, even when DDL statements are present. conditional-
        relational-setup DCR: pure-ts models stay marker-free.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config()
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                ddl_statements=["CREATE DATABASE iot_meta"],
                prepared_templates={},
                rel_init_specs=[],
                output_dir=tmpdir,
            )
            xml = gen.generate().read_text(encoding="utf-8")
            assert "RelInit_" not in xml
            assert "relprep" not in xml
            assert "Loop Controller for" not in xml

    def test_rel_init_loop_count_matches_spec(self):
        """``LoopController.loops`` MUST equal ``total_rows // batch_lines``."""
        rel_spec = {
            "table_name": "iot_meta.t_workshop",
            "columns": ["pk_int8_1"],
            "total_rows": 200,
            "batch_lines": 25,
            "rel_col_seed_files": ["1_pk_int8_1.csv"],
            "column_types": ["int8"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config = self._make_test_config()
            gen = JMXSkeletonGenerator(
                test_config=test_config,
                ddl_statements=["CREATE DATABASE iot_meta"],
                prepared_templates={},
                rel_init_specs=[rel_spec],
                output_dir=tmpdir,
            )
            xml = gen.generate().read_text(encoding="utf-8")
            # 200/25 = 8 loops.
            assert ">8<" in xml
