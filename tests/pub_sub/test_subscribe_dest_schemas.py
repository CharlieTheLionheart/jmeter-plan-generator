"""Tests for ``src/pub_sub/subscribe_dest_schemas.py::build_subscribe_dest_schemas``.

Per design.md §``build_subscribe_dest_schemas`` 段 + D8:

- 输入: ``publisher_ddls: List[str]`` (来自 ``DDLGenerator.generate``) +
  ``publisher_db: str``
- 输出: 等长 ``List[str]``,每条 DDL 做两步字符串替换
- 内部硬约定: ``sub_db = f"{publisher_db}_sub"`` (不作为参数)
- 替换规则:
  1. ``f'CREATE TS DATABASE {publisher_db}'`` →
     ``f'CREATE TS DATABASE {publisher_db}_sub'`` (字符串精确替换)
  2. ``re.sub(rf'\\b{re.escape(publisher_db)}\\.', '{pub}_sub.', ddl)``
     (word boundary regex,防误匹配 ``iot_monitor_other.t``)

D4 锁定: subscriber schema = publisher 全列(即使列子集发布也保持
super-set),所以本函数只做"db 名前缀替换",**不**做"列子集缩窄"。
"""

from __future__ import annotations

from pub_sub.subscribe_dest_schemas import build_subscribe_dest_schemas


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
        """基本替换: ``CREATE TS DATABASE iot_monitor`` → ``... iot_monitor_sub``."""
        out = build_subscribe_dest_schemas(
            ["CREATE TS DATABASE iot_monitor"], "iot_monitor"
        )
        assert out == ["CREATE TS DATABASE iot_monitor_sub"]

    def test_different_publisher_db(self) -> None:
        """不同 ``publisher_db`` → 不同 sub_db(内部硬约定 ``f"{publisher_db}_sub"``)."""
        out = build_subscribe_dest_schemas(
            ["CREATE TS DATABASE other_db"], "other_db"
        )
        assert out == ["CREATE TS DATABASE other_db_sub"]

    def test_precise_substitution_no_partial_match(self) -> None:
        """精确替换: ``CREATE TS DATABASE other_db`` (pub_db=iot_monitor) 不变."""
        out = build_subscribe_dest_schemas(
            ["CREATE TS DATABASE other_db"], "iot_monitor"
        )
        assert out == ["CREATE TS DATABASE other_db"]


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
            "CREATE TS DATABASE iot_monitor;\n"
            "CREATE TABLE iot_monitor.t_cnc "
            "(ts TIMESTAMP NOT NULL, k VARCHAR(64)) "
            "TAGS (k VARCHAR(64)) PRIMARY TAGS (k) WITH (retentions 3d);"
        )
        out = build_subscribe_dest_schemas([ddl], "iot_monitor")
        assert out == [
            "CREATE TS DATABASE iot_monitor_sub;\n"
            "CREATE TABLE iot_monitor_sub.t_cnc "
            "(ts TIMESTAMP NOT NULL, k VARCHAR(64)) "
            "TAGS (k VARCHAR(64)) PRIMARY TAGS (k) WITH (retentions 3d);"
        ]

    def test_multiple_ddls_all_replaced(self) -> None:
        """多条 DDL(typical ``DDLGenerator.generate_statements`` 输出)全部替换."""
        out = build_subscribe_dest_schemas(
            [
                "CREATE TS DATABASE iot_monitor",
                "CREATE TABLE iot_monitor.t1 (k INT)",
                "CREATE TABLE iot_monitor.t2 (k INT)",
            ],
            "iot_monitor",
        )
        assert out == [
            "CREATE TS DATABASE iot_monitor_sub",
            "CREATE TABLE iot_monitor_sub.t1 (k INT)",
            "CREATE TABLE iot_monitor_sub.t2 (k INT)",
        ]

    def test_word_boundary_among_replacement(self) -> None:
        """混合场景: 同一条 DDL 含 ``iot_monitor.t1`` (应替换) +
        ``iot_monitor_other.t2`` (不应替换)."""
        ddl = (
            "CREATE TABLE iot_monitor.t1 (k INT);\n"
            "CREATE TABLE iot_monitor_other.t2 (k INT);"
        )
        out = build_subscribe_dest_schemas([ddl], "iot_monitor")
        assert out == [
            "CREATE TABLE iot_monitor_sub.t1 (k INT);\n"
            "CREATE TABLE iot_monitor_other.t2 (k INT);"
        ]


class TestBuildSubscribeDestSchemasSubDbConvention:
    """``sub_db = f"{publisher_db}_sub"`` 内部硬约定(不作为参数)."""

    def test_sub_db_convention_consistent_across_publisher_dbs(self) -> None:
        """两个不同 publisher_db → 两个不同 sub_db(从结果推断硬约定正确)."""
        out1 = build_subscribe_dest_schemas(
            ["CREATE TS DATABASE iot_monitor"], "iot_monitor"
        )
        out2 = build_subscribe_dest_schemas(
            ["CREATE TS DATABASE benchmark"], "benchmark"
        )
        assert out1 == ["CREATE TS DATABASE iot_monitor_sub"]
        assert out2 == ["CREATE TS DATABASE benchmark_sub"]
        # 不同 publisher_db → 不同 sub_db 后缀
        assert "iot_monitor_sub" in out1[0]
        assert "benchmark_sub" in out2[0]
