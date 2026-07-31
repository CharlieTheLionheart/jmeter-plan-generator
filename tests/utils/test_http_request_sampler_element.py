"""针对 ``utils.xml_helpers.http_request_sampler_element`` 的单元测试。

覆盖 proposal §1.3：
  (a) GET/POST/PUT 方法切换
  (b) HeaderManager 节点
  (c) ssl_context 写入两属性
  (d) ssl_context=None 不产出 ssl 节点
  (e) body 字面量保留（JMeter 运行时展开）
  (f) (sampler, hashTree) 配对正确
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from utils.xml_helpers import http_request_sampler_element

NS = "http://jmeter.apache.org/"


def _local(tag: str) -> str:
    """去掉命名空间前缀，返回本地标签名。"""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _prop_map(elem: ET.Element) -> dict[str, str]:
    """收集 elem 直接子级中所有 stringProp/boolProp/intProp 的 name->text。"""
    out: dict[str, str] = {}
    for child in elem:
        if _local(child.tag) in ("stringProp", "boolProp", "intProp", "longProp"):
            out[child.get("name")] = child.text or ""
    return out


def _find_arg_value(sampler: ET.Element) -> str | None:
    """在 Arguments 子树里找到 HTTPArgument 的 Argument.value 文本。"""
    for sp in sampler.iter():
        if _local(sp.tag) == "stringProp" and sp.get("name") == "Argument.value":
            return sp.text
    return None


def _make(method="POST", *, body="", ssl_context=None, headers=None, follow_redirects=True):
    return http_request_sampler_element(
        method,
        "${rest_api.write_url_path}",
        headers if headers is not None else {"Content-Type": "application/json"},
        body,
        ssl_context=ssl_context,
        name="write-sampler",
        testname="write-sampler",
        follow_redirects=follow_redirects,
    )


# (f) 配对正确 --------------------------------------------------------------

def test_returns_sampler_and_hashtree_pair():
    sampler, ht = _make()
    assert _local(sampler.tag) == "HTTPSamplerProxy"
    assert _local(ht.tag) == "hashTree"
    assert sampler.get("guiclass") == "HttpTestSampleGui"
    assert sampler.get("testclass") == "HTTPSamplerProxy"
    assert sampler.get("enabled") == "true"
    assert sampler.get("testname") == "write-sampler"


# (a) 方法切换 --------------------------------------------------------------

def test_method_get_post_put_switch():
    for method in ("GET", "POST", "PUT"):
        sampler, _ = _make(method=method, body="" if method == "GET" else "{}")
        assert _prop_map(sampler)["HTTPSampler.method"] == method


def test_path_written():
    sampler, _ = _make()
    assert _prop_map(sampler)["HTTPSampler.path"] == "${rest_api.write_url_path}"


def test_standard_bool_props_present():
    sampler, _ = _make()
    props = _prop_map(sampler)
    assert props["HTTPSampler.follow_redirects"] == "true"
    assert props["HTTPSampler.auto_redirects"] == "false"
    assert props["HTTPSampler.use_keepalive"] == "true"
    assert props["HTTPSampler.DO_MULTIPART_POST"] == "false"
    assert props["HTTPSampler.BROWSER_COMPATIBLE_MULTIPART"] == "false"


def test_follow_redirects_false_when_disabled():
    sampler, _ = _make(follow_redirects=False)
    assert _prop_map(sampler)["HTTPSampler.follow_redirects"] == "false"


def test_caller_owned_props_not_written():
    """protocol/port/domain 由调用方写入，本函数不得产出，避免重复。"""
    sampler, _ = _make()
    props = _prop_map(sampler)
    assert "HTTPSampler.protocol" not in props
    assert "HTTPSampler.port" not in props
    assert "HTTPSampler.domain" not in props


# (b) HeaderManager --------------------------------------------------------

def test_header_manager_in_hashtree():
    sampler, ht = _make(headers={"Content-Type": "application/json", "Authorization": "Token abc"})
    hms = [c for c in ht if _local(c.tag) == "HeaderManager"]
    assert len(hms) == 1
    hm = hms[0]
    assert hm.get("testclass") == "HeaderManager"
    # HeaderManager 之后必须紧跟一个 hashTree 兄弟节点
    children = list(ht)
    idx = children.index(hm)
    assert _local(children[idx + 1].tag) == "hashTree"
    # 收集 header 的 name/value 对
    pairs = {}
    for ep in hm.iter():
        if _local(ep.tag) == "elementProp" and ep.get("elementType") == "Header":
            name = value = None
            for sp in ep:
                if sp.get("name") == "Header.name":
                    name = sp.text
                elif sp.get("name") == "Header.value":
                    value = sp.text
            pairs[name] = value
    assert pairs == {"Content-Type": "application/json", "Authorization": "Token abc"}


# (c) ssl_context 两属性 ----------------------------------------------------

def test_ssl_context_writes_two_props():
    sampler, _ = _make(ssl_context="/etc/ssl/ca.crt")
    props = _prop_map(sampler)
    assert props["HTTPSampler.customizedSslContext"] == "/etc/ssl/ca.crt"
    assert props["ssl.keystore.file"] == "/etc/ssl/ca.crt"


# (d) ssl_context=None 不产出 ssl 节点 --------------------------------------

def test_ssl_context_none_omits_ssl_props():
    sampler, _ = _make(ssl_context=None)
    props = _prop_map(sampler)
    assert "HTTPSampler.customizedSslContext" not in props
    assert "ssl.keystore.file" not in props


# (e) body 字面量保留 + postBodyRaw -----------------------------------------

def test_body_literal_preserved_and_post_body_raw():
    sampler, _ = _make(method="POST", body="${request_body}")
    assert _find_arg_value(sampler) == "${request_body}"
    assert _prop_map(sampler)["HTTPSampler.postBodyRaw"] == "true"


def test_empty_body_omits_post_body_raw():
    sampler, _ = _make(method="GET", body="")
    props = _prop_map(sampler)
    assert "HTTPSampler.postBodyRaw" not in props
    assert _find_arg_value(sampler) is None


def test_body_survives_xml_serialization():
    """序列化后 body 内容不丢失（CDATA/转义均可，只要往返一致）。"""
    sampler, _ = _make(method="POST", body="${request_body}")
    xml = ET.tostring(sampler, encoding="unicode")
    assert "${request_body}" in xml
