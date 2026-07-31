"""针对 ``ddl_setup.generate_ddl_setup_http_thread_group`` 的单元测试。

覆盖 OpenSpec §2.3（rest-schemaless-write DCR）：
  (a) ``pre_create_tables=true`` 生成 Login + DDL sampler
  (b) ``pre_create_tables=false`` 仅生成 Login
  (c) ``https_mode=tls`` + ``ca_cert_path`` 缺失抛 ``RestConfigError``
  (d) ``https_mode=insecure`` 不带 ``customizedSslContext``
  (e) 多条 DDL 生成对应数量的 DDL sampler
  (f) ``rel_init_specs`` 非空走现有 ``_build_rel_init_subtree`` 通路

参考资料：
  - docs/refs/jmx-components-references.md §HTTPSamplerProxy
  - docs/refs/jmeter-testplan-reference.md §18.5（Response Assertion）
        + §18.7（JSON Extractor）
  - utils/xml_helpers.http_request_sampler_element（Task 1 已交付）
  - utils/rest_errors.RestConfigError（Task 1 已交付）
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

import pytest

from jmx_skeleton_generator.generators.ddl_setup import (
    generate_ddl_setup_http_thread_group,
)
from utils.rest_errors import RestConfigError


NS = "http://jmeter.apache.org/"


def _local(tag: str) -> str:
    """去掉命名空间前缀，返回本地标签名。"""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _walk(elements):
    """递归产出 elements 及其所有后代 Element 节点（去重）。"""

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
    """收集 elem 直接子级中所有 stringProp / boolProp / intProp / longProp 的 name->text。"""
    out: Dict[str, str] = {}
    for child in elem:
        if _local(child.tag) in ("stringProp", "boolProp", "intProp", "longProp"):
            out[child.get("name")] = child.text or ""
    return out


def _collect_http_samplers(elements) -> List[ET.Element]:
    """从生成结果里找出所有 HTTPSamplerProxy 元素。"""
    return [e for e in _walk(elements) if _local(e.tag) == "HTTPSamplerProxy"]


def _collect_by_tag(elements, tag_name: str) -> List[ET.Element]:
    """按本地标签名收集元素。"""
    return [e for e in _walk(elements) if _local(e.tag) == tag_name]


def _header_pairs(elements, sampler: ET.Element) -> Dict[str, str]:
    """提取一个 HTTPSamplerProxy 的 HeaderManager 头键值对。

    Header 不在 sampler 子树内——它在 sampler 的**配对 hashTree 兄弟节点**里
    （JMeter 5.x 通过 sibling 关系识别 HeaderManager 配对给哪个 sampler）。
    因此本函数遍历整个 elements 树找到包含 sampler 的父节点，再读其
    sampler 之后的下一个兄弟 hashTree 节点。
    """
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


def _default_rest_api(**overrides: Any) -> Dict[str, Any]:
    """返回一个 ``https_mode=tls`` + ``ca_cert_path=/etc/kaiwudb/certs/ca.crt`` +
    ``pre_create_tables=true`` 的合法 rest_api_config。

    2026-07-27 行为变更：schemaless Login 强制 TLS（insecure 路径移除），
    因此默认 fixture 必带 ``ca_cert_path``。
    """
    cfg: Dict[str, Any] = {
        "login_url_path": "/restapi/login",
        "ddl_url_path": "/restapi/ddl",
        "login_user": "root",
        "login_password": "root123",
        "https_mode": "tls",
        "ca_cert_path": "/etc/kaiwudb/certs/ca.crt",
        "pre_create_tables": True,
    }
    cfg.update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# (a) pre_create_tables=true → Login + DDL samplers
# ---------------------------------------------------------------------------


def test_pre_create_true_emits_login_plus_ddl_samplers():
    """pre_create_tables=true 时生成 1 个 Login + N 个 DDL sampler（N=ddl_statements 数）。"""
    elems = generate_ddl_setup_http_thread_group(
        ["CREATE DATABASE foo", "CREATE TABLE t1"],
        rest_api_config=_default_rest_api(pre_create_tables=True),
    )

    # 顶层应是 [SetupThreadGroup, hashTree]
    assert len(elems) == 2
    assert _local(elems[0].tag) == "SetupThreadGroup"
    assert _local(elems[1].tag) == "hashTree"

    http_samplers = _collect_http_samplers(elems)
    assert len(http_samplers) == 1 + 2  # 1 Login + 2 DDL

    # Login sampler 应是 GET
    login = http_samplers[0]
    assert _prop_map(login)["HTTPSampler.method"] == "GET"
    assert _prop_map(login)["HTTPSampler.path"] == "/restapi/login"

    # Login 的 Authorization 应是 Basic <base64(user:pass)>
    expected_basic = "Basic " + base64.b64encode(b"root:root123").decode()
    assert _header_pairs(elems, login)["Authorization"] == expected_basic

    # DDL sampler 应是 POST，body 写入 Argument.value，path 是 ddl_url_path
    for i, ddl_sampler in enumerate(http_samplers[1:]):
        assert _prop_map(ddl_sampler)["HTTPSampler.method"] == "POST"
        assert _prop_map(ddl_sampler)["HTTPSampler.path"] == "/restapi/ddl"
        # body = 对应 DDL 字符串
        arg_value = None
        for sp in ddl_sampler.iter():
            if _local(sp.tag) == "stringProp" and sp.get("name") == "Argument.value":
                arg_value = sp.text
                break
        assert arg_value == ["CREATE DATABASE foo", "CREATE TABLE t1"][i]


# ---------------------------------------------------------------------------
# (b) pre_create_tables=false → 仅 Login，无 DDL
# ---------------------------------------------------------------------------


def test_pre_create_false_emits_login_only():
    """pre_create_tables=false 时 SetupTG 仅含 Login sampler，不发任何 DDL sampler。"""
    elems = generate_ddl_setup_http_thread_group(
        ["CREATE DATABASE foo", "CREATE TABLE t1", "CREATE TABLE t2"],
        rest_api_config=_default_rest_api(pre_create_tables=False),
    )

    http_samplers = _collect_http_samplers(elems)
    assert len(http_samplers) == 1, f"expected 1 Login only, got {len(http_samplers)}"
    login = http_samplers[0]
    assert _prop_map(login)["HTTPSampler.method"] == "GET"
    assert _prop_map(login)["HTTPSampler.path"] == "/restapi/login"


# ---------------------------------------------------------------------------
# (c) ca_cert_path=None → RestConfigError（fail-fast，2026-07-27 起 always TLS）
# ---------------------------------------------------------------------------


def test_missing_ca_cert_path_raises_rest_config_error():
    """ca_cert_path=None 时生成器应立即抛 RestConfigError（fail-fast）。

    2026-07-27 行为变更：schemaless Login 强制 TLS，insecure 路径移除，
    因此 ``ca_cert_path`` 必填，不再受 ``https_mode`` 分支影响。
    """
    with pytest.raises(RestConfigError) as excinfo:
        generate_ddl_setup_http_thread_group(
            ["CREATE DATABASE foo"],
            rest_api_config=_default_rest_api(ca_cert_path=None),
        )
    assert "ca_cert_path" in str(excinfo.value)


# ---------------------------------------------------------------------------
# (d) https_mode=tls → Login / DDL sampler 写 customizedSslContext
# ---------------------------------------------------------------------------


def test_tls_writes_customized_ssl_context():
    """https_mode=tls 时 Login 与 DDL sampler 都写 customizedSslContext / ssl.keystore.file，
    值是 UDV ``${__P(rest_api.ca_cert_path,)}``（空默认）。

    2026-07-27：ca_cert_path 不烘焙为字面路径；fixture 相对路径在不同 cwd
    下解析失败，改 UDV 形式由用户 `-Jrest_api.ca_cert_path=/abs/path` 注入。
    """
    elems = generate_ddl_setup_http_thread_group(
        ["CREATE DATABASE foo"],
        rest_api_config=_default_rest_api(
            https_mode="tls", ca_cert_path="/tmp/cert",
        ),
    )

    for sampler in _collect_http_samplers(elems):
        props = _prop_map(sampler)
        assert props.get("HTTPSampler.customizedSslContext") == "${__P(rest_api.ca_cert_path,)}"
        assert props.get("ssl.keystore.file") == "${__P(rest_api.ca_cert_path,)}"


# ---------------------------------------------------------------------------
# (e) 多条 DDL → 对应数量的 DDL sampler
# ---------------------------------------------------------------------------


def test_multiple_ddl_statements_emit_n_ddl_samplers():
    """5 条 DDL 应对应 5 个 DDL sampler（叠加 1 Login 共 6 个 HTTP sampler）。"""
    ddls = [f"CREATE TABLE t{i}" for i in range(5)]
    elems = generate_ddl_setup_http_thread_group(
        ddls,
        rest_api_config=_default_rest_api(pre_create_tables=True),
    )

    http_samplers = _collect_http_samplers(elems)
    assert len(http_samplers) == 1 + 5  # 1 Login + 5 DDL

    # 第二个起都是 POST + path=/restapi/ddl + body=对应 DDL
    ddl_samplers = http_samplers[1:]
    for i, ddl_sampler in enumerate(ddl_samplers):
        props = _prop_map(ddl_sampler)
        assert props["HTTPSampler.method"] == "POST"
        assert props["HTTPSampler.path"] == "/restapi/ddl"
        arg_value = None
        for sp in ddl_sampler.iter():
            if _local(sp.tag) == "stringProp" and sp.get("name") == "Argument.value":
                arg_value = sp.text
                break
        assert arg_value == ddls[i]


# ---------------------------------------------------------------------------
# (f) rel_init_specs 非空走 _build_rel_init_subtree 通路
# ---------------------------------------------------------------------------


def test_rel_init_specs_pass_through_unchanged():
    """rel_init_specs 非空时走现有 ``_build_rel_init_subtree``，不重写 rel-init 装配逻辑。

    验证手段：rel-init 子树特有的 ``RelInit_`` / ``relprep`` 标记出现，并且
    SetupTG 仍包含 Login sampler（证明 HTTP DDL SetupTG 与 rel-init 编排
    共存于同一 SetupThreadGroup 内）。
    """
    elems = generate_ddl_setup_http_thread_group(
        ["CREATE DATABASE foo"],
        rel_init_specs=[
            {
                "table_name": "db.rel.t1",
                "columns": ["col_varchar_1"],
                "total_rows": 100,
                "batch_lines": 100,
                "rel_col_seed_files": ["fake_seed.csv"],
                "column_types": ["varchar"],
            }
        ],
        rest_api_config=_default_rest_api(pre_create_tables=False),
    )

    xml = "".join(ET.tostring(e, encoding="unicode") for e in elems)

    # rel-init 子树特征标记必须出现（由现有 _build_rel_init_subtree 产出）。
    # sampler 命名遵循 sampler_generator.py:343：``f"RelInit_{db}_{table_name.split('.', 1)[1]}"``
    # 对 ``table_name="db.rel.t1"`` → ``RelInit_db_rel.t1``。
    assert "RelInit_db_rel.t1" in xml, (
        "rel-init subtree sampler 名称 RelInit_db_rel.t1 应出现"
    )
    assert "relprep" in xml, "rel-init JSR223PreProcessor relprep 应出现"

    # Login 仍存在（pre_create_tables=False → 仅 Login + rel-init）
    assert _prop_map(_collect_http_samplers(elems)[0])["HTTPSampler.method"] == "GET"


# ---------------------------------------------------------------------------
# Bug 1（§6 implementer smoke）：HTTPSampler 必须由 caller 注入 domain/port/protocol。
#
# 背景：``http_request_sampler_element`` 不产出 ``HTTPSampler.domain`` /
# ``HTTPSampler.port`` / ``HTTPSampler.protocol``（per utils ref doc R1 锁）。
# 缺这三项 → JMeter 报 "URI does not specify a valid host name: http:/restapi/ddl"。
# 验证必须 SPECIFIC：不能只断言键存在，要断言内容是 ``${__P(rest_api.*)}`` 引用。
# ---------------------------------------------------------------------------


def test_http_samplers_inject_domain_port_protocol_with_property_references():
    """每个 HTTP sampler（含 Login + 每条 DDL）必须有 ``HTTPSampler.domain`` /
    ``HTTPSampler.port`` / ``HTTPSampler.protocol`` 三个 stringProp，且取值
    是 ``${__P(rest_api.hostname,127.0.0.1)}`` / ``${__P(rest_api.http_port,8080)}``
    与 TLS 模式对应的 ``"https"`` 字面量（2026-07-27 起 always TLS）。"""
    elems = generate_ddl_setup_http_thread_group(
        ["CREATE DATABASE foo", "CREATE TABLE t1", "CREATE TABLE t2"],
        rest_api_config=_default_rest_api(pre_create_tables=True),
    )

    http_samplers = _collect_http_samplers(elems)
    assert len(http_samplers) == 1 + 3  # 1 Login + 3 DDL
    for sampler in http_samplers:
        props = _prop_map(sampler)
        assert props.get("HTTPSampler.domain") == "${__P(rest_api.hostname,127.0.0.1)}", (
            f"HTTPSampler.domain 必须注入 {{__P(rest_api.hostname,127.0.0.1)}} 引用, "
            f"got {props.get('HTTPSampler.domain')!r}"
        )
        assert props.get("HTTPSampler.port") == "${__P(rest_api.http_port,8080)}", (
            f"HTTPSampler.port 必须注入 {{__P(rest_api.http_port,8080)}} 引用, "
            f"got {props.get('HTTPSampler.port')!r}"
        )
        assert props.get("HTTPSampler.protocol") == "https", (
            f"TLS 模式下 HTTPSampler.protocol 必须等于 'https' 字面量, "
            f"got {props.get('HTTPSampler.protocol')!r}"
        )


# ---------------------------------------------------------------------------
# Bug 2（§6 implementer smoke）：JSR223 PostProcessor script 必须是真正 Groovy
# 代码，不能是 ``${__setProperty(...)}`` 这种 JMeter 函数表达式（后者被 JMeter
# 视为空脚本 → "Both script file and script text are empty"）。
# ---------------------------------------------------------------------------


_TOKEN_SET_PROP_GROOVY_LITERAL = (
    'def t = vars.get("token")\n'
    'if (t != null && t.length() > 0) {\n'
    '    props.put("rest_token", t)\n'
    '}\n'
    'return'
)


def test_rest_token_set_property_script_is_valid_groovy():
    """``REST Token Set Property`` JSR223 PostProcessor 的 script 必须是 Groovy
    代码 ``props.put("rest_token", vars.get("token"))\\nreturn``；不能含
    ``${__setProperty(...)}`` 之类的 JMeter 函数表达式（那会被 JMeter 视为
    空脚本报错）。"""
    elems = generate_ddl_setup_http_thread_group(
        ["CREATE DATABASE foo"],
        rest_api_config=_default_rest_api(pre_create_tables=False),
    )

    # 找 ``REST Token Set Property`` PostProcessor 的 script 字符串。
    # testname 是元素属性（attribs），不是 stringProp——直接读 .attrib。
    token_postprocs = _collect_by_tag(elems, "JSR223PostProcessor")
    target = None
    for pp in token_postprocs:
        # ElementTree 把 qname 写入 .attrib（命名空间被丢掉）；testname 是不带 ns 的 attr
        testname_attr = pp.attrib.get("testname", "")
        name_attr = pp.attrib.get("name", "")
        if "REST Token Set Property" in (testname_attr, name_attr):
            target = pp
            break
    assert target is not None, (
        "应存在 testname/name 包含 'REST Token Set Property' 的 JSR223PostProcessor"
    )

    script = _prop_map(target)["script"]
    # 必须完全等于 Groovy 字面量
    assert script == _TOKEN_SET_PROP_GROOVY_LITERAL, (
        f"JSR223 PostProcessor script 必须是 Groovy 代码, got {script!r}"
    )
    # 反例：不能含 ${__setProperty(...)} 函数表达式
    assert "${__setProperty" not in script, (
        f"script 不应含 JMeter 函数表达式 ${{__setProperty(...)}}, got {script!r}"
    )
    # 反例：不能仅是变量引用模板
    assert not script.lstrip().startswith("${"), (
        f"script 不应以 ${{...}} 模板开头, got {script!r}"
    )


# ---------------------------------------------------------------------------
# §6.4.2：JSR223 PostProcessor script 必须在 props.put 之前 null/empty 守卫。
#
# 背景：smoke 跑出 DDL-2 服务端拒 ``{"code":-1,"desc":"can not find Basic
# attribute"}``。根因：当 JSON Extractor 未抽出 ``${token}`` 或 Login 失败，
# ``vars.get("token")`` 返 null/空字符串；裸 ``props.put("rest_token", null)``
# 在 JMeter 的 Groovy 上下文会被字符串化成 "null" 或抛 NPE；下游
# ``${__property(rest_token)}`` 解析为空，Authorization header 变成
# ``Basic null`` 或 ``Basic ``，服务端认不出 Base64 token 直接拒。
#
# DDL-1（ts database）服务端弱校验侥幸 201 创建；DDL-2（ts table with
# primary tags）服务端强校验触发拒绝。修复：生成器层加 null/empty 守卫，
# 避免写入空值污染 JMeter 全局 property。
# ---------------------------------------------------------------------------


def test_setprop_script_guards_against_null_or_empty_token():
    """``REST Token Set Property`` JSR223 PostProcessor script 必须 null/empty
    守卫：仅在 ``vars.get("token")`` 返非空字符串时才 ``props.put``。

    验证手段：
      (1) script 内必须含 ``vars.get("token")`` 取值
      (2) script 内必须把取到的值赋给一个局部变量（典型名 ``t`` / ``token``）
      (3) script 内必须有空值守卫（``!= null && .length() > 0``
          或同义 表达式）
      (4) ``props.put("rest_token", ...)`` 出现在守卫的**分支体内**
          （"           n     n    "  -ish），

    反例：
      - 裸 ``props.put("rest_token", vars.get("token"))`` —— §6.4.2 BUG
      - 守卫但 ``props.put`` 在守卫外 —— 无效
    """
    elems = generate_ddl_setup_http_thread_group(
        ["CREATE DATABASE foo"],
        rest_api_config=_default_rest_api(pre_create_tables=False),
    )

    token_postprocs = _collect_by_tag(elems, "JSR223PostProcessor")
    target = None
    for pp in token_postprocs:
        testname_attr = pp.attrib.get("testname", "")
        name_attr = pp.attrib.get("name", "")
        if "REST Token Set Property" in (testname_attr, name_attr):
            target = pp
            break
    assert target is not None, (
        "应存在 testname/name 含 'REST Token Set Property' 的 JSR223PostProcessor"
    )

    script = _prop_map(target)["script"]
    # (1) 必须含 vars.get("token")
    assert 'vars.get("token")' in script, (
        f"script 必须取值 vars.get('token'), got {script!r}"
    )
    # (2) 必须含 null 守卫短语（精确两 token：'null' 与 'length()'）
    assert "null" in script and "length()" in script, (
        f"script 必须含 null/empty 守卫 (eg. 't != null && t.length() > 0'), "
        f"got {script!r}"
    )
    # (3) props.put 必须在守卫内 —— 用简化判定：'if (' 出现在 'props.put' 之前
    if_pos = script.find("if ")
    put_pos = script.find("props.put")
    assert if_pos != -1 and put_pos != -1 and if_pos < put_pos, (
        f"props.put 必须落在 'if' 守卫块体内, got {script!r}"
    )


# ---------------------------------------------------------------------------
# §6.4.2 副 Bug：SetupThreadGroup.duration 硬编 1s → TLS 握手 1.7s 时
# Login 之外的 DDL-1 / DDL-2 在 1s 截止线被停掉，从 JTL 消失。
#
# 现状：smoke 跑出 "12 samples / 11 pass / 1 fail"，少 DDL-1 / DDL-2 各 1
# sample，与 OpenSpec §6.3 (a) SetupTG Login/DDL `code==0` 期望的 3 个
# sampler 不符（仅 1 个 Login，2 个 DDL 缺失）。SetupTG.duration 必须
# ≥ TLS 握手 + DDL RTT 总和；硬编 1s 是过短。
#
# 修复（§6.4.2 锁 D）：SetupTG.duration 改为 ``${test_duration}`` UDV 形式，
# 与主 TG（Write/Query）一致；这样 -Jtest_duration=30 让 setup 也有 30s
# 跑完 Login + DDL-1 + DDL-2。
# ---------------------------------------------------------------------------


def test_setup_thread_group_duration_uses_test_duration_udv():
    """``SetupThreadGroup.duration`` 必须是 ``${test_duration}`` UDV 引用
    （非硬编字面 ``1`` / ``30``）。原因：TLS 握手 + DDL RTT 通常 ≥2s，
    硬编短值会让 Login 之后的 DDL-1 / DDL-2 被 scheduler 截止掉。
    """
    elems = generate_ddl_setup_http_thread_group(
        ["CREATE DATABASE foo", "CREATE TABLE t1"],
        rest_api_config=_default_rest_api(pre_create_tables=True),
    )

    setup_tg = elems[0]
    duration_prop = None
    for sp in setup_tg:
        if _local(sp.tag) == "stringProp" and sp.get("name") == "ThreadGroup.duration":
            duration_prop = sp.text
            break
    assert duration_prop is not None, (
        "SetupThreadGroup 必须有 ThreadGroup.duration stringProp"
    )
    assert duration_prop == "${test_duration}", (
        f"SetupThreadGroup.duration 必须是 ${{test_duration}} UDV 形式, "
        f"got {duration_prop!r}"
    )
    # 反例：不能是字面 1 / 30 / 任意秒数
    assert duration_prop not in ("1", "30", "60", "120"), (
        f"SetupThreadGroup.duration 不能硬编秒数, got {duration_prop!r}"
    )