"""针对 ``rest_query_groups.generate_rest_query_thread_group`` 的单元测试。

OpenSpec §4（task-4-brief.md）4 个 case (a)-(d)：

  (a) 每个 measurement 生成 1 个 Query sampler 单元
  (b) HTTPSamplerProxy path = rest_api.query_url_path（默认 ``/restapi/query``），
      headers 必含 ``Authorization: Basic ${__property(rest_token)}``
  (c) JSR223Assertion script 必含 ``vars.get('rows')`` 与 ``>= <expected_rows>``
      烘焙值；JSONPostProcessor ``jsonPathExprs`` = ``$.rows``，
      ``referenceNames`` = ``rows``
  (d) ``rest_api.pre_create_tables=false`` 时 Query TG 仍生成；
      断言不读 ``primary_tag``（不出现 ``primary_tag`` 字符串引用）

参考资料：
  - docs/refs/jmx-components-references.md §HTTPSamplerProxy + §JSONPostProcessor
  - utils/xml_helpers.http_request_sampler_element（§1 已交付）
  - throughput_control.generate_query_timer（既有，按字面 float throughput）
  - jmx_skeleton_generator.generators.ddl_setup._build_jsr223_assertion_element
        （§2 已交付，§4 直接复用其模式但走独立私有脚本）
"""

from __future__ import annotations

from typing import Any, Dict, List
from xml.etree import ElementTree as ET

import pytest

from config_parser.models import (
    ColTypeConfig,
    PrimaryTagColTypeConfig,
    TestModelConfig,
    TsDbConfig,
    TsTableConfig,
)
from jmx_skeleton_generator.generators.rest_query_groups import (
    generate_rest_query_thread_group,
)


NS = "http://jmeter.apache.org/"


# ---------------------------------------------------------------------------
# XML helpers（mirror pattern from test_ddl_setup_http_thread_group.py）
# ---------------------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _walk(elements):
    def _recurse(el):
        seen.add(id(el))
        yield el
        for child in el:
            if id(child) not in seen:
                yield from _recurse(child)

    seen: set = set()
    for el in elements:
        yield from _recurse(el)


def _prop_map(elem: ET.Element) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for child in elem:
        if _local(child.tag) in ("stringProp", "boolProp", "intProp", "longProp"):
            out[child.get("name")] = child.text or ""
    return out


def _collect_by_tag(elements, tag_name: str) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == tag_name]


def _collect_http_samplers(elements) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == "HTTPSamplerProxy"]


def _collect_jsr223_assertions(elements) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == "JSR223Assertion"]


def _collect_json_extractors(elements) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == "JSONPostProcessor"]


def _collect_thread_groups(elements) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == "ThreadGroup"]


def _collect_timers(elements) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == "ConstantThroughputTimer"]


def _sampler_body_text(sampler: ET.Element) -> str:
    """从 HTTPSamplerProxy 的 Arguments.HTTPArgument.Argument.value 提取 body 文本。"""
    for ep in sampler.iter():
        if _local(ep.tag) == "stringProp" and ep.get("name") == "Argument.value":
            return ep.text or ""
    return ""


def _paired_hash_tree(elements, sampler: ET.Element):
    """返回紧跟在 sampler 之后的配对 ``<hashTree>``（sibling 查找）。

    JMeter 5.x：post-processor / assertion 必须作为 sampler 配对 hashTree
    的子节点存在（与 HeaderManager 同一约定），才会在该 sampler 执行后运行。
    """
    for parent in _walk(elements):
        children = list(parent)
        if sampler in children:
            idx = children.index(sampler)
            if idx + 1 < len(children):
                return children[idx + 1]
            return None
    return None


def _header_pairs(elements, sampler: ET.Element) -> Dict[str, str]:
    """提取一个 HTTPSamplerProxy 的 HeaderManager 头键值对（sibling 查找）。"""
    pairs: Dict[str, str] = {}
    for parent in _walk(elements):
        children = list(parent)
        if sampler in children:
            idx = children.index(sampler)
            if idx + 1 >= len(children):
                return pairs
            paired_hash_tree = children[idx + 1]
            for ep in paired_hash_tree.iter():
                if _local(ep.tag) == "elementProp" and ep.get("elementType") == "Header":
                    name = value = None
                    for sp in ep:
                        if sp.get("name") == "Header.name":
                            name = sp.text
                        elif sp.get("name") == "Header.value":
                            value = sp.text
                    if name is not None:
                        pairs[name] = value
            return pairs
    return pairs


