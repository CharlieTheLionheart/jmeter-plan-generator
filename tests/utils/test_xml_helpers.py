"""Tests for ``utils.xml_helpers`` — 3 pub-sub helpers (OpenSpec §2).

Per ``docs/refs/jmx-components-references.md`` 实测 jmx schema:

- §PostThreadGroup: ``testclass=PostThreadGroup`` / ``guiclass=PostThreadGroupGui`` /
  ``ThreadGroup.duration`` 字段**不输出** (JMeter 5.6.3 默认行为,TG 跑完
  sampler 列表自然结束);Verify TG 典型用法 ``delay=60s`` 等主 TG 结束后
  让 CDC 同步完成
- §RegexExtractor: 字段顺序 ``useHeaders → refname → regex → template → default
  → default_empty_value → match_number``
- §JSR223Assertion: 字段顺序 ``cacheKey → filename → parameters → script →
  scriptLanguage``;``guiclass=TestBeanGUI``;字段名 ``script`` **而非**
  ``assertion_script`` (这是实测 jmx 的关键差异点)

The three helpers (``teardown_thread_group_element`` /
``regex_extractor_element`` / ``jsr223_assertion_element``) are the
pub-sub-only additions; the existing 20+ helpers in ``xml_helpers.py``
(``setup_thread_group_element`` / ``jdbc_sampler_element`` / …) keep
their pre-existing tests elsewhere or are unittested via the
JMX-generation integration tests in ``tests/jmx_skeleton_generator``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from utils.xml_helpers import (
    jsr223_assertion_element,
    regex_extractor_element,
    string_prop,
    teardown_thread_group_element,
)


# ---------------------------------------------------------------------------
# Namespace-aware helpers
# ---------------------------------------------------------------------------
#
# ``utils.xml_helpers._q(tag)`` qualifies every local tag name with the
# JMeter namespace ``{http://jmeter.apache.org/}`` (per
# ``docs/refs/jmeter-testplan-reference.md`` — JMeter JMX files always
# emit the namespace prefix on every element). Direct ``.find("./intProp")``
# XPath therefore fails because the children are named
# ``{http://jmeter.apache.org/}intProp``. Use the helpers below to
# compare by **local** tag name + ``name`` attribute.

NS = "{http://jmeter.apache.org/}"


def _local(tag: str) -> str:
    """Strip the JMeter namespace prefix from a tag name."""
    return tag[len(NS):] if tag.startswith(NS) else tag


def _find_prop(
    elem: ET.Element, tag: str, name: str
) -> ET.Element | None:
    """Find a direct child by local tag + ``name`` attribute."""
    for child in elem:
        if _local(child.tag) == tag and child.get("name") == name:
            return child
    return None


def _find_element_prop(elem: ET.Element, name: str) -> ET.Element | None:
    """Find a direct child ``<elementProp>`` by its ``name`` attribute."""
    return _find_prop(elem, "elementProp", name)


# ===========================================================================
# teardown_thread_group_element — PostThreadGroup (tearDown ThreadGroup)
# ===========================================================================

class TestTeardownThreadGroupElement:
    """``<PostThreadGroup>`` element renderer (JMeter tearDown TG).

    Per docs §PostThreadGroup: ``testclass=PostThreadGroup`` /
    ``guiclass=PostThreadGroupGui``, no ``ThreadGroup.duration`` field
    (PostThreadGroup 关键差异段: JMeter 5.6.3 默认不写, TG 跑完 sampler
    列表后自然结束), Verify TG 典型用法 ``delay=60s``.
    """

    def _build_default(self, **overrides) -> ET.Element:
        """Build a default PostThreadGroup, returning just the TG element
        (the paired hashTree is discarded — tests focus on TG content).

        To test the paired hashTree behaviour (e.g. children propagation),
        use ``teardown_thread_group_element(...)`` directly and unpack
        the tuple.
        """
        tg, _ = teardown_thread_group_element("VerifyTearDownTG", **overrides)
        return tg

    def test_testclass_and_guiclass(self) -> None:
        """``testclass='PostThreadGroup'`` / ``guiclass='PostThreadGroupGui'``
        (per docs §PostThreadGroup 关键属性表, 实测 jmx)."""
        elem = self._build_default()
        assert _local(elem.tag) == "PostThreadGroup"
        assert elem.attrib["testclass"] == "PostThreadGroup"
        assert elem.attrib["guiclass"] == "PostThreadGroupGui"

    def test_testname_passed_through(self) -> None:
        """``name`` arg maps to the Element's ``testname`` attribute."""
        tg, _ = teardown_thread_group_element("MyVerifyTG")
        assert tg.attrib["testname"] == "MyVerifyTG"

    def test_num_threads_default_one(self) -> None:
        """Default ``num_threads=1``."""
        elem = self._build_default()
        prop = _find_prop(elem, "intProp", "ThreadGroup.num_threads")
        assert prop is not None
        assert prop.text == "1"

    def test_ramp_time_default_one(self) -> None:
        """Default ``ramp_time=1``."""
        elem = self._build_default()
        prop = _find_prop(elem, "intProp", "ThreadGroup.ramp_time")
        assert prop is not None
        assert prop.text == "1"

    def test_delay_default_60(self) -> None:
        """Default ``delay=60`` (Verify TG 典型用法: 主 TG 结束后等 60s
        让 CDC 同步完成)."""
        elem = self._build_default()
        prop = _find_prop(elem, "longProp", "ThreadGroup.delay")
        assert prop is not None
        assert prop.text == "60"

    def test_scheduler_true(self) -> None:
        """``ThreadGroup.scheduler=true`` (must pair with ``delay`` so
        the scheduler actually waits)."""
        elem = self._build_default()
        prop = _find_prop(elem, "boolProp", "ThreadGroup.scheduler")
        assert prop is not None
        assert prop.text == "true"

    def test_same_user_on_next_iteration_true(self) -> None:
        """``ThreadGroup.same_user_on_next_iteration=true`` (matches
        SetupThreadGroup 实测 jmx 设定)."""
        elem = self._build_default()
        prop = _find_prop(
            elem, "boolProp", "ThreadGroup.same_user_on_next_iteration"
        )
        assert prop is not None
        assert prop.text == "true"

    def test_on_sample_error_continue(self) -> None:
        """``ThreadGroup.on_sample_error=continue``."""
        elem = self._build_default()
        prop = _find_prop(
            elem, "stringProp", "ThreadGroup.on_sample_error"
        )
        assert prop is not None
        assert prop.text == "continue"

    def test_loop_controller_loops_default_one(self) -> None:
        """``LoopController.loops=1`` by default (Verify TG 只跑一轮)."""
        elem = self._build_default()
        ctrl = _find_element_prop(elem, "ThreadGroup.main_controller")
        assert ctrl is not None
        assert ctrl.attrib["elementType"] == "LoopController"
        assert ctrl.attrib["guiclass"] == "LoopControlPanel"
        assert ctrl.attrib["testclass"] == "LoopController"
        loops = _find_prop(ctrl, "stringProp", "LoopController.loops")
        assert loops is not None
        assert loops.text == "1"

    def test_loop_controller_continue_forever_false(self) -> None:
        """``LoopController.continue_forever=false``."""
        elem = self._build_default()
        ctrl = _find_element_prop(elem, "ThreadGroup.main_controller")
        prop = _find_prop(ctrl, "boolProp", "LoopController.continue_forever")
        assert prop is not None
        assert prop.text == "false"

    def test_duration_NOT_emitted(self) -> None:
        """``ThreadGroup.duration`` MUST NOT be emitted under any tag
        (per docs §PostThreadGroup 关键差异段: JMeter 5.6.3 默认不写
        ``<longProp name='ThreadGroup.duration'>``, TG 跑完 sampler
        列表后自然结束)."""
        elem = self._build_default()
        for tag in ("intProp", "longProp", "stringProp"):
            assert _find_prop(elem, tag, "ThreadGroup.duration") is None, (
                f"unexpected {tag} for ThreadGroup.duration"
            )

    def test_custom_num_threads(self) -> None:
        """``num_threads`` kwarg overrides the default 1."""
        tg, _ = teardown_thread_group_element("X", num_threads=4)
        prop = _find_prop(tg, "intProp", "ThreadGroup.num_threads")
        assert prop.text == "4"

    def test_custom_delay(self) -> None:
        """``delay`` kwarg overrides the default 60."""
        tg, _ = teardown_thread_group_element("X", delay=10)
        prop = _find_prop(tg, "longProp", "ThreadGroup.delay")
        assert prop.text == "10"

    def test_custom_loops(self) -> None:
        """``loops`` kwarg maps to ``LoopController.loops``."""
        tg, _ = teardown_thread_group_element("X", loops=3)
        ctrl = _find_element_prop(tg, "ThreadGroup.main_controller")
        loops = _find_prop(ctrl, "stringProp", "LoopController.loops")
        assert loops.text == "3"

    def test_returns_element(self) -> None:
        """Return type is ``xml.etree.ElementTree.Element`` (not a
        tuple, not None, not bytes)."""
        elem = self._build_default()
        assert isinstance(elem, ET.Element)
        assert _local(elem.tag) == "PostThreadGroup"

    def test_returns_pair_of_tg_and_hashtree(self) -> None:
        """New API returns ``(tg, hashTree)`` tuple — paired JMeter schema
        (per A 决定, 对齐 ``setup_thread_group_element`` paired-hashTree 模式).
        """
        tg, tg_hash = teardown_thread_group_element("X")
        assert _local(tg.tag) == "PostThreadGroup"
        assert _local(tg_hash.tag) == "hashTree"
        # 默认空 hashTree (children=None)
        assert len(list(tg_hash)) == 0

    def test_children_kwarg_lands_in_paired_hashtree(self) -> None:
        """``children`` kwarg 传入的 sampler 列表出现在 paired ``<hashTree>`` 内部."""
        # 用一个最简单的 sampler-like child (mock):
        # 实际生产中 caller 传 jdbc_sampler_element 等 helper 产物
        mock_sampler = ET.Element(
            f"{NS}JDBCSampler",
            attrib={"testname": "MyMockSampler"}
        )
        tg, tg_hash = teardown_thread_group_element(
            "X", children=[mock_sampler]
        )
        # TG 元素本身不应含 children (它们在 hashTree 里)
        tg_children = [_local(c.tag) for c in tg]
        assert "JDBCSampler" not in tg_children
        # hashTree 含传入的 children
        children = list(tg_hash)
        assert len(children) == 1
        assert _local(children[0].tag) == "JDBCSampler"
        assert children[0].attrib["testname"] == "MyMockSampler"

    def test_enabled_default_true(self) -> None:
        """``enabled=True`` (默认) → TG 属性 ``enabled="true"``."""
        tg, _ = teardown_thread_group_element("X")
        assert tg.attrib["enabled"] == "true"

    def test_enabled_false(self) -> None:
        """``enabled=False`` → TG 属性 ``enabled="false"`` (临时禁用 TG)."""
        tg, _ = teardown_thread_group_element("X", enabled=False)
        assert tg.attrib["enabled"] == "false"

    def test_duration_when_passed_emits_longprop(self) -> None:
        """``duration`` kwarg 显式传 → 输出 ``<stringProp name="ThreadGroup.duration">``
        (覆盖默认不输出行为, 给未来场景用).
        """
        tg, _ = teardown_thread_group_element("X", duration="300")
        prop = _find_prop(tg, "stringProp", "ThreadGroup.duration")
        assert prop is not None
        assert prop.text == "300"

    def test_scheduler_false(self) -> None:
        """``scheduler=False`` → ``ThreadGroup.scheduler="false"`` (不启用调度器).

        Per docs §PostThreadGroup: 即使 scheduler=false, PostThreadGroup 仍
        在主 TG 完成后跑(tearDown 行为不依赖 scheduler); 但 caller
        仍可显式关掉 scheduler 用于不需要等待的场景.
        """
        tg, _ = teardown_thread_group_element("X", scheduler=False)
        prop = _find_prop(tg, "boolProp", "ThreadGroup.scheduler")
        assert prop.text == "false"

    def test_on_sample_error_override(self) -> None:
        """``on_sample_error`` kwarg 覆盖默认 ``"continue"`` (e.g. ``"stopthread"``)."""
        tg, _ = teardown_thread_group_element("X", on_sample_error="stopthread")
        prop = _find_prop(tg, "stringProp", "ThreadGroup.on_sample_error")
        assert prop.text == "stopthread"

    def test_same_user_on_next_iteration_false(self) -> None:
        """``same_user_on_next_iteration=False`` → ``boolProp="false"``."""
        tg, _ = teardown_thread_group_element("X", same_user_on_next_iteration=False)
        prop = _find_prop(
            tg, "boolProp", "ThreadGroup.same_user_on_next_iteration"
        )
        assert prop.text == "false"

    def test_props_kwarg_appends_extra_props(self) -> None:
        """``props`` kwarg 传入额外 stringProp / boolProp 直接 append 到 TG 元素内
        (跟 ``setup_thread_group_element`` 对齐的扩展点)."""
        extra = string_prop("MyCustom.field", "custom_value")
        tg, _ = teardown_thread_group_element("X", props=[extra])
        prop = _find_prop(tg, "stringProp", "MyCustom.field")
        assert prop is not None
        assert prop.text == "custom_value"


