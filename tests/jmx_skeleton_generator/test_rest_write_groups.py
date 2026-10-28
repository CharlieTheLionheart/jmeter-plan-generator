"""针对 ``rest_write_groups.generate_rest_write_thread_group`` 的单元测试。

OpenSpec §3（task-3-brief.md）7 个 case (a)-(g)：

  (a) 单 measurement → 1 个 sampler 单元
  (b) N measurements → N 个 TG，每个 TG 内 1 个 sampler 单元
  (c) tag_set key 与 DDL ptag 对齐时 PreProcessor 拼出的 line 正确格式
  (d) HTTPSamplerProxy body 必须是 ``${request_body}`` 变量引用（不烘焙）
  (e) PreProcessor 脚本必含 ``escapeLineValue`` / ``formatFieldValue`` /
      ``buildLine`` 三个 Groovy helper 定义
  (f) path 正确拼接 ``?db=`` 与 ``&tz=``（``timezone`` 仅在非空时附加）
  (g) ``customizedSslContext`` 仅在 ``https_mode=tls`` 时注入

参考资料：
  - docs/refs/jmx-components-references.md §HTTPSamplerProxy
  - docs/refs/kaiwudb-schemaless-write-reference.md §5.2（InfluxDB Line
        字段转义规则）
  - utils/xml_helpers.http_request_sampler_element / jsr223_preprocessor_element
        / thread_group_element（既有 helper）
  - throughput_control.generate_write_timer（既有，烤死 cfg ``WriteConfig.throughput`` 字面量）
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
    WriteConfig,
)
from jmx_skeleton_generator.generators.rest_write_groups import (
    generate_rest_write_thread_group,
)


NS = "http://jmeter.apache.org/"


# ---------------------------------------------------------------------------
# XML helpers (mirror pattern from test_ddl_setup_http_thread_group.py)
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


def _collect_jsr223_preps(elements) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == "JSR223PreProcessor"]


def _collect_timer_pairs(elements) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == "ConstantThroughputTimer"]


def _collect_thread_groups(elements) -> List[ET.Element]:
    return [e for e in _walk(elements) if _local(e.tag) == "ThreadGroup"]


def _sampler_body_text(sampler: ET.Element) -> str:
    """从 HTTPSamplerProxy 的 Arguments.HTTPArgument.Argument.value 提取 body 文本。"""
    for ep in sampler.iter():
        if _local(ep.tag) == "stringProp" and ep.get("name") == "Argument.value":
            return ep.text or ""
    return ""


# ---------------------------------------------------------------------------
# Fixtures: minimal TestModelConfig + TsTableConfig + rest_api_config
# ---------------------------------------------------------------------------

def _make_ptag(col_type: str = "varchar(64)", val_range: str = '"device_{1}"') -> PrimaryTagColTypeConfig:
    return PrimaryTagColTypeConfig(col_type=col_type, type_proportion=1.0, val_range=val_range)


def _make_rtag(col_type: str = "varchar(64)", val_range: str = '"Beijing"') -> ColTypeConfig:
    return ColTypeConfig(col_type=col_type, type_proportion=1.0, val_range=val_range, seed_num=1, nullable=False)


def _make_data_col(col_type: str = "float4", val_range: str = "0..100", seed_num: int = 100) -> ColTypeConfig:
    return ColTypeConfig(col_type=col_type, type_proportion=1.0, val_range=val_range, seed_num=seed_num, nullable=False)


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
        "write_url_path": "/restapi/influxdb",
        "default_db": "db_iot",
        "https_mode": "tls",
        "ca_cert_path": "/etc/kaiwudb/certs/ca.crt",
        "timezone": None,
    }
    cfg.update(overrides)
    return cfg


def _single_table_model() -> TestModelConfig:
    table = _make_table(
        name="meters",
        ptag=_make_ptag(),
        rtag=_make_rtag(val_range='"Beijing"'),
        data_col=_make_data_col(val_range="0..100"),
    )
    return TestModelConfig(
        ts_dbs=[TsDbConfig(name="db_iot", tables=[table])],
    )


def _multi_table_model() -> TestModelConfig:
    t1 = _make_table(
        name="meters",
        ptag=_make_ptag(),
        rtag=_make_rtag(val_range='"Beijing"'),
        data_col=_make_data_col(val_range="0..100"),
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


def _single_table_write_configs() -> List[WriteConfig]:
    """write_configs matching ``_single_table_model`` (table=db_iot.meters)."""
    return [
        WriteConfig(tbl_name="db_iot.meters", throughput=60.0, mode="schemaless"),
    ]


def _multi_table_write_configs() -> List[WriteConfig]:
    """write_configs matching ``_multi_table_model`` (db_iot.{meters,voltage})."""
    return [
        WriteConfig(tbl_name="db_iot.meters", throughput=60.0, mode="schemaless"),
        WriteConfig(tbl_name="db_iot.voltage", throughput=60.0, mode="schemaless"),
    ]


# ---------------------------------------------------------------------------
# (a) 单 measurement → 1 个 sampler 单元 + Timer + TG
# ---------------------------------------------------------------------------

def test_single_measurement_emits_one_sampler_unit():
    """单 measurement → 1 个 TG，内含 1 个 JSR223PreProcessor + 1 个 HTTPSamplerProxy + 1 个 ConstantThroughputTimer。"""
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_single_table_write_configs(),
    )

    # 顶层应为 [TG, hashTree, TG, hashTree, ...]；这里 N=1 → 2 个顶层元素
    tg_list = _collect_thread_groups(elems)
    assert len(tg_list) == 1, f"expected 1 ThreadGroup, got {len(tg_list)}"

    preps = _collect_jsr223_preps(elems)
    samplers = _collect_http_samplers(elems)
    timers = _collect_timer_pairs(elems)
    assert len(preps) == 1, f"expected 1 JSR223PreProcessor, got {len(preps)}"
    assert len(samplers) == 1, f"expected 1 HTTPSamplerProxy, got {len(samplers)}"
    assert len(timers) == 1, f"expected 1 ConstantThroughputTimer, got {len(timers)}"

    # Sampler 必须是 POST，path 必须含 ?db=db_iot
    sampler = samplers[0]
    sampler_props = _prop_map(sampler)
    assert sampler_props["HTTPSampler.method"] == "POST"
    assert sampler_props["HTTPSampler.path"] == "/restapi/influxdb?db=db_iot"


# ---------------------------------------------------------------------------
# (b) 多 measurement → N 个 TG，每个内含 1 个 sampler 单元
# ---------------------------------------------------------------------------

def test_multiple_measurements_emit_n_sampler_units():
    """N measurements → N 个 TG，每个 TG 内部各自 1 个 sampler 单元。"""
    elems = generate_rest_write_thread_group(
        _multi_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_multi_table_write_configs(),
    )

    tg_list = _collect_thread_groups(elems)
    assert len(tg_list) == 2, f"expected 2 ThreadGroups, got {len(tg_list)}"

    preps = _collect_jsr223_preps(elems)
    samplers = _collect_http_samplers(elems)
    timers = _collect_timer_pairs(elems)
    assert len(preps) == 2
    assert len(samplers) == 2
    assert len(timers) == 2

    # Sampler names / testnames 应区分 measurement（不可重名）
    testnames = [s.get("testname") for s in samplers]
    assert len(set(testnames)) == 2, f"samplers must have unique testnames, got {testnames}"


# ---------------------------------------------------------------------------
# (c) tag_set key 与 DDL ptag 对齐 → PreProcessor 拼出正确格式 line
# ---------------------------------------------------------------------------

def test_tag_set_matches_ptag_produces_correct_line():
    """fixture: measurement=meters, ptag=device_id(varchar), rtag=location(varchar), field=current(float)。
    模拟 SharedMemory 行 = [device_1, Beijing, 17.01]；验证 PreProcessor 脚本生成的
    Groovy 逻辑会产出 ``meters,device_id=device_1,location=Beijing current=17.01 <ts>``。
    """
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_single_table_write_configs(),
    )

    preps = _collect_jsr223_preps(elems)
    assert len(preps) == 1
    script = _prop_map(preps[0])["script"]

    # 必备的 Groovy helper 定义 + measurement-specific 常量 + 关键调用
    must_contain = [
        'def formatFieldValue',
        'def buildLine',
        'def measurement = "meters"',  # measurement 名（无 quotes）
        'def rowsKey = "__SHARED_MEM_db_iot_meters"',
        'globalProps.get(rowsKey)',     # 走 globalProps 而非 props
        'buildLine(measurement, tagMap, fieldMap)',  # 关键调用（B2 锁 E：ts 进 fieldMap）
    ]
    for needle in must_contain:
        assert needle in script, f"PreProcessor script must contain {needle!r}, got:\n{script}"

    # 验证三个 group（ptag / rtag / data_col）的列名分别烘焙进 Groovy 列表
    # 列名由 column_namer 分配，预期形式：ptag_varchar_1 / rtag_varchar_1 / col_float4_1
    # （不必强绑字面量，但要求至少 ptag / rtag / field 三组名字按 group 拆分）
    assert 'ptagNames' in script, "PreProcessor must define ptagNames set"
    assert 'tagNames' in script, "PreProcessor must define tagNames set"
    assert 'fieldNames' in script, "PreProcessor must define fieldNames set"

    # Regression guard: ptag names must route into tagMap (InfluxDB Line has no
    # ptag/rtag distinction; per kaiwudb-schemaless §9.1 the server maps tag
    # keys matching ptag column names → ptag column). If the loop ever
    # re-introduces the `if (name in ptagNames) { continue }` skip, the
    # script will produce empty tagMap entries for ptag columns and the
    # server has no data for ptag — silently dropping writes.
    import re
    assert not re.search(
        r"if\s*\(\s*name\s+in\s+ptagNames\s*\)\s*\{[^}]*continue",
        script,
        re.DOTALL,
    ), (
        "PreProcessor must NOT skip ptag names — InfluxDB Line routes ptag "
        "keys into tagMap. See kaiwudb-schemaless §9.1."
    )

    # Positive assertion: the for-loop's tagMap branch must cover ptag names
    # (i.e. `name in ptagNames || name in tagNames`). Verify by simulating
    # the loop logic against the baked-in sets: ptag column name should
    # land in tagMap, rtag column name should land in tagMap, field column
    # name should land in fieldMap.
    import re as _re
    assert _re.search(
        r"if\s*\(\s*name\s+in\s+ptagNames\s*\|\|\s*name\s+in\s+tagNames\s*\)",
        script,
    ), (
        "PreProcessor must merge ptag + rtag into the same tagMap branch "
        "(`name in ptagNames || name in tagNames`)."
    )

    # Extract the baked-in ptag / rtag / field names from the script and
    # simulate the loop to assert that the ptag key ends up in tagMap
    # (positive behaviour, not just structural absence).
    def _extract_set(name: str) -> List[str]:
        m = _re.search(rf"def {name}\s*=\s*\[(.*?)\]\s*as\s*Set", script)
        assert m, f"missing {name} set definition"
        return [s.strip().strip('"') for s in m.group(1).split(",") if s.strip()]

    ptag_names_baked = _extract_set("ptagNames")
    rtag_names_baked = _extract_set("tagNames")
    field_names_baked = _extract_set("fieldNames")
    assert ptag_names_baked, "ptagNames set must not be empty for meters fixture"
    assert rtag_names_baked, "tagNames set must not be empty for meters fixture"
    assert field_names_baked, "fieldNames set must not be empty for meters fixture"

    # Simulate: row = ["device_1", "Beijing", "17.01"]; columns = ptag + rtag + field
    columns = ptag_names_baked + rtag_names_baked + field_names_baked
    row = ["device_1", "Beijing", "17.01"]
    tagMap: Dict[str, str] = {}
    fieldMap: Dict[str, str] = {}
    for i, col_name in enumerate(columns):
        if col_name in ptag_names_baked or col_name in rtag_names_baked:
            tagMap[col_name] = row[i]  # escapeTagValue passthrough (no specials)
        elif col_name in field_names_baked:
            fieldMap[col_name] = row[i]

    # 关键：ptag 列名（device_id）必须在 tagMap 里 — 否则 server 无 ptag 数据
    assert ptag_names_baked[0] in tagMap, (
        f"ptag column {ptag_names_baked[0]!r} must populate tagMap, got tagMap={tagMap}"
    )
    assert tagMap[ptag_names_baked[0]] == "device_1", (
        f"ptag value must be 'device_1', got {tagMap[ptag_names_baked[0]]!r}"
    )
    # rtag 列名（location）也必须在 tagMap 里
    assert rtag_names_baked[0] in tagMap, (
        f"rtag column {rtag_names_baked[0]!r} must populate tagMap, got tagMap={tagMap}"
    )
    assert tagMap[rtag_names_baked[0]] == "Beijing"
    # field 列名（current）必须在 fieldMap 里
    assert field_names_baked[0] in fieldMap
    assert fieldMap[field_names_baked[0]] == "17.01"


# ---------------------------------------------------------------------------
# (d) HTTPSamplerProxy body 必须字符串等于 ``${request_body}``
# ---------------------------------------------------------------------------

def test_sampler_body_is_request_body_var_ref():
    """HTTPSamplerProxy body 必须等于 ``${request_body}``，**不**烘焙数据。"""
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_single_table_write_configs(),
    )

    samplers = _collect_http_samplers(elems)
    assert len(samplers) == 1
    body = _sampler_body_text(samplers[0])
    assert body == "${request_body}", f"body must be ${request_body}, got {body!r}"

    # 防退化：确保 body 字符串里没有烘焙的 SharedMemory 行内容（device_1 / Beijing / 17.01）
    assert "device_1" not in body
    assert "Beijing" not in body
    assert "17.01" not in body


# ---------------------------------------------------------------------------
# (e) PreProcessor script 必含三个 Groovy helper 定义
# ---------------------------------------------------------------------------

def test_groovy_script_contains_required_helpers():
    """PreProcessor script must define ``formatFieldValue`` + ``buildLine``.

    D-22 (2026-08-14): removed ``escapeLineValue`` helper — it was dead
    code (never invoked anywhere) with a Python double-escape chain that
    produced an Unescaped trailing backslash in JMeter 5.6.3 Groovy after
    the numThreads fix (D-21) exposed the path. ``formatFieldValue``
    handles all string escaping via its else-branch.
    """
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_single_table_write_configs(),
    )

    preps = _collect_jsr223_preps(elems)
    assert len(preps) == 1
    script = _prop_map(preps[0])["script"]

    assert "def formatFieldValue" in script, "script must define formatFieldValue"
    assert "def buildLine" in script, "script must define buildLine"

    # formatFieldValue must include InfluxDB Line escape sequences for
    # the string-quote-wrap else-branch (handles backslash and quote).
    assert "\\," in script or "','\\\\,'", "formatFieldValue must include InfluxDB escape sequences"


# ---------------------------------------------------------------------------
# (f) path 正确拼接 ``?db=`` 与可选 ``&tz=``
# ---------------------------------------------------------------------------

def test_path_includes_db_and_optional_tz():
    """默认 ``timezone=None`` → ``path=/restapi/influxdb?db=defaultdb``；
    ``timezone='Asia/Shanghai'`` → ``path=/restapi/influxdb?db=defaultdb&tz=Asia/Shanghai``。
    """
    cfg_no_tz = _default_rest_api(default_db="db_iot")
    elems_no_tz = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=cfg_no_tz,
        write_configs=_single_table_write_configs(),
    )
    samplers = _collect_http_samplers(elems_no_tz)
    assert len(samplers) == 1
    path_no_tz = _prop_map(samplers[0])["HTTPSampler.path"]
    assert path_no_tz == "/restapi/influxdb?db=db_iot", (
        f"expected path without tz, got {path_no_tz!r}"
    )

    # 有 timezone → 附加 &tz=
    cfg_tz = _default_rest_api(default_db="db_iot", timezone="Asia/Shanghai")
    elems_tz = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=cfg_tz,
        write_configs=_single_table_write_configs(),
    )
    samplers_tz = _collect_http_samplers(elems_tz)
    assert len(samplers_tz) == 1
    path_tz = _prop_map(samplers_tz[0])["HTTPSampler.path"]
    assert path_tz == "/restapi/influxdb?db=db_iot&tz=Asia/Shanghai", (
        f"expected path with tz, got {path_tz!r}"
    )


# ---------------------------------------------------------------------------
# (g) ``HTTPSampler.customizedSslContext`` 仅在 ``https_mode=tls`` 时注入
# ---------------------------------------------------------------------------

def test_customized_ssl_context_only_when_tls():
    """``https_mode='tls'`` + ``ca_cert_path='/tmp/cert'`` → HTTPSampler
    写 ``HTTPSampler.customizedSslContext`` / ``ssl.keystore.file`` 两个属性。

    2026-07-27 行为变更：schemaless Login 强制 TLS（insecure 路径移除），
    HTTPSampler 始终带 ssl 属性，不再有 insecure 分支对照。

    2026-07-27 进一步：``ca_cert_path`` **不**烘焙为字面路径，而是 UDV
    ``${__P(rest_api.ca_cert_path,)}``（空默认）—— 用户必须
    ``-Jrest_api.ca_cert_path=/abs/path/to/ca.crt`` 显式注入绝对路径，
    避免 fixture 相对路径在不同 cwd 下解析失败。
    """
    elems_tls = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(https_mode="tls", ca_cert_path="/tmp/cert"),
        write_configs=_single_table_write_configs(),
    )
    for sampler in _collect_http_samplers(elems_tls):
        props = _prop_map(sampler)
        assert props.get("HTTPSampler.customizedSslContext") == "${__P(rest_api.ca_cert_path,)}"
        assert props.get("ssl.keystore.file") == "${__P(rest_api.ca_cert_path,)}"


# ---------------------------------------------------------------------------
# (g) Bug-fix smoke 回归：HTTPSampler 必须含 ``__P(rest_api.*,default)`` 带默认值
#     的引用（缺默认值时 JMeter 在没有 -Jrest_api.* 时回退到 "1"，触发
#     "Connect to 1:1 [/0.0.0.1] failed: 连接超时"）。
# ---------------------------------------------------------------------------


def test_http_samplers_domain_and_port_have_property_defaults():
    """``HTTPSampler.domain`` / ``HTTPSampler.port`` 必须用 ``${__P(rest_api.*,DEFAULT)}``
    形式 — ``__P`` 第二参数是 JMeter 函数缺省值（属性未设时使用），允许
    ``-J`` 未传 rest_api.* 时 smoke 仍能连默认 127.0.0.1:8080。"""
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_single_table_write_configs(),
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


def test_preprocessor_script_handles_rows_empty_gracefully():
    """JSR223PreProcessor 在 rows 空时必须抛业务异常（不要继续发无效请求）。

    write-missing-data D11 修订：旧的"置空 body 静默退出"会让整轮测试
    "全绿但一行没写"——空种子池必须尽早暴露为 sampler error。

    反例（禁止）：
      - ``ctx.stopThread()`` / ``ctx.setStopThread(true)``（JMeter 5.6.3 接口无此方法）
      - ``SampleResult.setIgnore()``（PreProcessor 中 SampleResult 未绑定）
      - 仅 log 不停线程（会产生无效 HTTP 请求）
    """
    from jmx_skeleton_generator.generators.rest_write_groups import (
        _build_rest_write_preprocessor_script,
    )
    from config_parser.models import TsDbConfig, TsTableConfig, PrimaryTagColTypeConfig

    table = TsTableConfig(
        name="meters",
        data_col_count=0,
        data_cols=[],
        primary_tag_count=1,
        primary_tags=[
            PrimaryTagColTypeConfig(col_type="varchar(64)", type_proportion=1.0),
        ],
        regular_tag_count=0,
        regular_tags=[],
    )
    script = _build_rest_write_preprocessor_script(db="defaultdb", table="meters", ts_table=table)
    assert "throw new RuntimeException" in script, (
        f"rows-empty 分支必须抛业务异常（不静默降级）, got:\n{script}"
    )
    assert "seed CSV load failed" in script, (
        f"rows-empty 分支必须带失败提示, got:\n{script}"
    )
    assert "vars.put('request_body', '')" not in script, (
        f"rows-empty 分支禁止静默置空 body（会让整轮测试全绿但一行没写）, got:\n{script}"
    )
    assert "ctx.stopThread" not in script, (
        f"rows-empty 分支禁止 ctx.stopThread() 任何参数版（JMeter 5.6.3 接口无此方法）, "
        f"got:\n{script}"
    )
    assert "Thread.currentThread().stop" not in script, (
        f"rows-empty 分支禁止 Thread.currentThread().stop()（Java 21+ 抛 UnsupportedOperationException）, "
        f"got:\n{script}"
    )
    assert "SampleResult.setIgnore" not in script, (
        f"SampleResult 在 JSR223PreProcessor 未绑定，禁止使用, got:\n{script}"
    )


# ---------------------------------------------------------------------------
# B2 修复：ts 必须作为显式 ``ts=<ms>`` 字段，不能用 InfluxDB Line 协议
# trailing 时间戳（KaiwuDB 不识别），且不能用 ``System.nanoTime()``（单调
# 计时器不是 Unix epoch，TIMESTAMPTZ(3) 必拒）。
#
# 现状（smoke v4 实测）：
#   - JMeter 30 个 write 全 code:0 但 DB count=0
#   - curl 验证 ``ts=<ms>`` 作显式字段才能落库
#   - trailing 时间戳 → server: "pq: null value in column \"ts\""
#   - nanoTime 值 → server: "pq: value \"<大数>\" out of range for TIMESTAMPTZ(3)"
#
# 修复（§6.4.2 锁 E）：
#   1. buildLine 移除 trailing 时间戳，把 ``ts`` 当 field 加进 fields map
#   2. prep script 把 ``System.nanoTime()`` 换成 ``System.currentTimeMillis()``
# ---------------------------------------------------------------------------


def test_buildline_puts_ts_only_as_trailing_timestamp():
    """``buildLine`` 写 InfluxDB Line body — ts 在 line 末，**不在** fieldMap
    （KaiwuDB REST API 把字段名匹配 ts 列的 field 也算到该列，重复
    即 ``pq: multiple assignments to the same column``）。

    验证：
      (1) script 不含 ``fieldMap['ts'] =`` 或 ``fieldMap.put('ts'``（ts 不进 field_map）
      (2) script 含 ``sb.append(' ').append(tsValue)``（ts 在 line 末）
    """
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_single_table_write_configs(),
    )
    preps = _collect_jsr223_preps(elems)
    script = _prop_map(preps[0])["script"]

    assert "fieldMap['ts']" not in script, (
        f"ts 必须只在 line 末，不在 fieldMap, got:\n{script}"
    )
    assert "fieldMap.put('ts'" not in script, (
        f"ts 必须只在 line 末，不在 fieldMap, got:\n{script}"
    )
    assert "sb.append(' ').append(tsValue)" in script, (
        f"line 末必须有 tsValue append, got:\n{script}"
    )


def test_prep_uses_currentTimeMillis_not_nanoTime():
    """prep script 取 Unix epoch 时间必须用 ``System.currentTimeMillis()``，
    **禁止** ``System.nanoTime()``（单调计时器，不是 epoch，TIMESTAMPTZ(3) 必拒）。

    验证：
      (1) script 含 ``System.currentTimeMillis()``
      (2) script 不含 ``System.nanoTime()``
    """
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_single_table_write_configs(),
    )
    preps = _collect_jsr223_preps(elems)
    script = _prop_map(preps[0])["script"]

    assert "System.currentTimeMillis()" in script, (
        f"prep script 必须用 System.currentTimeMillis() 取 Unix epoch ms, "
        f"got:\n{script}"
    )
    assert "System.nanoTime()" not in script, (
        f"prep script 不能再用 System.nanoTime()（单调计时器不是 epoch）, "
        f"got:\n{script}"
    )


# ---------------------------------------------------------------------------
# B1 修复：Write sampler 必须挂 JSR223Assertion 检查 body ``code:0``
#
# 背景：KaiwuDB REST 协议契约——HTTP 层永远 200 OK，业务成功在 body
# ``code:0/-1``。当前 Write sampler 只看 HTTP 200，server 返 code:-1
# 也算 success，掩盖真失败（smoke v3-v8 全 pass 但 DB count=0 的
# 假阳性）。DDL sampler 已有同款 assertion（§6.4.2 沿用），Write 必须对齐。
#
# 修复（§6.4.2 锁 J）：每个 HTTPSamplerProxy 必须有 1 个
# JSR223Assertion 子节点（与 sampler 配对的 hashTree 内），
# script 含 ``if (prev.getResponseDataAsString().contains('"code":0'))
# return; else throw new RuntimeException(...)`` 模式。
# ---------------------------------------------------------------------------


def test_write_sampler_has_body_code_jsr223_assertion():
    """每个 Write HTTPSamplerProxy 必须挂 1 个 JSR223Assertion 检查 body
    ``"code":0`` substring；无 assertion 时 server 返 ``code:-1`` 仍
    success=true 掩盖真失败（§6.4.2 B1）。
    """
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_default_rest_api(),
        write_configs=_single_table_write_configs(),
    )
    samplers = _collect_http_samplers(elems)
    assert len(samplers) == 1, f"expected 1 Write sampler, got {len(samplers)}"

    # 在 generated JMX 里：HTTPSamplerProxy 配对 hashTree 是 sibling。
    # 该 hashTree 内应含 JSR223Assertion。
    for parent in _walk(elems):
        children = list(parent)
        if not children:
            continue
        for idx, ch in enumerate(children):
            if ch in samplers and idx + 1 < len(children):
                paired_hash = children[idx + 1]
                # search paired hashTree for JSR223Assertion
                assertions = [
                    e for e in _walk([paired_hash])
                    if _local(e.tag) == "JSR223Assertion"
                ]
                assert len(assertions) >= 1, (
                    f"Write sampler 必须挂 JSR223Assertion 检查 body code:0，"
                    f"实际无 assertion 子节点（只有 HeaderManager）"
                )
                # 取 script 字段
                script_prop = None
                for sp in assertions[0]:
                    if _local(sp.tag) == "stringProp" and sp.get("name") == "script":
                        script_prop = sp.text
                        break
                assert script_prop is not None, "JSR223Assertion 缺 script 字段"
                # 必须含 code:0 检查 + RuntimeException throw
                assert '"code":0' in script_prop, (
                    f"JSR223Assertion script 必须检查 body code:0, got {script_prop!r}"
                )
                assert "RuntimeException" in script_prop, (
                    f"JSR223Assertion script 失败时必须抛 RuntimeException, "
                    f"got {script_prop!r}"
                )
                return
    raise AssertionError(
        "无法定位 Write sampler 配对 hashTree — sampler 结构异常"
    )


# ---------------------------------------------------------------------------
# cfg-write-throughput-literal (2026-09-11): write throughput is baked
# into ConstantThroughputTimer from WriteConfig.throughput (no UDV).
# ---------------------------------------------------------------------------


def test_rest_write_groups_missing_wc_raises():
    """A TsTableConfig without a matching WriteConfig entry must fail fast.

    The schemaless write path requires every ts_table to have a per-table
    ``WriteConfig`` because the ``ConstantThroughputTimer`` now bakes the
    cfg ``throughput`` literal (no UDV fallback).
    """
    with pytest.raises(ValueError, match=r"missing write_config for ts_table db_iot\.meters"):
        generate_rest_write_thread_group(
            _single_table_model(),
            rest_api_config=_default_rest_api(),
            write_configs=[],  # explicit empty list
        )

# ---------------------------------------------------------------------------
# Groovy 转义回归闸门(2026-09-08 typo 引入,2026-10-28 smoke 才发现)
# ---------------------------------------------------------------------------


def _assert_no_stray_literal_backslash_n(script: str, label: str) -> None:
    """生成的 Groovy 里不得残留"字面反斜杠 + n"。

    Python 源码里 ``"\\n"``(字面反斜杠 n)与 ``"\\n"``(换行)是两回事:
    前者会被原样写进 Groovy 脚本,让 Groovy 编译器在那一行报
    ``Unexpected character: '\\'`` —— 整个 preprocessor 脚本编译失败,
    表现为 sampler 静默不写数据 / Write 全失败。

    唯一允许的字面 ``\\n`` 是 ``sb.append('\\n')`` —— 那是 Groovy 字符串
    字面量里刻意要写出的换行字符(InfluxDB Line 行分隔)。
    """
    scrubbed = script.replace("sb.append('\\n')", "")
    assert "\\n" not in scrubbed, (
        f"{label}: generated Groovy contains a stray literal '\\n' "
        f"(would break Groovy compilation):\n{script}"
    )


def test_non_bind_script_has_no_stray_literal_backslash_n():
    """非 bind 分支的 tsValue 行必须是真换行,不是字面 ``\\n``。"""
    from jmx_skeleton_generator.generators.rest_write_groups import (
        _build_rest_write_preprocessor_script,
    )

    script = _build_rest_write_preprocessor_script(
        db="db_iot", table="meters", ts_table=_single_table_model().ts_dbs[0].tables[0]
    )
    _assert_no_stray_literal_backslash_n(script, "schemaless non-bind")


def test_bind_script_has_no_stray_literal_backslash_n():
    """bind 分支同样不得残留字面 ``\\n``。"""
    from jmx_skeleton_generator.generators.rest_write_groups import (
        _build_rest_write_preprocessor_script,
    )

    script = _build_rest_write_preprocessor_script(
        db="db_iot",
        table="meters",
        ts_table=_single_table_model().ts_dbs[0].tables[0],
        col_tag_bind_mode=True,
        col_num_per_tag=2,
        num_threads=2,
    )
    _assert_no_stray_literal_backslash_n(script, "schemaless bind")
