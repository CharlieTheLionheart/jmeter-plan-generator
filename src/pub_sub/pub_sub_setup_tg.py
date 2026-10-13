"""Append pub-sub DDL chain to existing SetupTG (OpenSpec pub-sub §3.5).

Per design.md §``pub_sub_setup_tg.py`` 段 + tasks.md §3.5:

- 4 步顺序 (per design.md line 350-353):
  1. ``CreatePublication-<name>`` — 委托 ``build_publication_sql``
  2/3. ``CreateSubscriberDDL`` — 内部含 ``CREATE TS DATABASE <sub_db>`` +
       ``CREATE TABLE <sub_db>.<x> ...``(``;`` 分隔多条 SQL 合并到单 sampler,
       per 2026-10-12 user 提议: KaiwuDB JDBC driver 支持一次执行
       ``;`` 分隔的多条 SQL, 循环注入多 sampler 太臃肿)
  4. ``CreateSubscription-<name>`` — 委托 ``build_create_subscription_sql``

- 内部派生:
  - ``sub_db = f"{publisher_db}_sub"`` 硬约定(per D5 锁定)
  - ``publisher_ddls = DDLGenerator(test_model_config).generate_statements()``
- caller 过滤契约 (F-009): subscription-side options 4-key
  ``SUBSCRIPTION_OPTION_KEYS = frozenset({"target", "enable",
  "ignore_history", "retry"})`` 在调用 ``build_create_subscription_sql``
  前由 caller 端过滤;publication-side options 全传给
  ``build_publication_sql``
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from config_parser.models import PubSubConfig, TestModelConfig
from ddl_generator.generator import DDLGenerator
from pub_sub.publication_sql import build_publication_sql
from pub_sub.subscribe_dest_schemas import (
    build_create_subscription_sql,
    build_subscribe_dest_schemas,
)
from utils.xml_helpers import jdbc_sampler_element


# F-009 caller 过滤契约: caller 端在调用 build_publication_sql /
# build_create_subscription_sql 前分别过滤 pub_sub_config.options,
# 只保留对应 side 的 keys(对称)
PUBLICATION_OPTION_KEYS = frozenset({
    "buffer_size", "retrieve_tags", "publish",
})
SUBSCRIPTION_OPTION_KEYS = frozenset({
    "target", "enable", "ignore_history", "retry",
})


def append_pub_sub_to_setup_tg(
    setup_tg_element: ET.Element,
    pub_sub_config: PubSubConfig,
    test_model_config: TestModelConfig,
) -> None:
    """Append the pub-sub DDL chain to an existing SetupTG hashTree.

    Per design.md line 459-510 + tasks.md §3.5:

    - 输入: ``setup_tg_element`` (现有 SetupTG 的 paired ``<hashTree>``,
      由 ``generate_ddl_setup_thread_group`` 构造) + ``pub_sub_config``
      + ``test_model_config``
    - 输出: ``None`` (原地修改 ``setup_tg_element``)
    - 追加 3 个 JDBC Sampler(per design.md 实际代码 line 473/484/506;
      步骤 2 的 CREATE TS DATABASE sub 合并到步骤 3 的 CreateSubscriberDDL)

    Note on ``DDLGenerator`` call: design.md line 469 writes
    ``DDLGenerator.generate(test_model_config)`` but ``DDLGenerator.generate``
    returns a single ``;\n``-joined string, not a ``List[str]`` (per
    src/ddl_generator/generator.py:155). We use
    ``DDLGenerator(test_model_config).generate_statements()`` to get the
    list form required by ``build_subscribe_dest_schemas``.
    """
    pub_db = pub_sub_config.publisher_db
    sub_db = f"{pub_db}_sub"

    # 内部派生 publisher_ddls (避免 JMXSkeletonGenerator 在调用前先 derive 一次)
    publisher_ddls = DDLGenerator(test_model_config).generate_statements()

    # 步骤 1: CREATE PUBLICATION (单 sampler, FQN 表名 <publisher_db>.<t>)
    # F-009 caller 过滤: 只把 publication-side keys 传给 build_publication_sql
    pub_options = {
        k: v
        for k, v in pub_sub_config.options.items()
        if k in PUBLICATION_OPTION_KEYS
    }
    pub_sql = build_publication_sql(
        publication_name=pub_sub_config.publication_name,
        publisher_db=pub_db,
        tables=pub_sub_config.tables,
        options=pub_options,
    )
    pub_sampler, _ = jdbc_sampler_element(
        name=f"CreatePublication-{pub_sub_config.publication_name}",
        query=pub_sql,
    )
    setup_tg_element.append(pub_sampler)

    # 步骤 2 + 3 合并: CREATE TS DATABASE sub + CREATE TABLE sub.x 合并到单 sampler
    # (per 2026-10-12 user 提议: KaiwuDB JDBC driver 支持 `;` 分隔多条 SQL)
    subscribe_dest_schemas_ddls = build_subscribe_dest_schemas(
        publisher_ddls, pub_db
    )
    combined_subscriber_ddl = "; ".join(subscribe_dest_schemas_ddls)
    ddl_sampler, _ = jdbc_sampler_element(
        name="CreateSubscriberDDL",
        query=combined_subscriber_ddl,
    )
    setup_tg_element.append(ddl_sampler)

    # 步骤 4: CREATE SUBSCRIPTION
    # F-009 caller 过滤契约: 只把 subscription-side keys 传给 build_create_subscription_sql
    sub_options = {
        k: v
        for k, v in pub_sub_config.options.items()
        if k in SUBSCRIPTION_OPTION_KEYS
    }
    sub_sql = build_create_subscription_sql(
        subscription_name=pub_sub_config.subscription_name,
        publication_name=pub_sub_config.publication_name,
        conninfo=pub_sub_config.conninfo,
        options=sub_options,
    )
    sub_sampler, _ = jdbc_sampler_element(
        name=f"CreateSubscription-{pub_sub_config.subscription_name}",
        query=sub_sql,
    )
    setup_tg_element.append(sub_sampler)
