"""Tests for utils.xml_helpers."""

import pytest
from xml.etree import ElementTree as ET

from utils.xml_helpers import (
    bool_prop,
    collection_prop,
    element_prop,
    empty_hash_tree,
    hash_tree,
    int_prop,
    jdbc_data_source_element,
    jdbc_sampler_element,
    jsr223_preprocessor_element,
    long_prop,
    make_element,
    string_prop,
    test_plan_element,
    thread_group_element,
    setup_thread_group_element,
    argument_element,
    constant_throughput_timer_element,
    to_string,
)
from jmx_skeleton_generator.generators.ddl_setup import generate_ddl_setup_thread_group


class TestMakeElement:
    def test_name_attribute(self):
        elem = make_element("stringProp", name="foo.bar", text="hello")
        assert elem.attrib["name"] == "foo.bar"

    def test_testname_attribute(self):
        elem = make_element("JDBCSampler", testname="My Sampler")
        assert elem.attrib["testname"] == "My Sampler"

    def test_attributes_override(self):
        elem = make_element("JDBCSampler", name="sampler1", attributes={"enabled": "false"})
        assert elem.attrib["name"] == "sampler1"
        assert elem.attrib["enabled"] == "false"

    def test_children_appended(self):
        parent = make_element("TestPlan", children=[string_prop("TestPlan.comments", "note")])
        assert len(parent) == 1
        assert parent[0].attrib["name"] == "TestPlan.comments"


class TestPropHelpers:
    def test_string_prop(self):
        elem = string_prop("db_url", "jdbc:kaiwudb://localhost")
        assert elem.tag.endswith("stringProp")
        assert elem.attrib["name"] == "db_url"
        assert elem.text == "jdbc:kaiwudb://localhost"

    def test_bool_prop(self):
        elem = bool_prop("enabled", "true")
        assert elem.tag.endswith("boolProp")
        assert elem.text == "true"

    def test_int_prop(self):
        elem = int_prop("ThreadGroup.num_threads", 10)
        assert elem.text == "10"

    def test_long_prop(self):
        elem = long_prop("ThreadGroup.duration", 3600)
        assert elem.text == "3600"


class TestHashTree:
    def test_empty_hash_tree_serializes(self):
        xml = to_string(empty_hash_tree())
        assert "<hashTree" in xml
        assert "/>" in xml  # self-closing tag

    def test_hash_tree_with_children(self):
        ht = hash_tree(string_prop("key", "value"))
        xml = to_string(ht)
        assert "stringProp" in xml


class TestArgumentElement:
    def test_returns_tuple_of_two_elements(self):
        result = argument_element("UDV")
        assert isinstance(result, tuple)
        assert len(result) == 2
        args, h = result
        assert args.tag.endswith("Arguments")
        assert h.tag.endswith("hashTree")

    def test_second_element_is_hash_tree(self):
        _, h = argument_element("UDV")
        xml = to_string(h)
        assert "<hashTree" in xml  # has namespace prefix + self-closing


class TestTestPlanElement:
    def test_returns_testplan_and_hash_tree(self):
        result = test_plan_element("MyPlan")
        assert len(result) == 2
        tp, ht = result
        assert tp.tag.endswith("TestPlan")
        assert tp.attrib["name"] == "MyPlan"
        assert ht.tag.endswith("hashTree")

    def test_includes_teardown_prop(self):
        # test_plan_element without props produces an empty element;
        # the actual teardown prop is added by generate_test_plan()
        from jmx_skeleton_generator.generators.test_plan import generate_test_plan
        tp, _ = generate_test_plan()
        xml = to_string(tp)
        assert "TestPlan.tearDown_on_shutdown" in xml


