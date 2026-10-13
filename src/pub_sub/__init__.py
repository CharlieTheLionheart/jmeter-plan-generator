"""Pub-sub pub-sub DDL chain + verify TG (OpenSpec pub-sub §3).

Per design.md line 281-285 + tasks.md §3.7, the public API surface
(5 functions exposed via ``from pub_sub import X``) is:

- ``build_publication_sql`` — 第 6 种 ``CREATE PUBLICATION`` SQL 形态
- ``build_subscribe_dest_schemas`` — subscriber schema 字符串替换
- ``build_create_subscription_sql`` — ``CREATE SUBSCRIPTION`` SQL 拼接
- ``append_pub_sub_to_setup_tg`` — SetupTG 末尾追加 4 步 pub-sub DDL 链
- ``generate_pub_sub_verify_tg`` — Verify PostThreadGroup 编排

Module-private helpers (``_build_show_subscription_status_sampler`` /
``_build_count_sampler``) are **not** part of the public surface — callers
must go through ``pub_sub.pub_sub_verify_tg`` to access them, ensuring
the post-processing pipeline stays internal to the generator.
"""

from pub_sub.pub_sub_setup_tg import append_pub_sub_to_setup_tg
from pub_sub.pub_sub_verify_tg import generate_pub_sub_verify_tg
from pub_sub.publication_sql import build_publication_sql
from pub_sub.subscribe_dest_schemas import (
    build_create_subscription_sql,
    build_subscribe_dest_schemas,
)


__all__ = [
    "build_publication_sql",
    "build_subscribe_dest_schemas",
    "build_create_subscription_sql",
    "append_pub_sub_to_setup_tg",
    "generate_pub_sub_verify_tg",
]
