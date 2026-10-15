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
    """``CREATE SUBSCRIPTION`` SQL 字符串拼接.

    Per docs/refs/kaiwudb-pubsub-references.md §1 官方示例(line 47) +
    V3.3.0 实测(host-native + ent 3.3.0 镜像):

    基础形态: ``CREATE SUBSCRIPTION <name> CONNECTION '<conninfo>' PUBLICATION <pub_name>``
    (末尾可选 `` WITH OPTIONS (target = '<JSON>')``)。

    关键约束(per V3.3.0 实测):
    - ``target`` value 必须是 3 段表名 ``<db>.<schema>.<table>``(默认 schema
      是 ``public``,2 段自动补)
    - ``target`` value 用单引号包 JSON object literal
      (例 ``'{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}'``)
    - server 自动 default ``enable=on`` / ``retry=5`` / ``ignore_history=on``;
      写多 option 会触发语法错误(at or near "on"/"true"/"5"),所以 SQL
      builder 只透传 ``target``,忽略其他 subscription-side keys
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
        """``options={}`` → 不追加 ``WITH OPTIONS`` (防御性覆盖)."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={},
        )
        assert "WITH OPTIONS" not in sql

    def test_options_no_target_key_still_emits_with_options(self) -> None:
        """``options`` 无 ``target`` key 但有其他 keys → **仍然** 追加
        ``WITH OPTIONS``(包含 enable/retry/ignore_history)。

        Per V3.3.0 实测 + sub-sql.md:4 个 subscription-side keys 各自独立
        可用。本 DCR ``PubSubConfig.options.target`` 必填 (per D5),caller
        注入永远含 target,本分支仅作多集群扩展预留。"""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={"enable": "on", "retry": "5"},
        )
        assert "WITH OPTIONS" in sql
        assert "enable = 'on'" in sql
        assert "retry = '5'" in sql

    def test_all_four_subscription_side_keys_with_correct_value_forms(self) -> None:
        """``options`` 含 4 个 subscription-side keys → 全部进 SQL,各自 value 形式按 sub-sql.md:

        - ``target`` 单引号包 JSON,3 段
        - ``enable`` / ``ignore_history`` 单引号包 value
        - ``retry`` 数字字面(无引号)

        Per sub-sql.md line 114 官方 ALTER 例子: ``enable = 'on'``。"""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={
                "target": '{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}',
                "enable": "on",
                "ignore_history": "on",
                "retry": "5",
            },
        )
        assert sql.endswith(
            "WITH OPTIONS ("
            "target = '{\"iot_monitor.public.t_cnc\":\"iot_monitor_sub.public.t_cnc\"}', "
            "enable = 'on', "
            "ignore_history = 'on', "
            "retry = '5'"
            ")"
        )

    def test_target_value_wrapped_in_single_quotes(self) -> None:
        """``target`` value 整体用单引号包(JSON string literal).

        Per V3.3.0 实测 + reference §1 官方示例:
        ``target='{"benchmark.public.cpu":"sub_bench.public.sub_cpu"}'``.

        Note: fixture 必须写 3 段 ``<db>.public.<table>``(per V3.3.0
        实测 2 段触发 ``replication from scheme "" is unsupported``)。本测试
        用 3 段 input 验证单引号包 JSON 的拼接逻辑;2 段自动补段行为见
        ``test_target_2_segment_gets_public_added``。"""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={"target": '{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}'},
        )
        assert "target = '{\"iot_monitor.public.t_cnc\":\"iot_monitor_sub.public.t_cnc\"}'" in sql

    def test_target_2_segment_gets_public_added(self) -> None:
        """``target`` 2 段表名 ``<db>.<table>`` → 自动补 ``.public.`` 中间段.

        Per V3.3.0 实测:2 段报 ``replication from scheme \"\" is unsupported``;
        3 段 OK. 所以 generator 在 SQL 拼接时自动补 ``public`` schema."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={"target": '{"iot_monitor.t_cnc":"iot_monitor_sub.t_cnc"}'},
        )
        # 2 段表名 → 3 段
        assert "iot_monitor.public.t_cnc" in sql
        assert "iot_monitor_sub.public.t_cnc" in sql
        # 不应保留 2 段
        assert '"iot_monitor.t_cnc"' not in sql
        assert '"iot_monitor_sub.t_cnc"' not in sql

    def test_target_3_segment_unchanged(self) -> None:
        """``target`` 已是 3 段 ``<db>.public.<table>`` → 不修改."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            options={"target": '{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}'},
        )
        assert "iot_monitor.public.t_cnc" in sql
        assert "iot_monitor_sub.public.t_cnc" in sql
        # 不会被错误地补成 4 段
        assert "iot_monitor.public.public.t_cnc" not in sql

    def test_connection_quoted_with_single_quote(self) -> None:
        """``conninfo`` 用单引号包裹 (per design.md line 331)."""
        sql = build_create_subscription_sql(
            "sub_iot", "pub_iot",
            "postgresql://root@host:5432/db",
        )
        # CONNECTION '<conninfo>'
        assert "CONNECTION 'postgresql://root@host:5432/db'" in sql
