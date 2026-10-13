"""Tests for ``src/pub_sub/subscribe_dest_schemas.py``.

Two public APIs in the same module (per design.md line 311):

- ``build_subscribe_dest_schemas`` (§3.2, D8): 对
  ``DDLGenerator.generate`` 输出做两步字符串替换派生 subscriber schema
  (D4: super-set, 不做列子集缩窄)
- ``build_create_subscription_sql`` (§3.3): 拼接 ``CREATE SUBSCRIPTION``
  SQL 字符串,末尾可选 ``WITH OPTIONS`` 子句

Per design.md line 333 scope note: ``options.target`` 在本 DCR 同集群
两库场景下必填 → caller 实际注入的 options 永远非空 → 本函数支持
``options is None / {}`` 分支仅作多集群扩展预留,**pytest 防御性覆盖**
(本测试覆盖),**smoke test 不覆盖**。
"""

from __future__ import annotations

from pub_sub.subscribe_dest_schemas import (
    build_create_subscription_sql,
    build_subscribe_dest_schemas,
)


class TestBuildSubscribeDestSchemasEmpty:
    """空输入 / 不含 pub_db 字串的 DDL."""

    def test_empty_list_returns_empty_list(self) -> None:
        """``[]`` → ``[]``(不抛异常,空 pipeline 是合法输入)."""
        out = build_subscribe_dest_schemas([], "iot_monitor")
        assert out == []

    def test_ddl_without_pub_db_unchanged(self) -> None:
        """不含 pub_db 字串的 DDL 保持不变(无副作用)."""
        ddl = "CREATE USER foo WITH PASSWORD 'bar';"
        out = build_subscribe_dest_schemas([ddl], "iot_monitor")
        assert out == [ddl]


class TestBuildSubscribeDestSchemasCreateDatabase:
    """步骤 1: ``CREATE TS DATABASE <pub_db>`` → ``CREATE TS DATABASE <pub_db>_sub``
    (字符串精确替换)."""

    def test_simple_substitution(self) -> None:
        """基本替换: ``create ts database iot_monitor`` → ``create ts database iot_monitor_sub``.

        Note: 实际 DDLGenerator 输出小写 SQL 关键字(``create ts
        database``, 不是 ``CREATE TS DATABASE``), 所以测试用小写。
        ``build_subscribe_dest_schemas`` 用 ``re.IGNORECASE`` 匹配,
        replacement 保留小写。"""
        out = build_subscribe_dest_schemas(
            ["create ts database iot_monitor"], "iot_monitor"
        )
        assert out == ["create ts database iot_monitor_sub"]

    def test_different_publisher_db(self) -> None:
        """不同 ``publisher_db`` → 不同 sub_db(内部硬约定 ``f"{publisher_db}_sub"``)."""
        out = build_subscribe_dest_schemas(
            ["create ts database other_db"], "other_db"
        )
        assert out == ["create ts database other_db_sub"]

    def test_precise_substitution_no_partial_match(self) -> None:
        """精确替换: ``create ts database other_db`` (pub_db=iot_monitor) 不变."""
        out = build_subscribe_dest_schemas(
            ["create ts database other_db"], "iot_monitor"
        )
        assert out == ["create ts database other_db"]

    def test_case_insensitive_uppercase(self) -> None:
        """大写 ``CREATE TS DATABASE`` 也应被替换(IGNORECASE flag).

        Per DDLGenerator 实际输出 + design.md 字面规范, 关键字既可
        大写也可小写。``re.IGNORECASE`` 让函数对两种都接受。
        """
        out = build_subscribe_dest_schemas(
            ["CREATE TS DATABASE iot_monitor"], "iot_monitor"
        )
        # 替换保留小写(replacement 模板是固定的)
        assert out == ["create ts database iot_monitor_sub"]


