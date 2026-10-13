"""Tests for §4 integration: pub_sub elements in the generated JMX.

Per OpenSpec tasks.md §4.1:

- 不声明 ``pub_sub_config`` 段 → SetupTG / VerifyTG 不追加 pub_sub 元素
- 声明 ``pub_sub_config`` 段 → SetupTG 末尾 4 个 JDBC Sampler
  (CreatePublication / CreateTSDatabase / CreateSubscriberDDL /
  CreateSubscription) + VerifyTG (PostThreadGroup + 1 SHOW SUBSCRIPTION
  status sampler + N count samplers)
- XML 结构可通过 ``xml.etree.ElementTree.parse()`` 解析

Note: tasks.md 字面说"集成到 test_plan.py", 但 ``JMXSkeletonGenerator``
类实际在 ``src/jmx_skeleton_generator/generators/skeleton.py`` — 集成
注入点在 ``JMXSkeletonGenerator.generate()`` (Phase A 集成入口).

本测试是 Phase A: 端到端跑 ``JMXSkeletonGenerator.generate()`` + parse
生成的 jmx, **不**需要真实 KaiwuDB cluster(本地 pytest 跑通).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

import pytest

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
    WriteConfig,
)
from jmx_skeleton_generator import JMXSkeletonGenerator


NS = "{http://jmeter.apache.org/}"


def _local(tag: str) -> str:
    """Strip JMeter namespace prefix from a tag name."""
    return tag[len(NS):] if tag.startswith(NS) else tag


def _walk(elements: List[ET.Element]):
    """Recursively yield every Element in a tree (dedup by id)."""

    def _recurse(el):
        seen.add(id(el))
        yield el
        for child in el:
            if id(child) not in seen:
                yield from _recurse(child)

    seen: set[int] = set()
    for el in elements:
        if id(el) not in seen:
            yield from _recurse(el)


def _has_node_with_testname(elements: List[ET.Element], testname: str) -> bool:
    """Return True iff any node in the tree has ``testname="<name>"``."""
    for el in _walk(elements):
        if el.attrib.get("testname") == testname:
            return True
    return False


def _has_query_containing(elements: List[ET.Element], substring: str) -> bool:
    """Return True iff any ``<JDBCSampler>`` query field contains substring."""
    needle = substring.lower()
    for el in _walk(elements):
        if _local(el.tag) != "JDBCSampler":
            continue
        for child in el:
            if _local(child.tag) == "stringProp" and child.get("name") == "query":
                if child.text and needle in child.text.lower():
                    return True
    return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_test_model() -> TestModelConfig:
    """Minimal TestModelConfig: one ts db + one table."""
    table = TsTableConfig(
        name="t_cnc",
        ts_col=TsColConfig(name="ts", type="timestamp", ms_step=1000),
        primary_tag_count=1,
        regular_tag_count=1,
        data_col_count=1,
        primary_tags=[
            PrimaryTagColTypeConfig(col_type="int4", type_proportion=1.0)
        ],
        regular_tags=[
            ColTypeConfig(col_type="int4", type_proportion=1.0)
        ],
        data_cols=[
            ColTypeConfig(col_type="float8", type_proportion=1.0)
        ],
    )
    return TestModelConfig(
        ts_dbs=[TsDbConfig(name="iot_monitor", tables=[table])],
    )


def _build_test_config(
    *, pub_sub_config: PubSubConfig | None = None
) -> TestConfig:
    """Minimal TestConfig: no write_config / no query_config (Phase A
    integration only needs SetupTG + pub_sub setup, not full write pipeline).
    """
    return TestConfig(
        conn_config=ConnConfig(db_url="jdbc:kaiwudb://localhost:26257/defaultdb"),
        write_config=[],
        pub_sub_config=pub_sub_config,
    )


def _build_ddl_statements() -> List[str]:
    """Minimal DDL statements so ``generate_ddl_setup_thread_group``
    returns a non-empty ``[stg, hashTree]`` pair (otherwise the
    pub_sub integration point has no hashTree to append into).
    """
    return [
        "create database iot_monitor",
        "create ts database iot_monitor",
    ]


def _build_generator(
    cfg: TestConfig,
    model: TestModelConfig,
    output_dir: Path,
) -> JMXSkeletonGenerator:
    """Build a JMXSkeletonGenerator with minimal DDL statements."""
    return JMXSkeletonGenerator(
        cfg,
        model=model,
        ddl_statements=_build_ddl_statements(),
        output_dir=str(output_dir),
    )


def _build_pubsub_config() -> PubSubConfig:
    """PubSubConfig matching the test model's ``iot_monitor`` ts_db."""
    return PubSubConfig(
        publisher_db="iot_monitor",
        publication_name="pub_iot",
        subscription_name="sub_iot",
        conninfo="postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
        options={"target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc"},
    )


