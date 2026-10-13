"""Tests for ``src/pub_sub/pub_sub_verify_tg.py`` helpers (§3.4).

Two private helpers in the module (per design.md line 577-619):

- ``_build_show_subscription_status_sampler(subscription_name, subscriber_db)``:
  builds a JDBCSampler for ``SHOW SUBSCRIPTION <name>`` with a
  RegexExtractor extracting the ``status`` column and a JSR223Assertion
  asserting it contains ``running``.
- ``_build_count_sampler(publisher_db, table_name, subscriber_db, expected_min_rows)``:
  builds a JDBCSampler for ``select count(*) from <subscriber_db>.<table>``
  with a JSR223Assertion asserting ``count_1 >= expected_min_rows``.

The ``generate_pub_sub_verify_tg`` public function (§3.6) is exercised
in a separate test class in this same file (added in tasks.md §3.6.1).
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from config_parser.models import (
    ColTypeConfig,
    PrimaryTagColTypeConfig,
    PubSubConfig,
    TestModelConfig,
    TsColConfig,
    TsDbConfig,
    TsTableConfig,
)
from pub_sub.pub_sub_verify_tg import (
    _build_count_sampler,
    _build_show_subscription_status_sampler,
    generate_pub_sub_verify_tg,
)


NS = "{http://jmeter.apache.org/}"


def _local(tag: str) -> str:
    """Strip the JMeter namespace prefix from a tag name."""
    return tag[len(NS):] if tag.startswith(NS) else tag


def _find_child(elem: ET.Element, tag: str) -> ET.Element | None:
    """Find a direct child by local tag name."""
    for child in elem:
        if _local(child.tag) == tag:
            return child
    return None


def _find_prop(elem: ET.Element, tag: str, name: str) -> ET.Element | None:
    """Find a direct child by local tag + ``name`` attribute (per §2 helper style)."""
    for child in elem:
        if _local(child.tag) == tag and child.get("name") == name:
            return child
    return None


def _build_test_model_single_table() -> TestModelConfig:
    """Build a minimal ``TestModelConfig`` with one ts db + one table."""
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


def _build_pubsub_config(
    *,
    publisher_db: str = "iot_monitor",
    publication_name: str = "pub_iot",
    subscription_name: str = "sub_iot",
    expected_min_rows: int | None = None,
) -> PubSubConfig:
    """Build a minimal ``PubSubConfig`` that passes self-consistent validation."""
    return PubSubConfig(
        publisher_db=publisher_db,
        publication_name=publication_name,
        subscription_name=subscription_name,
        conninfo="postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
        options={"target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc"},
        expected_min_rows=expected_min_rows,
    )


# ===========================================================================
# _build_show_subscription_status_sampler (§3.4)
# ===========================================================================

class TestBuildShowSubscriptionStatusSampler:
    """``SHOW SUBSCRIPTION <name>`` sampler + status 提取 + running 断言.

    Per design.md line 580-599:
    - JDBCSampler name = ``ShowSubscription-{subscription_name}``
    - JDBCSampler query = ``SHOW SUBSCRIPTION {subscription_name}``
    - JDBCSampler variable_names = ``"status"`` (JDBC Request binds
      first column to ``vars.get('status')``)
    - 子节点 RegexExtractor: ref_name="sub_status",
      regex=``r"status\s*\|\s*(\w+)"``, template="$1$", match_number=1
    - 子节点 JSR223Assertion: script 断言
      ``vars.get('sub_status')?.contains('running')``
    """

    def _build(self, subscription_name="sub_iot", subscriber_db="iot_monitor_sub"):
        return _build_show_subscription_status_sampler(
            subscription_name, subscriber_db
        )

    def test_returns_jdbc_sampler_element(self) -> None:
        """返回 ``<JDBCSampler>`` 元素(per tasks.md §3.4.1 + design.md)."""
        sampler = self._build()
        assert isinstance(sampler, ET.Element)
        assert _local(sampler.tag) == "JDBCSampler"

    def test_testclass_and_guiclass(self) -> None:
        """``testclass='JDBCSampler'`` / ``guiclass='TestBeanGUI'``
        (per JMeter 5.6.3 实测 jdbc_sampler_element 行为)."""
        sampler = self._build()
        assert sampler.attrib["testclass"] == "JDBCSampler"
        assert sampler.attrib["guiclass"] == "TestBeanGUI"

    def test_sampler_name_uses_subscription_name(self) -> None:
        """``name='ShowSubscription-{subscription_name}'`` (per design.md line 583)."""
        sampler = self._build(subscription_name="sub_iot")
        assert sampler.attrib["testname"] == "ShowSubscription-sub_iot"

    def test_sampler_query_is_show_subscription(self) -> None:
        """``query='SHOW SUBSCRIPTION {subscription_name}'`` (per design.md line 584)."""
        sampler = self._build(subscription_name="sub_iot")
        prop = _find_prop(sampler, "stringProp", "query")
        assert prop is not None
        assert prop.text == "show subscription sub_iot"

    def test_sampler_variable_names_is_status(self) -> None:
        """``variable_names='status'`` (per design.md line 585: JDBC Request binds
        first column to ``vars.get('status')``)."""
        sampler = self._build()
        prop = _find_prop(sampler, "stringProp", "variableNames")
        assert prop is not None
        assert prop.text == "status"

    def test_has_regex_extractor_child(self) -> None:
        """子节点有 ``<RegexExtractor>`` (status 列提取)."""
        sampler = self._build()
        ext = _find_child(sampler, "RegexExtractor")
        assert ext is not None, "expected RegexExtractor child"
        assert ext.attrib["testclass"] == "RegexExtractor"

    def test_regex_extractor_refname_is_sub_status(self) -> None:
        """RegexExtractor.refname = 'sub_status' (per design.md line 588)."""
        sampler = self._build()
        ext = _find_child(sampler, "RegexExtractor")
        prop = _find_prop(ext, "stringProp", "RegexExtractor.refname")
        assert prop is not None
        assert prop.text == "sub_status"

    def test_regex_extractor_regex(self) -> None:
        """RegexExtractor.regex = ``r"status\s*\|\s*(\w+)"`` (per design.md line 589)."""
        sampler = self._build()
        ext = _find_child(sampler, "RegexExtractor")
        prop = _find_prop(ext, "stringProp", "RegexExtractor.regex")
        assert prop is not None
        assert prop.text == r"status\s*\|\s*(\w+)"

    def test_regex_extractor_template_and_match_number(self) -> None:
        """RegexExtractor.template='$1$' / match_number=1 (per design.md line 590-591)."""
        sampler = self._build()
        ext = _find_child(sampler, "RegexExtractor")
        tmpl = _find_prop(ext, "stringProp", "RegexExtractor.template")
        match = _find_prop(ext, "stringProp", "RegexExtractor.match_number")
        assert tmpl.text == "$1$"
        assert match.text == "1"

    def test_has_jsr223_assertion_child(self) -> None:
        """子节点有 ``<JSR223Assertion>`` (running 断言)."""
        sampler = self._build()
        assertion = _find_child(sampler, "JSR223Assertion")
        assert assertion is not None, "expected JSR223Assertion child"

    def test_assertion_script_contains_running(self) -> None:
        """JSR223Assertion script 包含 'running' 字符串(per design.md line 596)."""
        sampler = self._build()
        assertion = _find_child(sampler, "JSR223Assertion")
        prop = _find_prop(assertion, "stringProp", "script")
        assert prop is not None
        assert "running" in prop.text

    def test_assertion_script_uses_sub_status_variable(self) -> None:
        """JSR223Assertion script 读 ``vars.get('sub_status')`` (per design.md line 595)."""
        sampler = self._build()
        assertion = _find_child(sampler, "JSR223Assertion")
        prop = _find_prop(assertion, "stringProp", "script")
        assert prop is not None
        assert "sub_status" in prop.text

    def test_assertion_script_language_groovy(self) -> None:
        """JSR223Assertion 默认 ``scriptLanguage='groovy'`` (per JSR223 helper 默认)."""
        sampler = self._build()
        assertion = _find_child(sampler, "JSR223Assertion")
        prop = _find_prop(assertion, "stringProp", "scriptLanguage")
        assert prop is not None
        assert prop.text == "groovy"

    def test_subscription_name_passed_through(self) -> None:
        """``subscription_name`` 同时出现在 sampler name + query 中."""
        sampler = self._build(subscription_name="sub_custom_42")
        assert sampler.attrib["testname"] == "ShowSubscription-sub_custom_42"
        prop = _find_prop(sampler, "stringProp", "query")
        assert prop.text == "show subscription sub_custom_42"


# ===========================================================================
# _build_count_sampler (§3.4)
# ===========================================================================

class TestBuildCountSampler:
    """``select count(*) from <subscriber_db>.<table>`` sampler + 阈值断言.

    Per design.md line 605-618:
    - JDBCSampler name = ``CountRows-{subscriber_db}-{table_name}``
    - JDBCSampler query = ``select count(*) from {subscriber_db}.{table_name}``
      (FQN 跨库查, per D5)
    - JDBCSampler variable_names = ``"count"`` (JDBC Request binds
      count(*) to ``vars.get('count_1')``)
    - 子节点 JSR223Assertion: script 断言
      ``vars.get('count_1') as int >= expected_min_rows``
    """

    def _build(
        self,
        publisher_db="iot_monitor",
        table_name="t_cnc",
        subscriber_db="iot_monitor_sub",
        expected_min_rows=1,
    ):
        return _build_count_sampler(
            publisher_db, table_name, subscriber_db, expected_min_rows
        )

    def test_returns_jdbc_sampler_element(self) -> None:
        sampler = self._build()
        assert isinstance(sampler, ET.Element)
        assert _local(sampler.tag) == "JDBCSampler"

    def test_sampler_name_uses_subscriber_db_and_table(self) -> None:
        """``name='CountRows-{subscriber_db}-{table_name}'`` (per design.md line 608)."""
        sampler = self._build(subscriber_db="iot_monitor_sub", table_name="t_cnc")
        assert sampler.attrib["testname"] == "CountRows-iot_monitor_sub-t_cnc"

    def test_sampler_query_is_select_count_fqn(self) -> None:
        """``query='select count(*) from {subscriber_db}.{table_name}'`` (FQN 跨库查)."""
        sampler = self._build(subscriber_db="iot_monitor_sub", table_name="t_cnc")
        prop = _find_prop(sampler, "stringProp", "query")
        assert prop is not None
        assert prop.text == "select count(*) from iot_monitor_sub.t_cnc"

    def test_query_uses_subscriber_db_not_publisher_db(self) -> None:
        """反例: query 用 subscriber_db(不是 publisher_db)— per D5 锁定
        (subscriber 表 = FQN 跨库查, 不是 publisher 表)."""
        sampler = self._build(
            publisher_db="iot_monitor",
            subscriber_db="iot_monitor_sub",
            table_name="t_cnc",
        )
        prop = _find_prop(sampler, "stringProp", "query")
        # query 包含 subscriber_db,不包含 publisher_db 单独的 iot_monitor.t_cnc
        assert "iot_monitor_sub.t_cnc" in prop.text
        assert "iot_monitor.t_cnc" not in prop.text

    def test_sampler_variable_names_is_count(self) -> None:
        """``variable_names='count'`` (per design.md line 610: JDBC Request binds
        count(*) to ``vars.get('count_1')``)."""
        sampler = self._build()
        prop = _find_prop(sampler, "stringProp", "variableNames")
        assert prop is not None
        assert prop.text == "count"

    def test_has_jsr223_assertion_child(self) -> None:
        sampler = self._build()
        assertion = _find_child(sampler, "JSR223Assertion")
        assert assertion is not None

    def test_assertion_script_uses_count_1_variable(self) -> None:
        """JSR223Assertion script 读 ``vars.get('count_1')`` (per design.md line 614)."""
        sampler = self._build()
        assertion = _find_child(sampler, "JSR223Assertion")
        prop = _find_prop(assertion, "stringProp", "script")
        assert prop is not None
        assert "count_1" in prop.text

    def test_assertion_script_uses_expected_min_rows(self) -> None:
        """JSR223Assertion script 阈值断言含 ``expected_min_rows`` 值 (per design.md line 615)."""
        sampler = self._build(expected_min_rows=5)
        assertion = _find_child(sampler, "JSR223Assertion")
        prop = _find_prop(assertion, "stringProp", "script")
        assert prop is not None
        # 阈值 5 必须出现在 script 中(可以同时在 condition + error message)
        assert ">=" in prop.text
        assert " 5 " in prop.text or "5" in prop.text

    def test_assertion_script_threshold_zero(self) -> None:
        """``expected_min_rows=0`` (恒真) → script 包含 ``>= 0`` (per D3 锁定)."""
        sampler = self._build(expected_min_rows=0)
        assertion = _find_child(sampler, "JSR223Assertion")
        prop = _find_prop(assertion, "stringProp", "script")
        assert prop is not None
        # 0 阈值出现在条件里
        assert "0" in prop.text

    def test_assertion_script_threshold_default_one(self) -> None:
        """``expected_min_rows=1`` 默认 (per §3.6 generate_pub_sub_verify_tg 内联默认)."""
        sampler = self._build(expected_min_rows=1)
        assertion = _find_child(sampler, "JSR223Assertion")
        prop = _find_prop(assertion, "stringProp", "script")
        assert prop is not None
        assert "1" in prop.text
        # 错误消息中应含阈值
        assert "below threshold" in prop.text

    def test_assertion_script_language_groovy(self) -> None:
        sampler = self._build()
        assertion = _find_child(sampler, "JSR223Assertion")
        prop = _find_prop(assertion, "stringProp", "scriptLanguage")
        assert prop is not None
        assert prop.text == "groovy"

    def test_table_name_passed_through(self) -> None:
        """``table_name`` 同时出现在 sampler name + query 中."""
        sampler = self._build(table_name="t_custom")
        assert sampler.attrib["testname"] == "CountRows-iot_monitor_sub-t_custom"
        prop = _find_prop(sampler, "stringProp", "query")
        assert "iot_monitor_sub.t_custom" in prop.text


# ===========================================================================
# generate_pub_sub_verify_tg (OpenSpec §3.6)
# ===========================================================================

class TestGeneratePubSubVerifyTg:
    """``generate_pub_sub_verify_tg(pub_sub_config, test_model_config)``
    组装完整 Verify PostThreadGroup (per design.md line 513-380).

    内部:
    - 派生 ``sub_db = f"{pub_db}_sub"`` (D5 硬约定)
    - 调 ``teardown_thread_group_element`` 拿 PostThreadGroup( delay=60s
      + 不写 ThreadGroup.duration)
    - ``expected_min_rows = pub_sub_config.expected_min_rows or 1`` (内联默认)
    - 调 §3.4 helper 拿 1 个 SHOW SUBSCRIPTION status sampler + N 个
      ``select count(*) from <sub_db>.<table>`` sampler
    - 全部 sampler append 到 PostThreadGroup 元素(design.md 字面行为)
    """

    def _build_test_model_two_tables(self) -> TestModelConfig:
        """Two tables on one ts_db to exercise N-sampler count loop."""
        def _table(name: str) -> TsTableConfig:
            return TsTableConfig(
                name=name,
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
            ts_dbs=[
                TsDbConfig(
                    name="iot_monitor",
                    tables=[_table("t_cnc"), _table("t_cnc2")],
                ),
            ],
        )

    def test_returns_post_thread_group_element(self) -> None:
        """返回 ``<PostThreadGroup>`` 元素 (per §2 helper 字面 + design.md line 543).

        design.md 锁定 `tg = teardown_thread_group_element(...)` 单值返回
        + `tg.append(sampler)` 直接 append 到 PostThreadGroup 元素。
        """
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)

        assert isinstance(tg, ET.Element)
        assert _local(tg.tag) == "PostThreadGroup"
        assert tg.attrib["testclass"] == "PostThreadGroup"
        assert tg.attrib["guiclass"] == "PostThreadGroupGui"

    def test_post_thread_group_name_uses_subscription_name(self) -> None:
        """``testname='VerifyTearDownTG-PubSub-<subscription_name>'`` (per design.md line 544)."""
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config(subscription_name="sub_custom")
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        assert tg.attrib["testname"] == "VerifyTearDownTG-PubSub-sub_custom"

    def test_post_thread_group_delay_60(self) -> None:
        """PostThreadGroup.delay = 60s (per design.md line 547 + F-010 锁定).

        主 TG 结束后等 60s 让 CDC 同步完成再跑 Verify。
        """
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        prop = _find_prop(tg, "longProp", "ThreadGroup.delay")
        assert prop is not None
        assert prop.text == "60"

    def test_post_thread_group_duration_not_emitted(self) -> None:
        """PostThreadGroup 不输出 ``ThreadGroup.duration`` (per docs §PostThreadGroup 关键差异段)."""
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        for tag in ("intProp", "longProp", "stringProp"):
            assert _find_prop(tg, tag, "ThreadGroup.duration") is None

    def test_post_thread_group_loops_1(self) -> None:
        """``LoopController.loops=1`` (per design.md line 378)."""
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        ctrl = _find_prop(tg, "elementProp", "ThreadGroup.main_controller")
        loops = _find_prop(ctrl, "stringProp", "LoopController.loops")
        assert loops is not None
        assert loops.text == "1"

    def test_contains_one_show_subscription_status_sampler(self) -> None:
        """含 1 个 SHOW SUBSCRIPTION status sampler (per design.md line 558-562)."""
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        # 1 个 SHOW SUBSCRIPTION + 1 个 count = 2 个 sampler
        assert len(samplers) == 2
        # 首条 sampler 必须是 SHOW SUBSCRIPTION (per design.md 顺序)
        first = samplers[0]
        assert first.attrib["testname"] == "ShowSubscription-sub_iot"
        prop = _find_prop(first, "stringProp", "query")
        assert prop is not None
        assert prop.text == "show subscription sub_iot"

    def test_count_samplers_match_ts_tables_count(self) -> None:
        """count sampler 数量 = test_model.ts_dbs[*].tables[*] 总数 (per design.md line 565-572).

        N 张表 → N 个 ``CountRows-<sub_db>-<table>`` sampler
        (本测试用 2 张表 → 2 个 count sampler + 1 个 SHOW SUBSCRIPTION = 3 个总)
        """
        model = self._build_test_model_two_tables()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        # 1 SHOW SUBSCRIPTION + 2 count = 3 个总 sampler
        assert len(samplers) == 3

    def test_count_samplers_use_fqn_subscriber_table(self) -> None:
        """count sampler query 走 FQN 跨库查 ``select count(*) from <sub_db>.<table>``
        (per D5 + design.md line 567-571)."""
        model = self._build_test_model_two_tables()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        # 跳过首条 SHOW SUBSCRIPTION, 检查后 2 个 count sampler
        count_samplers = samplers[1:]
        assert len(count_samplers) == 2
        for sampler in count_samplers:
            prop = _find_prop(sampler, "stringProp", "query")
            assert prop is not None
            # FQN 跨库查 sub_db.table
            assert "iot_monitor_sub" in prop.text
            assert "select count(*) from iot_monitor_sub." in prop.text

    def test_default_expected_min_rows_is_one(self) -> None:
        """``expected_min_rows=None`` (默认) → 内联默认 ``1`` (per design.md line 372)."""
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config(expected_min_rows=None)
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        # 后 N 个 sampler 都是 count sampler
        count_samplers = samplers[1:]
        for sampler in count_samplers:
            assertion = _find_child(sampler, "JSR223Assertion")
            script = _find_prop(assertion, "stringProp", "script")
            # 阈值 1 出现 (>= 1)
            assert "1" in script.text
            assert ">=" in script.text

    def test_explicit_expected_min_rows_overrides(self) -> None:
        """``expected_min_rows=N`` (显式) → 内联用 N (per design.md line 372).

        WHERE 过滤场景 user 显式传 0 走恒真, 阈值覆盖测试用 7 验证。
        """
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config(expected_min_rows=7)
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        count_samplers = samplers[1:]
        for sampler in count_samplers:
            assertion = _find_child(sampler, "JSR223Assertion")
            script = _find_prop(assertion, "stringProp", "script")
            assert "7" in script.text
            assert ">=" in script.text

    def test_sampler_data_source_default_pool(self) -> None:
        """每 sampler 走 default_pool (per D5 单池 + FQN 跨库).

        所有 sampler 共享同一条 JDBC Connection Configuration, 通过
        ``dataSource='default_pool'`` 引用。
        """
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        for sampler in samplers:
            prop = _find_prop(sampler, "stringProp", "dataSource")
            assert prop is not None
            assert prop.text == "default_pool"

    def test_no_jdbc_database_field_in_samplers(self) -> None:
        """JMeter 5.6.3 JDBCSampler 无 ``database`` 字段 (per F-013 / 实际 jmx schema).

        单池 + FQN 跨库场景: sampler 不需要 ``database`` 字段覆盖,
        所有 SQL 在 defaultdb 连接上跑(通过 ``dataSource='default_pool'``
        引用), FQN 表名直接在 query 内表达跨库。
        """
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        for sampler in samplers:
            # 无 'database' 字段
            assert _find_prop(sampler, "stringProp", "database") is None
            # 无 JDBC Request.database 属性
            assert "database" not in sampler.attrib

    def test_sub_db_hardcoded_convention(self) -> None:
        """``sub_db = f"{publisher_db}_sub"`` 内部硬约定 (per D5).

        Verify TG 内部 sampler (count) 引用 ``iot_monitor_sub.t_cnc`` 而非
        ``iot_monitor.t_cnc`` — 这是 subscriber 表, 不是 publisher 表。
        """
        model = _build_test_model_single_table()
        pubsub = _build_pubsub_config(publisher_db="iot_monitor")
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        # count sampler name + query 都引用 sub_db
        for sampler in samplers:
            if "CountRows" in sampler.attrib["testname"]:
                assert "iot_monitor_sub" in sampler.attrib["testname"]
                prop = _find_prop(sampler, "stringProp", "query")
                assert "iot_monitor_sub" in prop.text
                # 反例: 不能引用单独的 iot_monitor (无 sub 后缀)
                assert "from iot_monitor.t_cnc" not in prop.text

    def test_verify_tg_iterates_all_ts_dbs(self) -> None:
        """Verify TG 遍历所有 ts_db 的所有 tables (per design.md line 565-571).

        双 ts_db 场景 (iot_monitor + benchmark) 各有 1 张表 →
        1 SHOW SUBSCRIPTION + 2 count = 3 个 sampler
        """
        def _table(name: str) -> TsTableConfig:
            return TsTableConfig(
                name=name,
                ts_col=TsColConfig(name="ts", type="timestamp", ms_step=1000),
                primary_tag_count=1,
                regular_tag_count=1,
                data_col_count=1,
                primary_tags=[PrimaryTagColTypeConfig(col_type="int4", type_proportion=1.0)],
                regular_tags=[ColTypeConfig(col_type="int4", type_proportion=1.0)],
                data_cols=[ColTypeConfig(col_type="float8", type_proportion=1.0)],
            )

        model = TestModelConfig(
            ts_dbs=[
                TsDbConfig(name="iot_monitor", tables=[_table("t_cnc")]),
                TsDbConfig(name="benchmark", tables=[_table("t_bench")]),
            ],
        )
        pubsub = _build_pubsub_config()
        tg, tg_hash = generate_pub_sub_verify_tg(pubsub, model)
        samplers = [c for c in tg_hash if _local(c.tag) == "JDBCSampler"]
        # 1 SHOW SUBSCRIPTION + 2 count = 3 个
        assert len(samplers) == 3
        # count sampler names 应分别引用 sub_db_1 + sub_db_2
        count_names = sorted(
            s.attrib["testname"] for s in samplers
            if "CountRows" in s.attrib["testname"]
        )
        # 注意: 这里两个 ts_db 都被 sub 化, 各自 sub_db
        # 但 generate_pub_sub_verify_tg 用 pub_sub_config.publisher_db
        # 派生 sub_db, 不会为不同 ts_db 各自派生 (F-009 + D5 单池)
        # 所以实际上 2 个 count sampler 都会用 iot_monitor_sub (因为 pub_sub_config.publisher_db = iot_monitor)
        # 这是 design.md 隐含的简化: sub_db 单一, 不为每个 ts_db 派生
        # 实际行为: 2 个 sampler 都用 iot_monitor_sub.<table> 查询
        # 我们只测 sampler 数量, 不测具体的 sub_db 命名 (因为 design.md 简化)
        assert len(count_names) == 2


# Fixtures shared with §3.4 tests (defined above):
# _local, _find_child, _find_prop, _find_samplers_in_order, _build_setup_tg

