"""Pub-sub Verify TG helpers (OpenSpec pub-sub §3.4 + §3.6).

Per design.md §``pub_sub_verify_tg.py`` 段 + tasks.md §3.4-§3.6:

- §3.4 module-private helpers (this commit):
  - ``_build_show_subscription_status_sampler(subscription_name, subscriber_db)``
    builds a JDBCSampler for ``SHOW SUBSCRIPTION <name>`` with a
    RegexExtractor extracting the ``status`` column and a JSR223Assertion
    asserting it contains ``running``.
  - ``_build_count_sampler(publisher_db, table_name, subscriber_db, expected_min_rows)``
    builds a JDBCSampler for ``select count(*) from <subscriber_db>.<table>``
    with a JSR223Assertion asserting ``count_1 >= expected_min_rows``.

- §3.6 public function (next commit):
  - ``generate_pub_sub_verify_tg(pub_sub_config, test_model_config)`` —
    assembles the full Verify PostThreadGroup hashTree.

Per design.md line 587-598 caller pattern: ``sampler.append(child)``
where child is a ``<RegexExtractor>`` or ``<JSR223Assertion>`` element.
The caller is expected to be aware of where these children belong
(paired-hashTree vs nested-under-sampler); per design.md, this module
follows the ``sampler.append(child)`` pattern explicitly.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Tuple

from config_parser.models import PubSubConfig, TestModelConfig
from utils.xml_helpers import (
    empty_hash_tree,
    jdbc_sampler_element,
    jsr223_assertion_element,
    regex_extractor_element,
    teardown_thread_group_element,
)


def _build_show_subscription_status_sampler(
    subscription_name: str,
    subscriber_db: str,
) -> ET.Element:
    """Build the ``SHOW SUBSCRIPTION <name>`` sampler for the Verify TG.

    Per design.md line 580-599:
    - JDBCSampler name = ``ShowSubscription-{subscription_name}``
    - JDBCSampler query = ``SHOW SUBSCRIPTION {subscription_name}``
    - JDBCSampler ``variable_names='status'`` (JDBC Request binds first
      column to ``vars.get('status')``)
    - RegexExtractor ``ref_name='sub_status'`` extracts ``status`` column
      from the pipe-separated ``SHOW SUBSCRIPTION`` output
    - JSR223Assertion asserts ``vars.get('sub_status')?.contains('running')``

    ``subscriber_db`` is accepted for API symmetry with
    ``_build_count_sampler`` (per tasks.md §3.4.2 signature) but is
    not used in the sampler: ``SHOW SUBSCRIPTION`` is a per-cluster
    metadata query (per D5: not bound to a specific database), so the
    query runs on the default-pool connection regardless of which db
    the subscription logically serves.
    """
    # JMeter schema 要求 sampler + paired hashTree 交替 (per JMXAssembler
    # docstring line 37-38: "component, <hashTree/>, component, ...");
    # regex_extractor / jsr223_assertion 必须在 sampler 自己的 paired hashTree
    # 内部, 不是 sampler 元素内部 (实测 ~/Downloads/JSR223 Assertion.jmx
    # line 35-56 是这个结构). 直接用 jdbc_sampler_element 返回的 sampler_hash
    # 装 child + 各自 paired empty hashTree (per rest_write_groups.py:515-522).
    sampler, sampler_hash = jdbc_sampler_element(
        name=f"ShowSubscription-{subscription_name}",
        query=f"show subscription {subscription_name}",
        variable_names="status",
    )
    sampler_hash.append(regex_extractor_element(
        ref_name="sub_status",
        regex=r"status\s*\|\s*(\w+)",
        template="$1$",
        match_number=1,
    ))
    sampler_hash.append(empty_hash_tree())  # paired with RegexExtractor
    sampler_hash.append(jsr223_assertion_element(
        script=f"""
def s = vars.get('sub_status')
assert s != null && s.contains('running') : 'subscription not running, status=' + s
""",
    ))
    sampler_hash.append(empty_hash_tree())  # paired with JSR223Assertion
    return sampler, sampler_hash


def _build_count_sampler(
    publisher_db: str,
    table_name: str,
    subscriber_db: str,
    expected_min_rows: int,
) -> ET.Element:
    """Build a ``count(*) from <subscriber_db>.<table>`` sampler for the Verify TG.

    Per design.md line 605-618:
    - JDBCSampler name = ``CountRows-{subscriber_db}-{table_name}``
    - JDBCSampler query = ``select count(*) from {subscriber_db}.{table_name}``
      (FQN 跨库查, 在 defaultdb 连接上跑 — per D5)
    - JDBCSampler ``variable_names='count'`` (JDBC Request binds count(*)
      to ``vars.get('count_1')``)
    - JSR223Assertion asserts ``vars.get('count_1') as int >= expected_min_rows``

    ``publisher_db`` is accepted for API symmetry (per tasks.md §3.4.2
    signature) but is **not** used in the sampler query: the count(*)
    is read from the **subscriber** table (FQN 跨库查), so the query
    only references ``{subscriber_db}.{table_name}``. The publisher
    db name is a caller-context hint (used by the verify TG assembly
    loop in §3.6 to iterate over ``test_model_config.ts_dbs``).
    """
    # 同 _build_show_subscription_status_sampler: child + 各自 paired
    # empty hashTree 装到 sampler 自己的 sampler_hash 内 (per rest_write_groups
    # 模式 + JMeter schema 严格 alternating)
    sampler, sampler_hash = jdbc_sampler_element(
        name=f"CountRows-{subscriber_db}-{table_name}",
        query=f"select count(*) from {subscriber_db}.{table_name}",
        variable_names="count",
    )
    sampler_hash.append(jsr223_assertion_element(
        script=f"""