# ---------------------------------------------------------------------------
# Fixtures: minimal TestModelConfig + TsTableConfig + rest_api_config
# ---------------------------------------------------------------------------

def _make_ptag(
    col_type: str = "varchar(64)", val_range: str = '"device_{1}"',
) -> PrimaryTagColTypeConfig:
    return PrimaryTagColTypeConfig(col_type=col_type, type_proportion=1.0, val_range=val_range)


def _make_rtag(
    col_type: str = "varchar(64)", val_range: str = '"Beijing"',
) -> ColTypeConfig:
    return ColTypeConfig(
        col_type=col_type, type_proportion=1.0, val_range=val_range,
        seed_num=1, nullable=False,
    )


def _make_data_col(
    col_type: str = "float4", val_range: str = "0..100", seed_num: int = 100,
) -> ColTypeConfig:
    return ColTypeConfig(
        col_type=col_type, type_proportion=1.0, val_range=val_range,
        seed_num=seed_num, nullable=False,
    )


def _make_table(
    name: str,
    ptag: PrimaryTagColTypeConfig,
    rtag: ColTypeConfig,
    data_col: ColTypeConfig,
) -> TsTableConfig:
    return TsTableConfig(
        name=name,
        data_col_count=1,
        data_cols=[data_col],
        primary_tag_count=1,
        primary_tags=[ptag],
        regular_tag_count=1,
        regular_tags=[rtag],
    )


def _default_rest_api(**overrides: Any) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "query_url_path": "/restapi/query",
        "https_mode": "tls",
        "ca_cert_path": "/etc/kaiwudb/certs/ca.crt",
        "pre_create_tables": True,
    }
    cfg.update(overrides)
    return cfg


def _single_table_model() -> TestModelConfig:
    table = _make_table(
        name="meters",
        ptag=_make_ptag(),
        rtag=_make_rtag(),
        data_col=_make_data_col(),
    )
    return TestModelConfig(
        ts_dbs=[TsDbConfig(name="db_iot", tables=[table])],
    )


def _multi_table_model() -> TestModelConfig:
    t1 = _make_table(
        name="meters",
        ptag=_make_ptag(),
        rtag=_make_rtag(),
        data_col=_make_data_col(),
    )
    t2 = _make_table(
        name="voltage",
        ptag=_make_ptag(val_range='"sensor_{1}"'),
        rtag=_make_rtag(val_range='"Shanghai"'),
        data_col=_make_data_col(val_range="200..240"),
    )
    return TestModelConfig(
        ts_dbs=[TsDbConfig(name="db_iot", tables=[t1, t2])],
    )


# ---------------------------------------------------------------------------
# (a) 每个 measurement → 1 个 Query sampler 单元
# ---------------------------------------------------------------------------

