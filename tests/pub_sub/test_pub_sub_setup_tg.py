"""Tests for ``src/pub_sub/pub_sub_setup_tg.py::append_pub_sub_to_setup_tg``.

Per design.md §``pub_sub_setup_tg.py`` 段 + tasks.md §3.5:

- 输入: ``setup_tg_element`` (SetupTG 的 paired ``<hashTree>``) +
  ``pub_sub_config`` (Pydantic) + ``test_model_config`` (Pydantic)
- 输出: ``None`` (原地修改 ``setup_tg_element``, append 4 个 JDBC Sampler)
- 4 步顺序 (per design.md line 350-353):
  1. ``CreatePublication-<name>`` — 委托 ``build_publication_sql``
  2. (内含步骤 2/3: 实际为 3 个 sampler — CREATE TS DATABASE
     sub_db + CREATE TABLE sub_db.x ... 合并到单个 ``CreateSubscriberDDL``)
  4. ``CreateSubscription-<name>`` — 委托 ``build_create_subscription_sql``
- 内部派生:
  - ``sub_db = f"{pub_db}_sub"`` 硬约定
  - ``publisher_ddls = DDLGenerator.generate(test_model_config)`` 内部调用
- caller 过滤契约 (F-009): subscription-side options 由 caller 端
  用 ``SUBSCRIPTION_OPTION_KEYS = frozenset({"target", "enable",
  "ignore_history", "retry"})`` 过滤后传给 ``build_create_subscription_sql``
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from config_parser.models import (
    ColTypeConfig,
    ConnConfig,
    PrimaryTagColTypeConfig,
    PubSubConfig,
    PublicationTableEntry,
    TestConfig,
    TestModelConfig,
    TsColConfig,
    TsDbConfig,
    TsTableConfig,
)
from pub_sub.pub_sub_setup_tg import append_pub_sub_to_setup_tg


NS = "{http://jmeter.apache.org/}"


def _local(tag: str) -> str:
    return tag[len(NS):] if tag.startswith(NS) else tag


def _find_child(elem: ET.Element, tag: str) -> ET.Element | None:
    for child in elem:
        if _local(child.tag) == tag:
            return child
    return None


def _find_prop(elem: ET.Element, tag: str, name: str) -> ET.Element | None:
    for child in elem:
        if _local(child.tag) == tag and child.get("name") == name:
            return child
    return None


def _find_samplers_in_order(setup_tg: ET.Element) -> list[ET.Element]:
    """Return all JDBCSampler children in insertion order, skipping
    paired-hashTree siblings."""
    return [
        c for c in setup_tg
        if _local(c.tag) == "JDBCSampler"
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_test_model() -> TestModelConfig:
    """Build a minimal TestModelConfig with one ts db + one table."""
    table = TsTableConfig(
        name="t_cnc",
        ts_col=TsColConfig(name="ts", type="timestamp", ms_step=1000),
        primary_tag_count=1,
        regular_tag_count=1,
        data_col_count=1,
        primary_tags=[
            PrimaryTagColTypeConfig(col_type="int4", type_proportion=1.0),
        ],
        regular_tags=[
            ColTypeConfig(col_type="int4", type_proportion=1.0),
        ],
        data_cols=[
            ColTypeConfig(col_type="float8", type_proportion=1.0),
        ],
    )
    return TestModelConfig(
        ts_dbs=[TsDbConfig(name="iot_monitor", tables=[table])],
    )


def _build_pubsub_config(
    *,
    publisher_db: str = "iot_monitor",
    publication_name: str = "pub_iot",
    subscription_name: str = "sub_iot",
    tables: Optional[list[PublicationTableEntry]] = None,
    options: Optional[dict[str, str]] = None,
) -> PubSubConfig:
    """Build a PubSubConfig that passes self-consistent validation."""
    if options is None:
        # Per sub-sql.md + V3.3.0 实测: target 必须 3 段 + enable='on'
        options = {
            "target": '{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}',
            "enable": "on",
        }
    return PubSubConfig(
        publisher_db=publisher_db,
        publication_name=publication_name,
        subscription_name=subscription_name,
        conninfo="postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
        tables=tables,
        options=options,
    )


def _build_test_config(pubsub: PubSubConfig) -> TestConfig:
    """Wrap a PubSubConfig into a minimal TestConfig (required by
    TestConfig validator; not actually used by append_pub_sub_to_setup_tg)."""
    return TestConfig(
        conn_config=ConnConfig(db_url="jdbc:kaiwudb://localhost:26257/defaultdb"),
        pub_sub_config=pubsub,
    )


def _build_setup_tg() -> ET.Element:
    """Build a minimal SetupTG paired ``<hashTree>`` (empty container)."""
    return ET.Element(f"{NS}hashTree")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAppendPubSubToSetupTgBasic:
    """基本 4 步顺序 + 3 个 sampler 出现(per design.md 实际代码示例)."""

    def test_three_jdbc_samplers_appended(self) -> None:
        """3 个 JDBCSampler 被 append 到 setup_tg_element(per design.md line 473/484/506):
        - CreatePublication-{name} (步骤 1)
        - CreateSubscriberDDL (步骤 3, 内含步骤 2 的 CREATE TS DATABASE sub)
        - CreateSubscription-{name} (步骤 4)
        """
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config()
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        assert len(samplers) == 3, (
            f"expected 3 JDBCSamplers (CreatePublication + CreateSubscriberDDL "
            f"+ CreateSubscription), got {len(samplers)}"
        )

    def test_sampler_order(self) -> None:
        """Sampler 顺序固定: CreatePublication → CreateSubscriberDDL → CreateSubscription."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config()
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        names = [s.attrib["testname"] for s in _find_samplers_in_order(setup_tg)]
        assert names == [
            "CreatePublication-pub_iot",
            "CreateSubscriberDDL",
            "CreateSubscription-sub_iot",
        ]


