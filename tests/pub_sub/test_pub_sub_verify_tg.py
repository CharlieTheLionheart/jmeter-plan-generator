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

from pub_sub.pub_sub_verify_tg import (
    _build_count_sampler,
    _build_show_subscription_status_sampler,
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
        assert prop.text == "SHOW SUBSCRIPTION sub_iot"

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
        assert prop.text == "SHOW SUBSCRIPTION sub_custom_42"


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
