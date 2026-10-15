"""Subscriber DDL string builder (OpenSpec pub-sub §3.2 + §3.3).

Per design.md line 311 + V3.3.0 实测(host-native + ent 3.3.0 镜像)+ 参考
docs/refs/kaiwudb-pubsub-references.md §1 官方示例:

- ``build_subscribe_dest_schemas`` (§3.2, D8): 对 ``DDLGenerator.generate``
  输出做两步字符串替换派生 subscriber schema (D4: super-set, 不做列子集
  缩窄)
- ``build_create_subscription_sql`` (§3.3): 拼接 ``CREATE SUBSCRIPTION``
  SQL (per-cluster metadata, 末尾可选 ``WITH OPTIONS (target = '<JSON>')``)

V3.3.0 实测的关键约束(2026-10-15):
- ``target`` value 必须是 3 段 ``<db>.<schema>.<table>`` (默认 ``public``);
  2 段会触发 ``replication from scheme "" is unsupported``
- ``target`` value 用单引号包 JSON object literal (server 解析为
  JSON string 然后内部 deserialize)
- server 自动 default ``enable=on`` / ``retry=5`` / ``ignore_history=on``;
  在 SQL 末尾加逗号分隔的额外 option 会触发 ``at or near "on"/"true"/"5"``
  syntax error
→ SQL builder 只透传 ``target`` 到 ``WITH OPTIONS``,其他 subscription-side
  keys (enable/ignore_history/retry) 由 server 默认,generator 不写

All functions are pure: do not execute SQL, do not connect to a database.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional


def _ensure_fqn_with_schema(qualified_name: str) -> str:
    """Ensure table name has 3 segments ``<db>.<schema>.<table>``.

    Per V3.3.0 实测:2 段表名 ``<db>.<table>`` 触发
    ``replication from scheme "" is unsupported``,必须 3 段。

    2 段 → 自动在中间补 ``public`` (KaiwuDB 默认 schema)。
    3 段 → 原样返回(允许非 ``public`` schema 显式声明)。
    """
    parts = qualified_name.split(".")
    if len(parts) == 2:
        return f"{parts[0]}.public.{parts[1]}"
    return qualified_name


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

    Per docs/refs/kaiwudb-pubsub-references.md §1 官方示例(line 36, 47) +
    V3.3.0 实测(2026-10-15, host-native V3.3.0-dirty):

    - Input: ``subscription_name`` / ``publication_name`` / ``conninfo``
      (libpq URI 形式, **必须含 dbname** — per V3.3.0-dirty 实测:
      keyword=value 无 dbname 报 ``replication from scheme ""``)
    - Input: ``options`` dict 接收 4 个 subscription-side keys:
      ``target`` / ``enable`` / ``ignore_history`` / ``retry``
    - Output: ``str`` like
      ``'CREATE SUBSCRIPTION <name> CONNECTION \\'<conninfo>\\' PUBLICATION <pub_name>'``
      (optionally with trailing `` WITH OPTIONS (k1 = v1, k2 = v2, ...)``)

    WITH OPTIONS 拼接规则(per V3.3.0 实测 + sub-sql.md 官方文档):

    - ``options is None`` or ``len(options) == 0`` → **不**追加
    - ``target`` value 是 JSON 字符串 → ``json.loads`` 解析为 dict,每个
      key/value 跑 ``_ensure_fqn_with_schema``(2 段自动补 ``.public.``),
      然后 ``json.dumps`` 序列化,**整体用单引号包**(per sub-sql.md line 28:
      "target: JSON 格式的字符串")
    - ``enable`` / ``ignore_history`` value 必须用**单引号包**(per
      sub-sql.md line 114 官方 ALTER 例子: ``enable = 'on'``)
    - ``retry`` value 是数字字面 0-10(per sub-sql.md line 28: "支持的取值
      范围为 0-10";实测 ``retry = '5s'`` 报 invalid)
    - 插入顺序保留(Python 3.7+ dict iteration order)

    Scope note: 本 DCR 同集群两库场景下 ``PubSubConfig.options.target`` 必填
    (per D5),caller 实际注入的 ``options`` 永远非空且含 ``target``。
    ``options is None / {}`` 分支仅作多集群扩展预留,防御性覆盖。
    """
    parts: List[str] = [
        f"CREATE SUBSCRIPTION {subscription_name}",
        f"CONNECTION '{conninfo}'",
        f"PUBLICATION {publication_name}",
    ]
    options_parts: List[str] = []
    if options:
        # target: 解析 JSON, 自动补 .public. (2 段 → 3 段), 单引号包
        target_raw = options.get("target")
        if target_raw:
            mapping = json.loads(target_raw)
            mapping_with_schema = {
                _ensure_fqn_with_schema(k): _ensure_fqn_with_schema(v)
                for k, v in mapping.items()
            }
            options_parts.append(
                f"target = '{json.dumps(mapping_with_schema, separators=(',', ':'))}'"
            )
        # enable / ignore_history: 单引号包 value (per sub-sql.md line 114)
        for k in ("enable", "ignore_history"):
            if k in options:
                options_parts.append(f"{k} = '{options[k]}'")
        # retry: 数字字面 (per sub-sql.md line 28: 0-10)
        if "retry" in options:
            options_parts.append(f"retry = {options['retry']}")
    if options_parts:
        parts.append(f"WITH OPTIONS ({', '.join(options_parts)})")
    return " ".join(parts)

