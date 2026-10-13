"""Tests for ``src/pub_sub/publication_sql.py::build_publication_sql``.

Per design.md Decision 1 (D1 段 SQL 形态表 + WITH OPTIONS 拼接规则) +
tasks.md §3.1 acceptance:

- 6 SQL 形态(整库 / 单表 / 单表+列子集 / 单表+WHERE / 单表+列子集+WHERE / 多表)
- WITH OPTIONS 拼接(无 options 不追加 / 有 options 含 publication-side
  keys 才追加 / 12 形态插入顺序保留)

Note: caller-side filtering of subscription-side option keys
(``target`` / ``enable`` / ``ignore_history`` / ``retry``) is the
caller's responsibility (``append_pub_sub_to_setup_tg`` per F-009) and
is exercised in ``test_pub_sub_setup_tg.py`` (tasks.md §3.5.1). This
test file does NOT assert that filtering contract — ``build_publication_sql``
just stringifies the options dict in insertion order, period.
"""

from __future__ import annotations

from typing import Optional

from config_parser.models import PublicationTableEntry
from pub_sub.publication_sql import build_publication_sql


# ---------------------------------------------------------------------------
# 6 SQL 形态 (D1 对照表)
# ---------------------------------------------------------------------------

class TestBuildPublicationSqlDatabaseMode:
    """整库模式:``tables=None`` / ``tables=[]`` → ``FOR DATABASE <db>``."""

    def test_tables_none(self) -> None:
        """``tables=None`` → ``CREATE PUBLICATION <name> FOR DATABASE <db>``."""
        sql = build_publication_sql("pub_iot", "iot_monitor", None)
        assert sql == "CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor"

    def test_tables_empty_list(self) -> None:
        """``tables=[]`` → 整库模式 (与 ``None`` 等价)."""
        sql = build_publication_sql("pub_iot", "iot_monitor", [])
        assert sql == "CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor"


class TestBuildPublicationSqlTableMode:
    """表级模式 (``len(tables)==1``):各种 columns / where 组合."""

    def test_single_table_no_columns_no_where(self) -> None:
        """``len(tables)==1``, 无 columns 无 where → ``FOR TABLE <db>.<t1>``."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor",
            [PublicationTableEntry(name="t_cnc")],
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot FOR TABLE iot_monitor.t_cnc"
        )

    def test_single_table_with_columns(self) -> None:
        """``len(tables)==1`` + ``columns`` → ``FOR TABLE <db>.<t1> (col1, col2)``."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor",
            [PublicationTableEntry(
                name="t_cnc",
                columns=["k_timestamp", "device_id", "col_float8_1"],
            )],
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot FOR TABLE iot_monitor.t_cnc "
            "(k_timestamp, device_id, col_float8_1)"
        )

    def test_single_table_with_where(self) -> None:
        """``len(tables)==1`` + ``where`` → ``FOR TABLE <db>.<t1> WHERE <expr>``."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor",
            [PublicationTableEntry(name="t_cnc", where="col_float8_1 > 0")],
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot FOR TABLE iot_monitor.t_cnc "
            "WHERE col_float8_1 > 0"
        )

    def test_single_table_with_columns_and_where(self) -> None:
        """``len(tables)==1`` + ``columns`` + ``where`` → ``FOR TABLE <db>.<t1> (cols) WHERE <expr>``."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor",
            [PublicationTableEntry(
                name="t_cnc",
                columns=["k_timestamp", "col_float8_1"],
                where="col_float8_1 > 0",
            )],
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot FOR TABLE iot_monitor.t_cnc "
            "(k_timestamp, col_float8_1) WHERE col_float8_1 > 0"
        )


class TestBuildPublicationSqlMultiTableMode:
    """多表模式 (``len(tables)>1``) →  ``FOR TABLE <db>.<t1>, <db>.<t2>, ...``."""

    def test_two_tables(self) -> None:
        """``len(tables)==2`` → 两个 FQN 表名逗号分隔."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor",
            [
                PublicationTableEntry(name="t_cnc"),
                PublicationTableEntry(name="t_cnc2"),
            ],
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot "
            "FOR TABLE iot_monitor.t_cnc, iot_monitor.t_cnc2"
        )

    def test_three_tables(self) -> None:
        """``len(tables)==3`` → 三个 FQN 表名逗号分隔(顺序保留)."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor",
            [
                PublicationTableEntry(name="t_a"),
                PublicationTableEntry(name="t_b"),
                PublicationTableEntry(name="t_c"),
            ],
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot "
            "FOR TABLE iot_monitor.t_a, iot_monitor.t_b, iot_monitor.t_c"
        )


# ---------------------------------------------------------------------------
# WITH OPTIONS 拼接规则
# ---------------------------------------------------------------------------