@pytest.fixture
def tmp_output_dir(tmp_path) -> Path:
    """Empty output dir for JMX file generation."""
    d = tmp_path / "out"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNoPubSubConfig:
    """不声明 ``pub_sub_config`` 段 → jmx 不含 pub_sub elements."""

    def test_no_create_publication_sampler_in_jmx(self, tmp_output_dir) -> None:
        """SetupTG 不含 ``CreatePublication-*`` sampler."""
        cfg = _build_test_config(pub_sub_config=None)
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert not _has_node_with_testname(elements, "CreatePublication-pub_iot")

    def test_no_create_subscription_sampler_in_jmx(self, tmp_output_dir) -> None:
        """SetupTG 不含 ``CreateSubscription-*`` sampler."""
        cfg = _build_test_config(pub_sub_config=None)
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert not _has_node_with_testname(elements, "CreateSubscription-sub_iot")

    def test_no_verify_post_thread_group_in_jmx(self, tmp_output_dir) -> None:
        """jmx 不含 ``VerifyTearDownTG-PubSub-*`` PostThreadGroup."""
        cfg = _build_test_config(pub_sub_config=None)
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert not _has_node_with_testname(elements, "VerifyTearDownTG-PubSub-sub_iot")


class TestWithPubSubConfig:
    """声明 ``pub_sub_config`` 段 → jmx 含 pub_sub elements."""

    def test_create_publication_sampler_in_setup_tg(self, tmp_output_dir) -> None:
        """SetupTG 末尾含 ``CreatePublication-pub_iot`` sampler."""
        cfg = _build_test_config(pub_sub_config=_build_pubsub_config())
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert _has_node_with_testname(elements, "CreatePublication-pub_iot")

    def test_create_subscriber_ddl_sampler_in_setup_tg(self, tmp_output_dir) -> None:
        """SetupTG 末尾含 ``CreateSubscriberDDL`` sampler (per F-006)."""
        cfg = _build_test_config(pub_sub_config=_build_pubsub_config())
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert _has_node_with_testname(elements, "CreateSubscriberDDL")

    def test_create_subscription_sampler_in_setup_tg(self, tmp_output_dir) -> None:
        """SetupTG 末尾含 ``CreateSubscription-sub_iot`` sampler."""
        cfg = _build_test_config(pub_sub_config=_build_pubsub_config())
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert _has_node_with_testname(elements, "CreateSubscription-sub_iot")

    def test_setup_tg_sub_ddl_contains_sub_db(self, tmp_output_dir) -> None:
        """CreateSubscriberDDL sampler query 包含 sub_db (``create ts database if not exists iot_monitor_sub``)."""
        cfg = _build_test_config(pub_sub_config=_build_pubsub_config())
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        # Phase A: 仅测 sub_db 派生; FQN 跨库查 (count(*)) 由 §3.6 测试覆盖
        assert _has_query_containing(elements, "create ts database if not exists iot_monitor_sub")

    def test_create_subscription_uses_target_option(self, tmp_output_dir) -> None:
        """CreateSubscription sampler query 包含 target option (F-009 caller 过滤契约)."""
        cfg = _build_test_config(pub_sub_config=_build_pubsub_config())
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert _has_query_containing(elements, "with options (target =")

    def test_verify_post_thread_group_present(self, tmp_output_dir) -> None:
        """jmx 含 ``VerifyTearDownTG-PubSub-sub_iot`` PostThreadGroup."""
        cfg = _build_test_config(pub_sub_config=_build_pubsub_config())
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert _has_node_with_testname(elements, "VerifyTearDownTG-PubSub-sub_iot")

    def test_verify_tg_has_show_subscription_status_sampler(self, tmp_output_dir) -> None:
        """VerifyTG 含 ``ShowSubscription-sub_iot`` sampler."""
        cfg = _build_test_config(pub_sub_config=_build_pubsub_config())
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert _has_node_with_testname(elements, "ShowSubscription-sub_iot")

    def test_verify_tg_has_count_sampler_per_table(self, tmp_output_dir) -> None:
        """VerifyTG 含 N 个 count sampler (每张 ts_table 一条, 1 张表 → 1 个).

        sampler testname 形如 ``CountRows-<sub_db>-<table>``.
        """
        cfg = _build_test_config(pub_sub_config=_build_pubsub_config())
        _build_generator(cfg, _build_test_model(), tmp_output_dir).generate()
        tree = ET.parse(str(tmp_output_dir / "test_plan.jmx"))
        elements = list(tree.getroot())
        assert _has_node_with_testname(
            elements, "CountRows-iot_monitor_sub-t_cnc"
        )