class TestSetupThreadGroupElement:
    def test_returns_tuple(self):
        result = setup_thread_group_element("MySetup")
        assert len(result) == 2

    def test_contains_loop_controller(self):
        stg, _ = setup_thread_group_element("Setup")
        xml = to_string(stg)
        assert "LoopController" in xml
        assert "SetupThreadGroup.on_sample_error" in xml

    def test_empty_ddl_returns_empty_list(self):
        result = generate_ddl_setup_thread_group([])
        assert result == []

    def test_ddl_sampler_is_update_statement(self):
        from jmx_skeleton_generator.generators.ddl_setup import generate_ddl_setup_thread_group
        elems = generate_ddl_setup_thread_group(["CREATE DATABASE foo"])
        # find JDBCSampler
        for e in elems:
            if e.tag.endswith("JDBCSampler"):
                xml = to_string(e)
                assert "Update Statement" in xml
                break


class TestThreadGroupElement:
    def test_returns_tuple(self):
        result = thread_group_element("Write-T1")
        assert len(result) == 2

    def test_scheduler_enabled(self):
        tg, _ = thread_group_element("TG1", scheduler=True)
        xml = to_string(tg)
        assert "ThreadGroup.scheduler" in xml
        assert "true" in xml

    def test_infinite_loops(self):
        tg, _ = thread_group_element("TG1", loops="-1")
        xml = to_string(tg)
        assert "LoopController.loops" in xml


class TestJdbcSamplerElement:
    def test_returns_tuple(self):
        result = jdbc_sampler_element("Samp1", "SELECT 1")
        assert len(result) == 2
        samp, ht = result
        assert samp.tag.endswith("JDBCSampler")
        assert ht.tag.endswith("hashTree")

    def test_query_in_element(self):
        samp, _ = jdbc_sampler_element("Samp1", "SELECT * FROM t")
        xml = to_string(samp)
        assert "SELECT * FROM t" in xml
        assert "dataSource" in xml


class TestJdbcDataSourceElement:
    def test_returns_tuple(self):
        result = jdbc_data_source_element("pool1", "jdbc:kaiwudb://localhost", "com.kaiwudb.Driver")
        assert len(result) == 2

    def test_db_url_property(self):
        ds, _ = jdbc_data_source_element("pool1", "jdbc:kaiwudb://localhost", "com.kaiwudb.Driver")
        xml = to_string(ds)
        assert "dbUrl" in xml
        assert "jdbc:kaiwudb://localhost" in xml

    def test_driver_property(self):
        ds, _ = jdbc_data_source_element("pool1", "jdbc:kaiwudb://localhost", "com.kaiwudb.Driver")
        xml = to_string(ds)
        assert "com.kaiwudb.Driver" in xml


class TestJsr223PreprocessorElement:
    def test_returns_tuple(self):
        result = jsr223_preprocessor_element("PreProc1", "vars.put('k','v')")
        assert len(result) == 2

    def test_script_in_element(self):
        proc, _ = jsr223_preprocessor_element("PreProc1", "vars.put('k','v')")
        xml = to_string(proc)
        assert "vars.put" in xml
        assert "scriptLanguage" in xml


class TestConstantThroughputTimerElement:
    def test_returns_tuple(self):
        result = constant_throughput_timer_element("Timer1")
        assert len(result) == 2

    def test_calc_mode(self):
        timer, _ = constant_throughput_timer_element("Timer1", calc_mode=0)
        xml = to_string(timer)
        assert "calcMode" in xml


class TestCollectionProp:
    def test_collection_prop_with_children(self):
        cp = collection_prop("Arguments.arguments", children=[
            element_prop("key1", "Argument", props=[
                string_prop("Argument.name", "key1"),
                string_prop("Argument.value", "val1"),
            ])
        ])
        xml = to_string(cp)
        assert "collectionProp" in xml
        assert "Arguments.arguments" in xml
        assert "key1" in xml


class TestSerialization:
    def test_xml_declaration_utf8(self):
        elem = test_plan_element("P")[0]
        xml = to_string(elem)
        assert '<?xml version' in xml
        assert 'encoding=' in xml

    def test_jmeter_namespace(self):
        elem = test_plan_element("P")[0]
        xml = to_string(elem)
        assert 'xmlns="http://jmeter.apache.org/"' in xml

    def test_self_closing_hash_tree(self):
        elem = empty_hash_tree()
        xml = to_string(elem)
        assert "<hashTree" in xml
        assert "/>" in xml  # self-closing, not expanded tags