def n = vars.get('count_1') as int
assert n >= {expected_min_rows} : 'row count ' + n + ' below threshold {expected_min_rows}'
""",
    ))
    sampler_hash.append(empty_hash_tree())  # paired with JSR223Assertion
    return sampler, sampler_hash


def generate_pub_sub_verify_tg(
    pub_sub_config: PubSubConfig,
    test_model_config: TestModelConfig,
) -> Tuple[ET.Element, ET.Element]:
    """Assemble the full Verify PostThreadGroup + paired hashTree (per §3.6).

    Per design.md line 513-380 + tasks.md §3.6:

    - 输入: ``pub_sub_config`` (Pydantic) + ``test_model_config`` (Pydantic)
    - 输出: ``(tg, tg_hash)`` — PostThreadGroup 节点 + 配对 hashTree
      (delegated to §2 ``teardown_thread_group_element`` 通用 paired
      factory)
    - 内部派生:
      - ``sub_db = f"{pub_sub_config.publisher_db}_sub"`` (D5 硬约定)
      - ``expected_min_rows = pub_sub_config.expected_min_rows
        if not None else 1`` (内联默认, per D3 锁定)
    - 元素结构 (per design.md line 528-378):
      1. PostThreadGroup (num_threads=1, ramp_time=1, delay=60s, 无
         ``ThreadGroup.duration``, ``LoopController.loops=1``) —
         委托 §2 ``teardown_thread_group_element``
      2. 1 个 SHOW SUBSCRIPTION status sampler + RegexExtractor + JSR223Assertion
         (委托 §3.4 ``_build_show_subscription_status_sampler``)
      3. N 个 ``select count(*) from <sub_db>.<table>`` sampler
         (每张 ts_table 一条, 委托 §3.4 ``_build_count_sampler``)
    - 装配: 所有 sampler 收集到 ``samplers`` 列表, 一次性作为
      ``children`` kwarg 传入 §2 helper(per F 决定: aligned paired
      hashTree 模式, 跟 ``setup_thread_group_element`` 一致)

    Per D5 (单池 + FQN 跨库): 所有 sampler 都用 ``dataSource='default_pool'``
    引用同一条 JDBC Connection Configuration, sampler query 走 FQN 表名
    跨库查, **不** 写 ``database`` 字段 (per F-013 / 实际 jmx schema,
    JMeter 5.6.3 JDBCSampler 无此字段)。
    """
    sub_db = f"{pub_sub_config.publisher_db}_sub"

    # D3 内联默认: pub_sub_config.expected_min_rows = None → 兜底 1
    expected_min_rows = (
        pub_sub_config.expected_min_rows
        if pub_sub_config.expected_min_rows is not None
        else 1
    )

    # 收集所有 sampler + paired hashTree 元组, 展平为
    # (sampler, hashTree, sampler, hashTree, ...) 序列 传给 §2 helper
    # 的 children kwarg (per F 决定: aligned paired hashTree 模式).
    # JMeter schema 要求 component + paired hashTree 交替, 所以 sampler 和
    # 它自己的 paired hashTree 必须相邻 — 展平后顺序正确
    # (per JMXAssembler docstring line 37-38).
    sampler_pairs: List[ET.Element] = []
    show_sampler, show_hash = _build_show_subscription_status_sampler(
        subscription_name=pub_sub_config.subscription_name,
        subscriber_db=sub_db,  # = <publisher_db>_sub
    )
    sampler_pairs.extend([show_sampler, show_hash])
    for ts_db in test_model_config.ts_dbs:
        for table in ts_db.tables:
            count_sampler, count_hash = _build_count_sampler(
                publisher_db=ts_db.name,
                table_name=table.name,
                subscriber_db=sub_db,  # = <publisher_db>_sub
                expected_min_rows=expected_min_rows,
            )
            sampler_pairs.extend([count_sampler, count_hash])

    return teardown_thread_group_element(
        name=f"VerifyTearDownTG-PubSub-{pub_sub_config.subscription_name}",
        num_threads=1,
        ramp_time=1,
        delay=60,  # 主 TG 结束后等 60s 让 CDC 同步完成
        # duration 不显式设: per §2 helper 不输出 ThreadGroup.duration
        children=sampler_pairs,
    )