def test_each_measurement_emits_one_query_sampler_unit():
    """N measurements → N 个 ThreadGroup，每个 TG 内含恰好 1 个 HTTPSamplerProxy +
    1 个 JSONPostProcessor + 1 个 JSR223Assertion + 1 个 ConstantThroughputTimer。
    """
    elems = generate_rest_query_thread_group(
        _multi_table_model(),
        rest_api_config=_default_rest_api(),
        expected_rows=10,
    )

    tg_list = _collect_thread_groups(elems)
    assert len(tg_list) == 2, f"expected 2 ThreadGroups (one per measurement), got {len(tg_list)}"

    samplers = _collect_http_samplers(elems)
    extractors = _collect_json_extractors(elems)
    assertions = _collect_jsr223_assertions(elems)
    timers = _collect_timers(elems)
    assert len(samplers) == 2, f"expected 2 HTTPSamplerProxy, got {len(samplers)}"
    assert len(extractors) == 2, f"expected 2 JSONPostProcessor, got {len(extractors)}"
    assert len(assertions) == 2, f"expected 2 JSR223Assertion, got {len(assertions)}"
    assert len(timers) == 2, f"expected 2 ConstantThroughputTimer, got {len(timers)}"

    # Sampler 必须是 POST
    for sampler in samplers:
        assert _prop_map(sampler)["HTTPSampler.method"] == "POST"

    # Sampler testnames 必须按 measurement 区分（不可重名）
    testnames = [s.get("testname") for s in samplers]
    assert len(set(testnames)) == 2, f"samplers must have unique testnames, got {testnames}"

    # JMeter 5.x：JSONPostProcessor + JSR223Assertion 必须挂在每个
    # HTTPSamplerProxy 的配对 hashTree 内（否则 JMeter 当作 TG 级兄弟忽略，
    # 既不抽取 rows 也不跑断言）。仅数元素总数不足以捕获此结构错误。
    for tg_idx, sampler in enumerate(samplers):
        paired = _paired_hash_tree(elems, sampler)
        assert paired is not None, (
            f"TG[{tg_idx}] HTTPSamplerProxy must have a paired hashTree sibling"
        )
        children_tags = [_local(c.tag) for c in paired]
        assert "JSONPostProcessor" in children_tags, (
            f"TG[{tg_idx}] HTTPSamplerProxy's paired hashTree must contain "
            f"JSONPostProcessor as a child; got {children_tags}"
        )
        assert "JSR223Assertion" in children_tags, (
            f"TG[{tg_idx}] HTTPSamplerProxy's paired hashTree must contain "
            f"JSR223Assertion as a child; got {children_tags}"
        )


# ---------------------------------------------------------------------------
# (b) HTTPSamplerProxy path = rest_api.query_url_path；headers 含 Authorization
# ---------------------------------------------------------------------------

def test_path_and_authorization_header_correct():
    """HTTPSamplerProxy ``path`` 必须等于 ``rest_api.query_url_path``（默认 ``/restapi/query``）；
    headers 必须包含 ``Authorization: Basic ${__property(rest_token)}`` 与 ``Content-Type: text/plain``。
    """
    # 默认 path = /restapi/query
    elems_default = generate_rest_query_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
    )
    samplers = _collect_http_samplers(elems_default)
    assert len(samplers) == 1
    sampler = samplers[0]
    assert _prop_map(sampler)["HTTPSampler.path"] == "/restapi/query", (
        f"default HTTPSampler.path must be '/restapi/query', got {_prop_map(sampler)['HTTPSampler.path']!r}"
    )

    headers = _header_pairs(elems_default, sampler)
    assert headers.get("Authorization") == "Basic ${__property(rest_token)}", (
        f"Authorization header must be 'Basic ${{__property(rest_token)}}', got {headers.get('Authorization')!r}"
    )
    assert headers.get("Content-Type") == "text/plain", (
        f"Content-Type header must be 'text/plain', got {headers.get('Content-Type')!r}"
    )

    # 自定义 query_url_path 必须按字面写入
    elems_custom = generate_rest_query_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(query_url_path="/api/v2/query"),
    )
    custom_sampler = _collect_http_samplers(elems_custom)[0]
    assert _prop_map(custom_sampler)["HTTPSampler.path"] == "/api/v2/query", (
        f"custom query_url_path must be written verbatim, got {_prop_map(custom_sampler)['HTTPSampler.path']!r}"
    )

    # Sampler body 必须精确等于 db-qualified count(*) 语句（不留末尾条件、带分号）
    body = _sampler_body_text(sampler)
    assert body == "select count(*) from db_iot.meters;", (
        f"body must equal 'select count(*) from db_iot.meters;', got {body!r}"
    )


# ---------------------------------------------------------------------------
# (c) rows 字段断言正确
# ---------------------------------------------------------------------------

