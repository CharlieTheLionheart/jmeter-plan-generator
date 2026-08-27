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


def test_ts_table_columns_excludes_tag_columns():
    """Regression: tags must not also appear in the column list.

    KaiwuDB rejects ``CREATE TABLE`` whose main column list duplicates a
    column name declared in ``TAGS (...)``.  Primary tags belong only to
    the ``primary tags (...)`` clause; regular tags only to ``tags (...)``.
    """
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    # Extract the column list between the outermost parens after the table name.
    head = script.split("iot_monitor.t_cnc (", 1)[1]
    column_list = head.split(")", 1)[0]
    assert "ptag_int8_1" not in column_list, (
        f"primary tag leaked into column list: {column_list}"
    )
    assert "rtag_varchar_1" not in column_list, (
        f"regular tag leaked into column list: {column_list}"
    )
    assert "ts" in column_list
    assert "col_int8_1" in column_list


def test_ts_table_primary_tags_clause():
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert "primary tags (ptag_int8_1)" in script


def test_ts_table_with_retentions():
    table = _ts_table(retentions="5d")
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    # Per spec §8.2: ``retentions`` is bare (no ``with`` prefix) and
    # the duration is unquoted. The previous shape ``with retentions '5d'``
    # was rejected by KaiwuDB.
    assert "retentions 5d" in script


def test_ts_table_with_hash():
    table = _ts_table(with_hash=100)
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "with hash(100)" in script


def test_ts_table_combined_options():
    table = _ts_table(retentions="5d", with_hash=64)
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    # Per spec §8.2: ``retentions`` is bare, ``with hash`` is LAST.
    assert "retentions 5d" in script
    assert "with hash(64)" in script
    assert script.index("retentions 5d") < script.index("with hash(64)")


def test_ts_table_comment_with_other_options():
    table = _ts_table(retentions="5d", with_hash=64, comment="数控机床表")
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "comment '数控机床表'" in script
    assert "retentions 5d" in script
    assert "with hash(64)" in script
    # Order: retentions < comment < with hash.
    assert script.index("retentions 5d") < script.index("comment '数控机床表'")
    assert script.index("comment '数控机床表'") < script.index("with hash(64)")


def test_ts_table_with_comment():
    table = _ts_table(comment="数控机床表")
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "comment '数控机床表'" in script


def test_ts_table_lower_case():
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert script == script.lower()


# ---------------------------------------------------------------------------
# sparse (KaiwuDB 2.4.1+) — ``create sparse table`` DDL keyword emission
# ---------------------------------------------------------------------------


def test_ts_table_sparse_keyword():
    """sparse=True emits the ``sparse`` keyword between ``create`` and ``table``."""
    table = _ts_table(sparse=True)
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "create sparse table if not exists iot_monitor.t_cnc" in script


def test_ts_table_non_sparse_keyword():
    """sparse=False (default) emits the plain ``create table`` form."""
    model = TestModelConfig(ts_dbs=[_ts_db()])
    script = DDLGenerator(model).generate()
    assert "create table if not exists iot_monitor.t_cnc" in script
    assert "create sparse table" not in script


def test_ts_table_sparse_with_if_not_exists_ordering():
    """``if not exists`` stays directly after ``table`` (spec §8.3)."""
    table = _ts_table(sparse=True, if_not_exists=True)
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    # Scope to the CREATE TABLE statement — the script also contains
    # ``create ts database if not exists iot_monitor`` which would
    # otherwise trip the substring ordering assertions below.
    head = script.split("iot_monitor.t_cnc", 1)[0]
    create_pos = head.rindex("create")
    sparse_pos = head.rindex("sparse")
    table_pos = head.rindex("table")
    ine_pos = head.rindex("if not exists")
    assert create_pos < sparse_pos < table_pos < ine_pos


def test_ts_table_sparse_with_hash_last():
    """sparse + retentions + comment + with_hash: ordering invariants preserved.

    ``with hash(N)`` must remain LAST regardless of sparse flag.
    """
    table = _ts_table(
        sparse=True, retentions="5d", comment="稀疏表", with_hash=64
    )
    model = TestModelConfig(ts_dbs=[_ts_db_with_table(table)])
    script = DDLGenerator(model).generate()
    assert "create sparse table" in script
    assert "retentions 5d" in script
    assert "comment '稀疏表'" in script
    assert "with hash(64)" in script
    assert script.index("retentions 5d") < script.index("with hash(64)")
    assert script.index("comment '稀疏表'") < script.index("with hash(64)")


def test_ts_table_sparse_no_if_not_exists():
    """sparse=True with if_not_exists=False omits the guard clause."""
    table = _ts_table(sparse=True, if_not_exists=False)
    # Disable ``if not exists`` on the database CREATE too, so the script
    # contains no ``if not exists`` substring at all.
    db = TsDbConfig(name="iot_monitor", if_not_exists=False, tables=[table])
    model = TestModelConfig(ts_dbs=[db])
    script = DDLGenerator(model).generate()
    assert "create sparse table iot_monitor.t_cnc" in script
    assert "if not exists" not in script
