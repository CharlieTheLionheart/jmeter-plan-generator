"""Tests for relational DDL generation."""

import pytest

from config_parser.models import ColTypeConfig, RelDbConfig, RelTableConfig, TestModelConfig
from ddl_generator import DDLGenerator


def _rel_db(name="iot_metadata", **db_kwargs) -> RelDbConfig:
    table = RelTableConfig(
        name="t_workshop",
        primary_key_count=1,
        data_col_count=1,
        primary_keys=[
            ColTypeConfig(col_type="int8", type_proportion=1.0, nullable=False),
        ],
        data_cols=[
            ColTypeConfig(col_type="varchar(16)", type_proportion=1.0),
        ],
    )
    return RelDbConfig(name=name, tables=[table], **db_kwargs)


def test_create_database_if_not_exists():
    model = TestModelConfig(rel_dbs=[_rel_db(if_not_exists=True)])
    script = DDLGenerator(model).generate()
    assert "create database if not exists iot_metadata;" in script


def test_create_database_with_encoding():
    model = TestModelConfig(rel_dbs=[_rel_db(with_encoding="utf-8")])
    script = DDLGenerator(model).generate()
    assert "create database if not exists iot_metadata with encoding 'utf-8';" in script


def test_create_database_with_comment():
    model = TestModelConfig(rel_dbs=[_rel_db(comment="工业互联网元数据库")])
    script = DDLGenerator(model).generate()
    assert "create database if not exists iot_metadata comment '工业互联网元数据库';" in script


def test_create_table_qualified_name():
    model = TestModelConfig(rel_dbs=[_rel_db()])
    script = DDLGenerator(model).generate()
    assert "create table if not exists iot_metadata.t_workshop" in script
    assert "iot_metadata.t_workshop" in script


def test_create_table_if_not_exists():
    model = TestModelConfig(rel_dbs=[_rel_db()])
    table = model.rel_dbs[0].tables[0]
    table.if_not_exists = True
    script = DDLGenerator(model).generate()
    assert "create table if not exists iot_metadata.t_workshop" in script


def test_create_table_with_comment():
    model = TestModelConfig(rel_dbs=[_rel_db()])
    table = model.rel_dbs[0].tables[0]
    table.comment = "车间表"
    script = DDLGenerator(model).generate()
    assert "comment '车间表';" in script


def test_primary_key_constraint():
    model = TestModelConfig(rel_dbs=[_rel_db()])
    script = DDLGenerator(model).generate()
    assert "primary key (pk_int8_1)" in script


def test_not_null_for_nullable_false():
    model = TestModelConfig(rel_dbs=[_rel_db()])
    script = DDLGenerator(model).generate()
    assert "pk_int8_1 int8 not null" in script


def test_omit_not_null_for_nullable_true():
    model = TestModelConfig(rel_dbs=[_rel_db()])
    script = DDLGenerator(model).generate()
    assert "col_varchar_1 varchar(16)" in script
    assert "col_varchar_1 varchar(16) not null" not in script


def test_lower_case_output():
    model = TestModelConfig(rel_dbs=[_rel_db()])
    script = DDLGenerator(model).generate()
    assert script == script.lower()


def test_multiple_databases_grouping():
    db1 = _rel_db(name="db1")
    db2 = _rel_db(name="db2")
    model = TestModelConfig(rel_dbs=[db1, db2])
    statements = DDLGenerator(model).generate_statements()
    assert statements[0].startswith("create database")
    assert statements[1].startswith("create table if not exists db1")
    assert statements[2].startswith("create database")
    assert statements[3].startswith("create table if not exists db2")