def test_data_field_assertion_correct():
    """JSR223Assertion script 必含 ``vars.get('data')`` + ``.size() >= <expected_rows>`` 烘焙值
    （expected_rows 锁为字面 int，默认 1）；JSONPostProcessor ``jsonPathExprs`` = ``$.data``，
    ``referenceNames`` = ``data``。

    §6.4.2 锁 L：B3 修复后取代原 ``$.rows`` 形式（rows 是列数假阳性）。
    """
    elems = generate_rest_query_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        expected_rows=42,
    )

    # JSONPostProcessor
    extractors = _collect_json_extractors(elems)
    assert len(extractors) == 1, f"expected 1 JSONPostProcessor, got {len(extractors)}"
    ext_props = _prop_map(extractors[0])
    assert ext_props.get("JSONPostProcessor.referenceNames") == "data", (
        f"JSONPostProcessor.referenceNames must be 'data', got {ext_props.get('JSONPostProcessor.referenceNames')!r}"
    )
    assert ext_props.get("JSONPostProcessor.jsonPathExprs") == "$.data", (
        f"JSONPostProcessor.jsonPathExprs must be '$.data', got {ext_props.get('JSONPostProcessor.jsonPathExprs')!r}"
    )

    # JSR223Assertion
    assertions = _collect_jsr223_assertions(elems)
    assert len(assertions) == 1, f"expected 1 JSR223Assertion, got {len(assertions)}"
    script = _prop_map(assertions[0])["script"]
    assert "vars.get('data')" in script, (
        f"JSR223Assertion script must call vars.get('rows'), got script={script!r}"
    )
    # 锁 expected_rows 烘焙值：必须出现字面 ``>= 42``，不可只放变量引用
    assert ">= 42" in script, (
        f"JSR223Assertion script must contain literal '>= 42' (expected_rows baked), got script={script!r}"
    )
    # 锁额外保障：expected_rows 必须是 int 字面量；不接受 `${...}` 包裹
    assert "${expected_rows" not in script, (
        f"JSR223Assertion script must NOT leave expected_rows as ${{...}} variable, got script={script!r}"
    )

    # 默认 expected_rows=1：再次验证
    elems_default = generate_rest_query_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
    )
    default_script = _prop_map(_collect_jsr223_assertions(elems_default)[0])["script"]
    assert ">= 1" in default_script, (
        f"default expected_rows=1 must bake into '>= 1', got script={default_script!r}"
    )


# ---------------------------------------------------------------------------
# (d) pre_create_tables=false 时 Query TG 仍可用，但断言不读 primary_tag
# ---------------------------------------------------------------------------

def test_pre_create_tables_false_still_works_but_no_primary_tag():
    """即使 ``rest_api.pre_create_tables=false``（SetupTG 不预建表），Query TG 仍生成；
    JSR223Assertion 脚本与 JSONPostProcessor 配置中均不出现 ``primary_tag`` 字符串引用。
    """
    elems = generate_rest_query_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(pre_create_tables=False),
    )

    # Query TG 仍生成（不被 pre_create_tables 跳过）
    tg_list = _collect_thread_groups(elems)
    assert len(tg_list) == 1, (
        f"Query TG must still emit when pre_create_tables=false, got {len(tg_list)} TG(s)"
    )
    samplers = _collect_http_samplers(elems)
    extractors = _collect_json_extractors(elems)
    assertions = _collect_jsr223_assertions(elems)
    assert len(samplers) == 1
    assert len(extractors) == 1
    assert len(assertions) == 1

    # 序列化整个 TG → XML，断言不出现 primary_tag 字符串
    xml = "".join(ET.tostring(e, encoding="unicode") for e in elems)
    assert "primary_tag" not in xml, (
        f"Query TG must NOT reference 'primary_tag' anywhere in XML, got xml snippet:\n"
        f"{xml[:1000]}"
    )

    # 进一步收紧：JSR223Assertion 脚本 + JSONPostProcessor 配置单独检查
    script = _prop_map(assertions[0])["script"]
    assert "primary_tag" not in script, (
        f"JSR223Assertion script must NOT reference 'primary_tag', got script={script!r}"
    )
    ext_props = _prop_map(extractors[0])
    for prop_name, prop_value in ext_props.items():
        assert "primary_tag" not in prop_value, (
            f"JSONPostProcessor prop {prop_name} must NOT contain 'primary_tag', got {prop_value!r}"
        )


# ---------------------------------------------------------------------------
# Bug-fix smoke 回归：HTTPSampler 必须含 ``__P(rest_api.*,default)`` 带默认值
# ---------------------------------------------------------------------------