class TestAppendPubSubToSetupTgCreatePublication:
    """步骤 1: CreatePublication sampler."""

    def test_create_publication_query(self) -> None:
        """CreatePublication query 来自 ``build_publication_sql`` (整库模式)."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config(tables=None)  # 整库模式
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        create_pub = samplers[0]
        prop = _find_prop(create_pub, "stringProp", "query")
        assert prop is not None
        assert prop.text == (
            "CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor"
        )

    def test_create_publication_uses_table_mode(self) -> None:
        """CreatePublication query 来自 ``build_publication_sql`` (表级模式)."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config(
            tables=[PublicationTableEntry(name="t_cnc")],
        )
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        create_pub = samplers[0]
        prop = _find_prop(create_pub, "stringProp", "query")
        assert prop.text == (
            "CREATE PUBLICATION pub_iot FOR TABLE iot_monitor.t_cnc"
        )


class TestAppendPubSubToSetupTgCreateSubscriberDDL:
    """步骤 2/3: CreateSubscriberDDL sampler (含 CREATE TS DATABASE sub + CREATE TABLE sub.x).

    Per design.md line 482-487 + F-006: ``; `` 分隔 ``build_subscribe_dest_schemas``
    输出,合并到单 sampler(per 2026-10-12 user 提议:KaiwuDB JDBC driver 支持
    ``;`` 分隔多条 SQL 一次执行)。
    """

    def test_create_subscriber_ddl_contains_create_ts_database_sub(self) -> None:
        """CreateSubscriberDDL query 包含 ``create ts database if not exists <sub_db>``
        (步骤 2 + 3 合并, 实际 DDL 关键字小写 + ``if not exists`` 子句).

        Note: 实际 DDLGenerator 输出**小写** SQL 关键字(``create ts
        database if not exists ...``), 所以断言用小写; 见
        ``build_subscribe_dest_schemas`` IGNORECASE 处理。
        """
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config()
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        ddl = samplers[1]
        prop = _find_prop(ddl, "stringProp", "query")
        assert prop is not None
        assert "create ts database if not exists iot_monitor_sub" in prop.text

    def test_create_subscriber_ddl_uses_sub_db_not_publisher_db(self) -> None:
        """CreateSubscriberDDL query 内部应使用 sub_db (FQN 跨库, per D5)."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config()
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        ddl = samplers[1]
        prop = _find_prop(ddl, "stringProp", "query")
        # 包含 iot_monitor_sub, 不含单独的 iot_monitor (无 . 后缀)
        assert "iot_monitor_sub" in prop.text

    def test_create_subscriber_ddl_semi_colon_joined(self) -> None:
        """CreateSubscriberDDL query 是 ``; `` 分隔的多条 DDL 合并(per F-006).

        ``build_subscribe_dest_schemas`` 输出多条 DDL,本函数用
        ``'; '.join(...)`` 合并到单 query。
        """
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config()
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        ddl = samplers[1]
        prop = _find_prop(ddl, "stringProp", "query")
        # 至少 1 个 `; ` 分隔(实际 DDLGenerator.generate 输出多条)
        assert "; " in prop.text

    def test_sub_db_hardcoded_convention(self) -> None:
        """``sub_db = f"{publisher_db}_sub"`` 内部硬约定 (per D5, 不作为参数)."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config(publisher_db="iot_monitor")
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        ddl = samplers[1]
        prop = _find_prop(ddl, "stringProp", "query")
        assert "iot_monitor_sub" in prop.text