class TestBuildPublicationSqlWithOptions:
    """``WITH OPTIONS`` 拼接规则 (per D1 段 + design.md line 77-78):

    - ``options=None`` 或 ``options={}`` → **不**追加 ``WITH OPTIONS``
    - ``options`` 非空 → 末尾追加 ``WITH OPTIONS (k1 = v1, k2 = v2)``
      (保留 dict 插入顺序)
    - WITH OPTIONS 始终在 SQL 末尾(无论 FOR DATABASE / FOR TABLE / WHERE 后)
    """

    def test_no_options_no_with_options_clause(self) -> None:
        """``options=None`` → ``WITH OPTIONS`` 不出现."""
        sql = build_publication_sql("pub_iot", "iot_monitor", None, None)
        assert "WITH OPTIONS" not in sql

    def test_empty_dict_no_with_options_clause(self) -> None:
        """``options={}`` → ``WITH OPTIONS`` 不出现 (空 dict 等价于无 options)."""
        sql = build_publication_sql("pub_iot", "iot_monitor", None, {})
        assert "WITH OPTIONS" not in sql

    def test_default_options_none(self) -> None:
        """``options`` 缺省 (= None) → ``WITH OPTIONS`` 不出现 (签名默认)."""
        sql = build_publication_sql("pub_iot", "iot_monitor", None)
        assert "WITH OPTIONS" not in sql

    def test_options_appended_to_database_mode(self) -> None:
        """整库模式 + options → 末尾追加 ``WITH OPTIONS (...)``."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor", None,
            {"buffer_size": "4", "publish": "insert"},
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor "
            "WITH OPTIONS (buffer_size = 4, publish = insert)"
        )

    def test_options_appended_after_table_where(self) -> None:
        """表级 + WHERE + options → ``WITH OPTIONS`` 在 WHERE 子句之后."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor",
            [PublicationTableEntry(name="t_cnc", where="col_float8_1 > 0")],
            {"buffer_size": "4"},
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot "
            "FOR TABLE iot_monitor.t_cnc WHERE col_float8_1 > 0 "
            "WITH OPTIONS (buffer_size = 4)"
        )

    def test_options_appended_after_columns_and_where(self) -> None:
        """表级 + columns + WHERE + options → ``WITH OPTIONS`` 在末尾."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor",
            [PublicationTableEntry(
                name="t_cnc",
                columns=["k_timestamp", "col_float8_1"],
                where="col_float8_1 > 0",
            )],
            {"buffer_size": "4"},
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot "
            "FOR TABLE iot_monitor.t_cnc (k_timestamp, col_float8_1) "
            "WHERE col_float8_1 > 0 "
            "WITH OPTIONS (buffer_size = 4)"
        )

    def test_options_insertion_order_preserved(self) -> None:
        """``options`` dict 插入顺序保留(不是字母序).

        This is a key contract: ``append_pub_sub_to_setup_tg`` relies on
        the dict's insertion order to align publication-side vs
        subscription-side options with the same iteration order.
        """
        sql = build_publication_sql(
            "pub_iot", "iot_monitor", None,
            {
                "buffer_size": "4",
                "publish": "insert",
                "retrieve_tags": "true",
            },
        )
        # 插入顺序: buffer_size → publish → retrieve_tags
        # 不是字母序 (buffer_size, publish, retrieve_tags 碰巧按字母升序也是同样结果,
        # 所以再换个顺序,确认不是字母序):
        sql2 = build_publication_sql(
            "pub_iot", "iot_monitor", None,
            {
                "retrieve_tags": "true",
                "buffer_size": "4",
                "publish": "insert",
            },
        )
        assert sql.endswith(
            "WITH OPTIONS (buffer_size = 4, publish = insert, retrieve_tags = true)"
        )
        assert sql2.endswith(
            "WITH OPTIONS (retrieve_tags = true, buffer_size = 4, publish = insert)"
        )

    def test_all_three_publication_side_keys(self) -> None:
        """3 个 publication-side keys 都接受 (Pydantic Literal 校验在
        PubSubConfig 层完成,本函数只负责拼接,见设计段)."""
        sql = build_publication_sql(
            "pub_iot", "iot_monitor", None,
            {
                "buffer_size": "4",
                "retrieve_tags": "true",
                "publish": "insert",
            },
        )
        assert sql == (
            "CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor "
            "WITH OPTIONS (buffer_size = 4, retrieve_tags = true, publish = insert)"
        )

    def test_options_value_quoted_correctly(self) -> None:
        """options value 是带引号字符串 → 字面拼到 SQL (caller 保证 quoting).

        Per design.md: ``options`` 字典的 key + value 字符串字面直接
        拼到对应 DDL 的 ``WITH OPTIONS`` 子句(保留插入顺序),不二次 quote.
        """
        sql = build_publication_sql(
            "pub_iot", "iot_monitor", None,
            {"publish": "'insert,update'"},
        )
        # value 字面带单引号直接拼
        assert sql == (
            "CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor "
            "WITH OPTIONS (publish = 'insert,update')"
        )
