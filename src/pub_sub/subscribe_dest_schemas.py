"""Subscriber DDL string builder (OpenSpec pub-sub §3.2 + §3.3).

Per design.md line 311:

- ``build_subscribe_dest_schemas`` (§3.2, D8): 对 ``DDLGenerator.generate``
  输出做两步字符串替换派生 subscriber schema (D4: super-set, 不做列子集
  缩窄)
- ``build_create_subscription_sql`` (§3.3): 拼接 ``CREATE SUBSCRIPTION``
  SQL (per-cluster metadata, 末尾可选 ``WITH OPTIONS`` 子句)

All functions are pure: do not execute SQL, do not connect to a database.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


def build_subscribe_dest_schemas(
    publisher_ddls: List[str],
    publisher_db: str,
) -> List[str]:
    """Build subscriber-end schema DDLs by string-replacement on publisher DDLs.

    Per design.md line 313-322:

    - Input: ``publisher_ddls`` (``DDLGenerator.generate`` output) +
      ``publisher_db``
    - Output: equal-length ``List[str]`` with each DDL string-replaced
    - 内部硬约定: ``sub_db = f"{publisher_db}_sub"`` (no parameter, no
      ``sub_subscriber_db`` field on ``PubSubConfig`` — fully hard-coded
      per D5 锁定;同集群两库场景下唯一命名规则)

    Two-step replacement (per D8):

    1. ``f'CREATE TS DATABASE {publisher_db}'`` →
       ``f'CREATE TS DATABASE {sub_db}'`` (precise string replace)
    2. ``re.sub(rf'\\b{re.escape(publisher_db)}\\.', f'{sub_db}.', ddl)``
       (word boundary regex — prevents ``iot_monitor_other.t`` from
       being falsely matched as ``iot_monitor`` + ``.``)

    Per D4: subscriber schema = publisher 全列 (super-set, even for
    column-subset publications). This function does **not** narrow
    the subscriber schema based on publication ``columns``; that would
    duplicate DDL generation logic and is not aligned with the
    "subscriber side = super-set" decision.
    """
    sub_db = f"{publisher_db}_sub"
    result: List[str] = []
    for ddl in publisher_ddls:
        # 步骤 1: 大小写不敏感替换 CREATE TS DATABASE
        # 实际 DDLGenerator 输出 ``create ts database if not exists <db>``
        # (小写关键字 + ``if not exists`` 子句), 所以 regex 必须:
        # 1) IGNORECASE (匹配大小写两种 DDL)
        # 2) 容忍可选的 ``if not exists`` 子句
        ddl = re.sub(
            rf"create\s+ts\s+database(\s+if\s+not\s+exists)?\s+{re.escape(publisher_db)}",
            lambda m: f"create ts database{m.group(1) or ''} {sub_db}",
            ddl,
            flags=re.IGNORECASE,
        )
        # 步骤 2: word boundary regex 替换 `<pub_db>.` → `<sub_db>.`
        # \b 防止 iot_monitor 误匹配 iot_monitor_other 的前缀。
        ddl = re.sub(
            rf"\b{re.escape(publisher_db)}\.",
            f"{sub_db}.",
            ddl,
        )
        result.append(ddl)
    return result


def build_create_subscription_sql(
    subscription_name: str,
    publication_name: str,
    conninfo: str,
    options: Optional[Dict[str, str]] = None,
) -> str:
    """Build a ``CREATE SUBSCRIPTION`` SQL string.

    Per design.md line 323-333:

    - Input: ``subscription_name`` / ``publication_name`` / ``conninfo``
      (libpq-format string for the server to reverse-connect to
      publisher) / ``options`` (subscription-side only: ``target`` /
      ``enable`` / ``ignore_history`` / ``retry`` — caller filters
      the 4 keys from the 7-key ``PubSubConfig.options`` dict per
      F-009 caller filtering contract)
    - Output: ``str`` like
      ``'CREATE SUBSCRIPTION <name> CONNECTION \\'<conninfo>\\' PUBLICATION <pub_name>'``
      (optionally with trailing ``WITH OPTIONS (...)``)

    WITH OPTIONS 拼接规则 (与 ``build_publication_sql`` 对齐):

    - ``options is None`` or ``len(options) == 0`` → **不**追加
    - 否则 → 末尾追加 `` WITH OPTIONS (k1 = v1, k2 = v2)``
      (Python 3.7+ dict 保留插入顺序)

    Scope note (per design.md line 333, scope = 同集群两库):
    ``PubSubConfig.options.target`` 是必填(同集群两库场景下服务端无法
    仅靠两端 db.table 名对应推断同步关系,D5 锁定),因此 caller
    (``append_pub_sub_to_setup_tg``) 实际注入的 ``options`` 永远非空。
    本函数支持 ``options is None / options == {}`` 分支仅作多集群
    扩展预留(目标推断规则可能不同),**不应被本 DCR 生产调用触发**。
    """
    parts: List[str] = [
        f"CREATE SUBSCRIPTION {subscription_name}",
        f"CONNECTION '{conninfo}'",
        f"PUBLICATION {publication_name}",
    ]
    if options:
        # 保留 dict 插入顺序 (Python 3.7+); options 永远在 SQL 末尾
        options_str = ", ".join(f"{k} = {v}" for k, v in options.items())
        parts.append(f"WITH OPTIONS ({options_str})")
    return " ".join(parts)