# ===========================================================================
# regex_extractor_element
# ===========================================================================

class TestRegexExtractorElement:
    """``<RegexExtractor>`` element renderer (JMeter Post Processor)."""

    def _build_default(self, **overrides) -> ET.Element:
        return regex_extractor_element(
            "sub_status",
            r"status\s*\|\s*(\w+)",
            "$1$",
            "1",
            **overrides,
        )

    def test_testclass_and_guiclass(self) -> None:
        """``testclass='RegexExtractor'`` / ``guiclass='RegexExtractorGui'``."""
        elem = self._build_default()
        assert _local(elem.tag) == "RegexExtractor"
        assert elem.attrib["testclass"] == "RegexExtractor"
        assert elem.attrib["guiclass"] == "RegexExtractorGui"

    def test_testname_is_ref_name(self) -> None:
        """``testname`` equals ``ref_name`` so the var name shows in the
        JMeter GUI tree (per JMeter GUI 实测 jmx
        ``~/Downloads/JSR223 Assertion.jmx:36``)."""
        elem = regex_extractor_element("my_var", r"x", "$1$", "1")
        assert elem.attrib["testname"] == "my_var"

    def test_use_headers_default_false(self) -> None:
        """``useHeaders='false'`` (default: parse response body, not headers)."""
        elem = self._build_default()
        prop = _find_prop(elem, "stringProp", "RegexExtractor.useHeaders")
        assert prop is not None
        assert prop.text == "false"

    def test_default_empty_value_false(self) -> None:
        """``default_empty_value='false'`` (unmatched returns the ``default``
        value, NOT an empty string; this is the JMeter default per docs
        §RegexExtractor 关键属性表)."""
        elem = self._build_default()
        prop = _find_prop(
            elem, "boolProp", "RegexExtractor.default_empty_value"
        )
        assert prop is not None
        assert prop.text == "false"

    def test_required_fields_present(self) -> None:
        """All 7 documented fields MUST be present (per docs
        §RegexExtractor 关键属性表). Field order is not asserted
        (JMeter parses by name, not by position — over-specifying order
        would break valid implementations that use a different internal
        insertion order).

        The required set is the union of:
        - ``RegexExtractor.useHeaders`` (stringProp)
        - ``RegexExtractor.refname`` (stringProp)
        - ``RegexExtractor.regex`` (stringProp)
        - ``RegexExtractor.template`` (stringProp)
        - ``RegexExtractor.default`` (stringProp)
        - ``RegexExtractor.default_empty_value`` (boolProp)
        - ``RegexExtractor.match_number`` (stringProp)
        """
        elem = self._build_default()
        names_with_tag = {
            (_local(child.tag), child.get("name")) for child in elem
        }
        expected = {
            ("stringProp", "RegexExtractor.useHeaders"),
            ("stringProp", "RegexExtractor.refname"),
            ("stringProp", "RegexExtractor.regex"),
            ("stringProp", "RegexExtractor.template"),
            ("stringProp", "RegexExtractor.default"),
            ("boolProp", "RegexExtractor.default_empty_value"),
            ("stringProp", "RegexExtractor.match_number"),
        }
        assert names_with_tag == expected

    def test_refname_passed_through(self) -> None:
        """``ref_name`` maps to ``RegexExtractor.refname``."""
        elem = regex_extractor_element("my_var", r"x", "$1$", "1")
        prop = _find_prop(elem, "stringProp", "RegexExtractor.refname")
        assert prop.text == "my_var"

    def test_regex_passed_through(self) -> None:
        """``regex`` arg maps to ``RegexExtractor.regex``."""
        elem = regex_extractor_element("v", r"\d+", "$1$", "1")
        prop = _find_prop(elem, "stringProp", "RegexExtractor.regex")
        assert prop.text == r"\d+"

    def test_template_passed_through(self) -> None:
        """``template`` arg maps to ``RegexExtractor.template``."""
        elem = regex_extractor_element("v", r"x", "$0$", "1")
        prop = _find_prop(elem, "stringProp", "RegexExtractor.template")
        assert prop.text == "$0$"

    def test_default_passed_through(self) -> None:
        """``default`` kwarg maps to ``RegexExtractor.default``."""
        elem = regex_extractor_element(
            "v", r"x", "$1$", "1", default="NOT_FOUND"
        )
        prop = _find_prop(elem, "stringProp", "RegexExtractor.default")
        assert prop.text == "NOT_FOUND"

    def test_default_kwarg_default_empty_string(self) -> None:
        """``default=''`` (empty string) when not passed."""
        elem = self._build_default()
        prop = _find_prop(elem, "stringProp", "RegexExtractor.default")
        assert prop.text == ""

    def test_match_number_passed_through(self) -> None:
        """``match_number`` arg maps to ``RegexExtractor.match_number``
        (as a string, since the field is ``<stringProp>`` per docs)."""
        elem = regex_extractor_element("v", r"x", "$1$", "-1")
        prop = _find_prop(elem, "stringProp", "RegexExtractor.match_number")
        assert prop.text == "-1"


