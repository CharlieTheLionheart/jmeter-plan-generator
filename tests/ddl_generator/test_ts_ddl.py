"""Tests for time-series DDL generation."""

from config_parser.models import (
    ColTypeConfig,
    PrimaryTagColTypeConfig,
    TsDbConfig,
    TsTableConfig,
    TestModelConfig,
)
from ddl_generator import DDLGenerator


def _ts_table(**table_kwargs) -> TsTableConfig:
    return TsTableConfig(
        name="t_cnc",
        data_col_count=1,
        primary_tag_count=1,
        regular_tag_count=1,
        data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
        primary_tags=[PrimaryTagColTypeConfig(col_type="int8", type_proportion=1.0)],
        regular_tags=[ColTypeConfig(col_type="varchar(10)", type_proportion=1.0)],
        **table_kwargs,
    )


def _ts_db(name="iot_monitor", **db_kwargs) -> TsDbConfig:
    return TsDbConfig(name=name, tables=[_ts_table()], **db_kwargs)


def _ts_db_with_table(table: TsTableConfig, name="iot_monitor", **db_kwargs) -> TsDbConfig:
    return TsDbConfig(name=name, tables=[table], **db_kwargs)


def test_create_ts_database():
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert "create ts database if not exists iot_monitor;" in script


def test_create_ts_database_retentions():
    model = TestModelConfig(ts_dbs=[_ts_db(retentions="3d")])
    script = DDLGenerator(model).generate()
    assert "create ts database if not exists iot_monitor retentions 3d;" in script


def test_create_ts_database_partition_interval():
    model = TestModelConfig(ts_dbs=[_ts_db(partition_interval="1d")])
    script = DDLGenerator(model).generate()
    assert "create ts database if not exists iot_monitor partition interval 1d;" in script


def test_create_ts_table_qualified():
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert "create table if not exists iot_monitor.t_cnc" in script


def test_ts_table_has_timestamp_column():
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert "ts timestamp not null" in script


def test_ts_table_tags_clause():
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert "tags (ptag_int8_1 int8 not null, rtag_varchar_1 varchar(10))" in script


def test_ts_table_primary_tags_clause():
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert "primary tags (ptag_int8_1)" in script


def test_ts_table_with_retentions():
    table = _ts_table(retentions="5d")
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "with retentions '5d'" in script


def test_ts_table_with_hash():
    table = _ts_table(with_hash=100)
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "with hash(100)" in script


def test_ts_table_combined_options():
    table = _ts_table(retentions="5d", with_hash=64)
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "with retentions '5d' with hash(64)" in script


def test_ts_table_comment_with_other_options():
    table = _ts_table(retentions="5d", with_hash=64, comment="数控机床表")
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "comment '数控机床表'" in script
    assert "with retentions '5d'" in script
    assert "with hash(64)" in script


def test_ts_table_with_comment():
    table = _ts_table(comment="数控机床表")
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "comment '数控机床表'" in script


def test_ts_table_lower_case():
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert script == script.lower()
