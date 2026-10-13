"""Subscriber DDL string builder (OpenSpec pub-sub §3.2).

Per design.md §``build_subscribe_dest_schemas`` 段 (D8):

- 对 ``DDLGenerator.generate`` 输出做两步字符串替换派生 subscriber
  schema (D4: super-set, 不做列子集缩窄)
- 纯函数: 不执行 SQL, 不连数据库

``build_create_subscription_sql`` (§3.3) lives in the same module per
design.md line 311, but is implemented separately per the TDD rhythm
in tasks.md §3.3.
"""

from __future__ import annotations

import re
from typing import List


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
        # 步骤 1: 字符串精确替换 CREATE TS DATABASE
        # 整库名 + 大写 SQL 关键字(per design.md 字面规范)。
        # 大小写敏感:SQL 关键字在 publisher 端按字面写大写。
        ddl = ddl.replace(
            f"CREATE TS DATABASE {publisher_db}",
            f"CREATE TS DATABASE {sub_db}",
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

