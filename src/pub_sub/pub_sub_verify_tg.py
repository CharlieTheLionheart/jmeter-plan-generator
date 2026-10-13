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

from utils.xml_helpers import (
    jdbc_sampler_element,
    jsr223_assertion_element,
    regex_extractor_element,
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
    # 解构 jdbc_sampler_element 忽略 paired hashTree
    # (caller 端负责把 sampler 放到合适的 hashTree 位置,见 design.md line 559-572)
    sampler, _ = jdbc_sampler_element(
        name=f"ShowSubscription-{subscription_name}",
        query=f"SHOW SUBSCRIPTION {subscription_name}",
        variable_names="status",
    )
    sampler.append(regex_extractor_element(
        ref_name="sub_status",
        regex=r"status\s*\|\s*(\w+)",
        template="$1$",
        match_number=1,
    ))
    sampler.append(jsr223_assertion_element(
        script=f"""
def s = vars.get('sub_status')
assert s != null && s.contains('running') : 'subscription not running, status=' + s
""",
    ))
    return sampler


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
    # 解构 jdbc_sampler_element 忽略 paired hashTree (同上注释)
    sampler, _ = jdbc_sampler_element(
        name=f"CountRows-{subscriber_db}-{table_name}",
        query=f"select count(*) from {subscriber_db}.{table_name}",
        variable_names="count",
    )
    sampler.append(jsr223_assertion_element(
        script=f"""
def n = vars.get('count_1') as int
assert n >= {expected_min_rows} : 'row count ' + n + ' below threshold {expected_min_rows}'
""",
    ))
    return sampler