class TestBuildSubscribeDestSchemasTableQualifiedName:
    """步骤 2: ``<pub_db>.`` → ``<pub_db>_sub.`` (word boundary regex)."""

    def test_table_qualified_name_substitution(self) -> None:
        """基本替换: ``CREATE TABLE iot_monitor.t_cnc`` → ``... iot_monitor_sub.t_cnc``."""
        ddl = "CREATE TABLE iot_monitor.t_cnc (ts TIMESTAMP NOT NULL)"
        out = build_subscribe_dest_schemas([ddl], "iot_monitor")
        assert out == [
            "CREATE TABLE iot_monitor_sub.t_cnc (ts TIMESTAMP NOT NULL)"
        ]

    def test_word_boundary_no_false_match(self) -> None:
        """反例: ``iot_monitor_other.t`` 不可被误匹配(``iot_monitor`` 后不是 ``.``).

        Per design.md line 321: ``\\b{re.escape(publisher_db)}\\.`` — word
        boundary 防止 ``iot_monitor`` 匹配 ``iot_monitor_other`` 的前缀。
        """
        out = build_subscribe_dest_schemas(
            ["SELECT * FROM iot_monitor_other.t_cnc"],
            "iot_monitor",
        )
        # iot_monitor_other.t 中的 iot_monitor 不应被替换
        assert out == ["SELECT * FROM iot_monitor_other.t_cnc"]

    def test_qualified_name_with_schema(self) -> None:
        """``iot_monitor.t_cnc`` 在任意位置都应被替换(SQL 中段)."""
        ddl = "INSERT INTO iot_monitor.t_cnc VALUES (1)"
        out = build_subscribe_dest_schemas([ddl], "iot_monitor")
        assert out == ["INSERT INTO iot_monitor_sub.t_cnc VALUES (1)"]


class TestBuildSubscribeDestSchemasCombined:
    """组合测试: 多 DDL + 完整 publisher DDL."""

    def test_full_publisher_ddl_combined(self) -> None:
        """完整 publisher DDL (建库 + 建表 合并到一条字符串) → 全部替换."""
        ddl = (
            "create ts database iot_monitor;\n"
            "create table iot_monitor.t_cnc "
            "(ts TIMESTAMP NOT NULL, k VARCHAR(64)) "
            "tags (k VARCHAR(64)) primary tags (k) with (retentions 3d);"
        )
        out = build_subscribe_dest_schemas([ddl], "iot_monitor")
        assert out == [
            "create ts database iot_monitor_sub;\n"
            "create table iot_monitor_sub.t_cnc "
            "(ts TIMESTAMP NOT NULL, k VARCHAR(64)) "
            "tags (k VARCHAR(64)) primary tags (k) with (retentions 3d);"
        ]

    def test_multiple_ddls_all_replaced(self) -> None:
        """多条 DDL(typical ``DDLGenerator.generate_statements`` 输出)全部替换."""
        out = build_subscribe_dest_schemas(
            [
                "create ts database iot_monitor",
                "create table iot_monitor.t1 (k INT)",
                "create table iot_monitor.t2 (k INT)",
            ],
            "iot_monitor",
        )
        assert out == [
            "create ts database iot_monitor_sub",
            "create table iot_monitor_sub.t1 (k INT)",
            "create table iot_monitor_sub.t2 (k INT)",
        ]

    def test_word_boundary_among_replacement(self) -> None:
        """混合场景: 同一条 DDL 含 ``iot_monitor.t1`` (应替换) +
        ``iot_monitor_other.t2`` (不应替换)."""
        ddl = (
            "create table iot_monitor.t1 (k INT);\n"
            "create table iot_monitor_other.t2 (k INT);"
        )
        out = build_subscribe_dest_schemas([ddl], "iot_monitor")
        assert out == [
            "create table iot_monitor_sub.t1 (k INT);\n"
            "create table iot_monitor_other.t2 (k INT);"
        ]


class TestBuildSubscribeDestSchemasSubDbConvention:
    """``sub_db = f"{publisher_db}_sub"`` 内部硬约定(不作为参数)."""

    def test_sub_db_convention_consistent_across_publisher_dbs(self) -> None:
        """两个不同 publisher_db → 两个不同 sub_db(从结果推断硬约定正确)."""
        out1 = build_subscribe_dest_schemas(
            ["create ts database iot_monitor"], "iot_monitor"
        )
        out2 = build_subscribe_dest_schemas(
            ["create ts database benchmark"], "benchmark"
        )
        assert out1 == ["create ts database iot_monitor_sub"]
        assert out2 == ["create ts database benchmark_sub"]
        # 不同 publisher_db → 不同 sub_db 后缀
        assert "iot_monitor_sub" in out1[0]
        assert "benchmark_sub" in out2[0]