# ===========================================================================
# jsr223_assertion_element
# ===========================================================================

class TestJsr223AssertionElement:
    """``<JSR223Assertion>`` element renderer (JMeter post-sampler script)."""

    def _build_default(self, **overrides) -> ET.Element:
        return jsr223_assertion_element(
            "def s = vars.get('sub_status')\n"
            "assert s != null && s.contains('running') : 'subscription not running'\n",
            **overrides,
        )

    def test_testclass_and_guiclass(self) -> None:
        """``testclass='JSR223Assertion'`` / ``guiclass='TestBeanGUI'``
        (per docs §JSR223Assertion 实测 jmx — 注意 ``guiclass`` 是
        ``TestBeanGUI`` 不是 ``JSR223AssertionGui``)."""
        elem = self._build_default()
        assert _local(elem.tag) == "JSR223Assertion"
        assert elem.attrib["testclass"] == "JSR223Assertion"
        assert elem.attrib["guiclass"] == "TestBeanGUI"

    def test_cache_key_true(self) -> None:
        """``cacheKey='true'`` (Groovy script compilation cache enabled,
        per docs §JSR223Assertion 关键属性)."""
        elem = self._build_default()
        prop = _find_prop(elem, "stringProp", "cacheKey")
        assert prop is not None
        assert prop.text == "true"

    def test_filename_empty(self) -> None:
        """``filename=''`` (default: inline script, no external file)."""
        elem = self._build_default()
        prop = _find_prop(elem, "stringProp", "filename")
        assert prop is not None
        assert prop.text == ""

    def test_parameters_empty(self) -> None:
        """``parameters=''`` (no external parameters passed to the script)."""
        elem = self._build_default()
        prop = _find_prop(elem, "stringProp", "parameters")
        assert prop is not None
        assert prop.text == ""

    def test_field_name_is_script_not_assertion_script(self) -> None:
        """字段名是 ``script`` (NOT ``assertion_script`` — 这是实测 jmx
        的关键差异点, docs §JSR223Assertion 关键属性明确用 ``script``).
        """
        elem = self._build_default()
        prop = _find_prop(elem, "stringProp", "script")
        assert prop is not None
        # The WRONG name must be absent.
        assert _find_prop(elem, "stringProp", "assertion_script") is None

    def test_script_passed_through(self) -> None:
        """``script`` arg maps to ``<stringProp name='script'>``."""
        elem = jsr223_assertion_element("def x = 1")
        prop = _find_prop(elem, "stringProp", "script")
        assert prop.text == "def x = 1"

    def test_script_language_default_groovy(self) -> None:
        """``scriptLanguage='groovy'`` by default (per docs §JSR223Assertion
        示例, Groovy 是 pub-sub 断言的事实标准选择)."""
        elem = self._build_default()
        prop = _find_prop(elem, "stringProp", "scriptLanguage")
        assert prop is not None
        assert prop.text == "groovy"

    def test_script_language_override(self) -> None:
        """``script_language`` kwarg overrides the default 'groovy'."""
        elem = jsr223_assertion_element("var x = 1", script_language="javascript")
        prop = _find_prop(elem, "stringProp", "scriptLanguage")
        assert prop.text == "javascript"

    def test_required_fields_present(self) -> None:
        """All 5 documented fields MUST be present (per docs
        §JSR223Assertion 关键属性表). Field order is not asserted
        (JMeter parses by name, not by position — over-specifying order
        would break valid implementations that use a different internal
        insertion order).

        The required set is the union of:
        - ``cacheKey`` (stringProp)
        - ``filename`` (stringProp)
        - ``parameters`` (stringProp)
        - ``script`` (stringProp, NOT ``assertion_script`` — a key
          attribute name that 实测 jmx uses; see
          ``test_field_name_is_script_not_assertion_script`` for the
          negative case)
        - ``scriptLanguage`` (stringProp)
        """
        elem = self._build_default()
        names_with_tag = {
            (_local(child.tag), child.get("name")) for child in elem
        }
        expected = {
            ("stringProp", "cacheKey"),
            ("stringProp", "filename"),
            ("stringProp", "parameters"),
            ("stringProp", "script"),
            ("stringProp", "scriptLanguage"),
        }
        assert names_with_tag == expected