def test_http_samplers_domain_and_port_have_property_defaults():
    """``HTTPSampler.domain`` / ``HTTPSampler.port`` 必须用 ``${__P(rest_api.*,DEFAULT)}``
    形式 — 缺默认值时 JMeter 在没有 -Jrest_api.* 时回退到 ``"1"``，触发连接超时。"""
    elems = generate_rest_query_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
    )
    for sampler in _collect_http_samplers(elems):
        props = _prop_map(sampler)
        assert props.get("HTTPSampler.domain") == "${__P(rest_api.hostname,127.0.0.1)}", (
            f"HTTPSampler.domain 必须有默认值 127.0.0.1, "
            f"got {props.get('HTTPSampler.domain')!r}"
        )
        assert props.get("HTTPSampler.port") == "${__P(rest_api.http_port,8080)}", (
            f"HTTPSampler.port 必须有默认值 8080, "
            f"got {props.get('HTTPSampler.port')!r}"
        )


# ---------------------------------------------------------------------------
# B3 修复：Query assertion 必须检 ``$.data`` 数组长度（非 ``$.rows`` 列数）
#
# 背景：smoke v14 实跑（curl 验证）：
#   {"code":0,"column_meta":[["count","INT8",8]],"data":[["0"]],"rows":1}
# 关键：``rows`` 是**列数**（= column_meta.length），不是数据行数。
# 原 assertion 检 ``vars.get('rows').toInteger() >= expected_rows`` 永远
# = 1（列数恒为 1），不验证实际数据存在，掩盖 query 真失败（表不存在返
# code:-1 但 rows 字段也被 JSONExtractor 处理成 null/0 → NumberFormatException
# 掩盖成 assertion 错误而非 query 错误）。
#
# 修复（§6.4.2 锁 L）：JSONPostProcessor 改抽 ``$.data``（实际行数组），
# JSR223Assertion 检 ``vars.get('data')`` 不为 null 且 ``.length >= expected_rows``。
# ---------------------------------------------------------------------------


def test_query_assertion_extracts_data_not_rows_field():
    """Query JSONPostProcessor 必须抽 ``$.data``（实际数据行数组），**禁止**
    抽 ``$.rows``（那是列数不是数据行数，会假阳性）。

    §6.4.2 锁 L：B3 修复根因——``rows`` 是 KaiwuDB server 返的**列数**
    （= column_meta.length），非数据行数。``select count(*)`` 永远 rows=1
    （1 列），不验证表里真有数据。
    """
    elems = generate_rest_query_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
    )

    extractors = _collect_json_extractors(elems)
    assert len(extractors) == 1, f"expected 1 JSONPostProcessor, got {len(extractors)}"
    ext_props = _prop_map(extractors[0])
    # 必须抽 $.data
    assert ext_props.get("JSONPostProcessor.jsonPathExprs") == "$.data", (
        f"JSONPostProcessor.jsonPathExprs must be '$.data' (B3 fix), "
        f"got {ext_props.get('JSONPostProcessor.jsonPathExprs')!r}"
    )
    assert ext_props.get("JSONPostProcessor.referenceNames") == "data", (
        f"JSONPostProcessor.referenceNames must be 'data', "
        f"got {ext_props.get('JSONPostProcessor.referenceNames')!r}"
    )
    # 反例：不再抽 $.rows
    assert ext_props.get("JSONPostProcessor.jsonPathExprs") != "$.rows", (
        "B3: 禁止抽 $.rows（那是列数非数据行数，假阳性）"
    )


def test_query_assertion_checks_data_length_not_rows_toInteger():
    """Query JSR223Assertion 必须检 ``vars.get('data').length >= expected_rows``，
    **禁止**用 ``vars.get('rows').toInteger()``（rows 是列数 1，恒等通过）。
    """
    elems = generate_rest_query_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        expected_rows=42,
    )

    assertions = _collect_jsr223_assertions(elems)
    assert len(assertions) == 1, f"expected 1 JSR223Assertion, got {len(assertions)}"
    script = _prop_map(assertions[0])["script"]

    # 必须含 vars.get('data') + length >= expected
    assert "vars.get('data')" in script, (
        f"assertion 必须取 vars.get('data')（B3 锁 L）, got:\n{script}"
    )
    # 期望烘焙 expected_rows=42
    assert "42" in script, (
        f"assertion 必须烘焙 expected_rows=42, got:\n{script}"
    )
    # 反例：不再用 vars.get('rows').toInteger()
    assert "vars.get('rows').toInteger()" not in script, (
        f"B3: 禁止 vars.get('rows').toInteger()（rows 是列数 1，假阳性）, "
        f"got:\n{script}"
    )