# ===========================================================================
# build_create_subscription_sql (OpenSpec §3.3)
# ===========================================================================

class TestBuildCreateSubscriptionSql:
    """``CREATE SUBSCRIPTION`` SQL 字符串拼接(per design.md line 323-333).

    基础形态: ``CREATE SUBSCRIPTION <name> CONNECTION '<conninfo>' PUBLICATION <pub_name>``
    (末尾可选 `` WITH OPTIONS (...)``)。
    """

    def test_basic_no_options(self) -> None:
        """无 options: 基础 ``CREATE SUBSCRIPTION ... CONNECTION '...' PUBLICATION ...``."""
        sql = build_create_subscription_sql(
            subscription_name="sub_iot",
            publication_name="pub_iot",
            conninfo="postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
        )
        assert sql == (
            "CREATE SUBSCRIPTION sub_iot "
            "CONNECTION 'postgresql://root@localhost:26257/iot_monitor?sslmode=disable' "
            "PUBLICATION pub_iot"
        )

    def test_options_none_no_with_options(self) -> None:
        """``options=None`` → 不追加 ``WITH OPTIONS`` (默认参数)."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options=None,
        )
        assert "WITH OPTIONS" not in sql

    def test_options_default_none(self) -> None:
        """``options`` 缺省(= None) → 不追加 ``WITH OPTIONS`` (签名默认)."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
        )
        assert "WITH OPTIONS" not in sql

    def test_options_empty_dict_no_with_options(self) -> None:
        """``options={}`` → 不追加 ``WITH OPTIONS`` (防御性覆盖,per design.md scope note)."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={},
        )
        assert "WITH OPTIONS" not in sql

    def test_options_appended(self) -> None:
        """``options`` 非空 → 末尾追加 `` WITH OPTIONS (...)``."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={"target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc"},
        )
        assert sql == (
            "CREATE SUBSCRIPTION sub_iot "
            "CONNECTION 'postgresql://root@localhost:26257/iot_monitor?sslmode=disable' "
            "PUBLICATION pub_iot "
            "WITH OPTIONS (target = iot_monitor.t_cnc=iot_monitor_sub.t_cnc)"
        )

    def test_options_insertion_order_preserved(self) -> None:
        """``options`` dict 插入顺序保留 (Python 3.7+ dict iteration order)."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={
                "target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc",
                "enable": "on",
            },
        )
        # 插入顺序: target → enable
        assert sql.endswith(
            "WITH OPTIONS (target = iot_monitor.t_cnc=iot_monitor_sub.t_cnc, enable = on)"
        )
        # 换插入顺序确认不是字母序
        sql2 = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={
                "enable": "on",
                "target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc",
            },
        )
        assert sql2.endswith("WITH OPTIONS (enable = on, target = iot_monitor.t_cnc=iot_monitor_sub.t_cnc)")

    def test_all_four_subscription_side_keys(self) -> None:
        """4 个 subscription-side keys 都接受 (``target`` / ``enable`` /
        ``ignore_history`` / ``retry``,per design.md line 329)."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={
                "target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc",
                "enable": "on",
                "ignore_history": "true",
                "retry": "5s",
            },
        )
        # 插入顺序保留
        assert sql.endswith(
            "WITH OPTIONS ("
            "target = iot_monitor.t_cnc=iot_monitor_sub.t_cnc, "
            "enable = on, "
            "ignore_history = true, "
            "retry = 5s"
            ")"
        )

    def test_connection_quoted_with_single_quote(self) -> None:
        """``conninfo`` 用单引号包裹 (per design.md line 331)."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@host:5432/db",
        )
        # CONNECTION '<conninfo>'
        assert "CONNECTION 'postgresql://root@host:5432/db'" in sql
