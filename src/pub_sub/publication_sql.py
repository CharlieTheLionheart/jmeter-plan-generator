"""``CREATE PUBLICATION`` SQL string builder (OpenSpec pub-sub §3.1).

Per design.md Decision 1 (D1 段 SQL 形态表 + WITH OPTIONS 拼接规则) +
tasks.md §3.1 acceptance. Pure function — does not execute SQL, does
not connect to a database.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from config_parser.models import PublicationTableEntry


def build_publication_sql(
    publication_name: str,
    publisher_db: str,
    tables: Optional[List[PublicationTableEntry]],
    options: Optional[Dict[str, str]] = None,
) -> str:
    """Build a ``CREATE PUBLICATION`` SQL string per D1's 6-form table.

    SQL 形态 (D1 段):
    - ``tables is None or len(tables) == 0`` →
      ``FOR DATABASE <publisher_db>``
    - ``len(tables) == 1``, no cols/where →
      ``FOR TABLE <pub_db>.<t1>``
    - ``len(tables) == 1``, cols, no where →
      ``FOR TABLE <pub_db>.<t1> (col1, col2, ...)``
    - ``len(tables) == 1``, no cols, where →
      ``FOR TABLE <pub_db>.<t1> WHERE <expr>``
    - ``len(tables) == 1``, cols + where →
      ``FOR TABLE <pub_db>.<t1> (col1, col2, ...) WHERE <expr>``
    - ``len(tables) > 1`` →
      ``FOR TABLE <pub_db>.<t1>, <pub_db>.<t2>, ...``
      (multi-table publication 文档明确不支持 columns/where —
      ``PubSubConfig.multi_table_forbids_columns_and_where`` 校验在
      Pydantic 层完成,本函数直接拼)

    WITH OPTIONS 拼接规则 (D1 段 + design.md line 76-78):
    - ``options is None`` 或 ``len(options) == 0`` → **不**追加
    - 否则 → 末尾追加 `` WITH OPTIONS (k1 = v1, k2 = v2)``
      (Python 3.7+ dict 迭代保留插入顺序,不是字母序)
    - 子句始终在 SQL 末尾(无论 FOR DATABASE / FOR TABLE / WHERE 后)

    Caller-side filtering of subscription-side option keys is NOT this
    function's concern: Pydantic Literal validation on
    ``PubSubConfig.options`` allows the 3 publication-side + 4
    subscription-side keys in a single dict; ``append_pub_sub_to_setup_tg``
    (F-009 caller filtering contract) is responsible for splitting the
    dict before calling ``build_publication_sql`` (publication-side) and
    ``build_create_subscription_sql`` (subscription-side).
    """
    parts: List[str] = [f"CREATE PUBLICATION {publication_name}"]

    if not tables:
        # 整库模式 (None or [] 都走这条)
        parts.append(f"FOR DATABASE {publisher_db}")
    elif len(tables) == 1:
        # 单表模式:4 种 columns/where 组合(per D1 对照表)
        entry = tables[0]
        parts.append(f"FOR TABLE {publisher_db}.{entry.name}")
        if entry.columns:
            parts.append(f"({', '.join(entry.columns)})")
        if entry.where:
            parts.append(f"WHERE {entry.where}")
    else:
        # 多表模式:逗号分隔 FQN, no columns/where
        # (per D1 + PubSubConfig.multi_table_forbids_columns_and_where 校验)
        table_refs = ", ".join(
            f"{publisher_db}.{t.name}" for t in tables
        )
        parts.append(f"FOR TABLE {table_refs}")

    if options:
        # dict 插入顺序保留 (Python 3.7+); options 永远在 SQL 末尾
        options_str = ", ".join(f"{k} = {v}" for k, v in options.items())
        parts.append(f"WITH OPTIONS ({options_str})")

    return " ".join(parts)