class TestAppendPubSubToSetupTgCreateSubscription:
    """步骤 4: CreateSubscription sampler."""

    def test_create_subscription_query_with_target(self) -> None:
        """CreateSubscription query 来自 ``build_create_subscription_sql``,
        含 conninfo + target option (per F-009 caller 过滤契约)."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config(
            options={"target": '{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}'},
        )
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        sub = samplers[2]
        prop = _find_prop(sub, "stringProp", "query")
        assert prop is not None
        assert "CREATE SUBSCRIPTION sub_iot" in prop.text
        assert "CONNECTION 'postgresql://root@localhost:26257/iot_monitor?sslmode=disable'" in prop.text
        assert "PUBLICATION pub_iot" in prop.text
        assert "WITH OPTIONS" in prop.text
        # target value 整体用单引号包 JSON (per sub-sql.md line 28 + V3.3.0 实测)
        assert "target = '{\"iot_monitor.public.t_cnc\":\"iot_monitor_sub.public.t_cnc\"}'" in prop.text

    def test_create_subscription_caller_filters_options(self) -> None:
        """Caller 过滤契约 (F-009): 7-key options 中只把 subscription-side keys
        传给 ``build_create_subscription_sql``.

        options 含 publication-side key (``buffer_size``) + subscription-side
        key (``target``) → 末尾 query 不应包含 ``buffer_size``(应被 caller 过滤掉)。
        """
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config(
            options={
                "buffer_size": "4",  # publication-side, 应被过滤
                "target": '{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}',  # subscription-side, 保留
            },
        )
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        sub = samplers[2]
        prop = _find_prop(sub, "stringProp", "query")
        # publication-side key 不应在 subscription sampler 的 query 中
        assert "buffer_size" not in prop.text
        # subscription-side key 保留
        assert "target" in prop.text

    def test_create_subscription_passes_target_only(self) -> None:
        """Subscription sampler query 只含 target 4 个 subscription-side keys
        (per tasks.md §3.5.1 ``SUBSCRIPTION_OPTION_KEYS = frozenset({"target",
        "enable", "ignore_history", "retry"})`` 契约)."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config(
            options={
                "target": '{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}',
                "enable": "on",
                "ignore_history": "on",  # per sub-sql.md line 28: on/off
                "retry": "5",  # per sub-sql.md line 28: 数字 0-10 字面
                # publication-side keys (应被过滤):
                "buffer_size": "4",
                "retrieve_tags": "true",
                "publish": "insert",
            },
        )
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        sub = samplers[2]
        prop = _find_prop(sub, "stringProp", "query")
        # 4 个 subscription-side keys 都保留
        assert "target" in prop.text
        assert "enable" in prop.text
        assert "ignore_history" in prop.text
        assert "retry" in prop.text
        # 3 个 publication-side keys 都被过滤
        assert "buffer_size" not in prop.text
        assert "retrieve_tags" not in prop.text
        assert "publish" not in prop.text

    def test_create_subscription_returns_none(self) -> None:
        """``append_pub_sub_to_setup_tg`` 原地修改 setup_tg_element, 返回 ``None``
        (per design.md line 348: 输出 ``None``)."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config()
        result = append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)
        assert result is None

    def test_create_publication_passes_publication_side_options(self) -> None:
        """对称契约: CreatePublication sampler query 包含 publication-side options
        (buffer_size/retrieve_tags/publish), 不含 subscription-side keys."""
        setup_tg = _build_setup_tg()
        test_model = _build_test_model()
        pubsub = _build_pubsub_config(
            options={
                "buffer_size": "4",  # publication-side, 应在 CreatePublication
                "target": '{"iot_monitor.public.t_cnc":"iot_monitor_sub.public.t_cnc"}',  # subscription-side, 不应在
            },
        )
        append_pub_sub_to_setup_tg(setup_tg, pubsub, test_model)

        samplers = _find_samplers_in_order(setup_tg)
        create_pub = samplers[0]
        prop = _find_prop(create_pub, "stringProp", "query")
        # publication-side key 在 CreatePublication query
        assert "buffer_size" in prop.text
        # subscription-side key 不在 CreatePublication query (caller 过滤)
        assert "target" not in prop.text
