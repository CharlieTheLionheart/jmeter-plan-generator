"""REST Query ThreadGroup generators (POST /restapi/query).

Design: openspec/changes/rest-schemaless-write/design.md
Spec:    openspec/changes/rest-schemaless-write/specs/rest-schemaless-write/spec.md §4

For every ``TsTableConfig`` in ``test_model_config.ts_dbs`` this module
emits one JMeter ``ThreadGroup`` whose children are:

- ``ConstantThroughputTimer``  (literal float ``query_throughput``,
  from ``throughput_control.generate_query_timer``)
- ``HTTPSamplerProxy``         (P0-B: POST + raw body + HeaderManager;
  body = ``select count(*) from <db>.<table>;`` baked at generation
  time — no PreProcessor needed)
- ``JSONPostProcessor``        ($.rows → ${rows}; A2 private copy —
  ddl_setup.py version hardcodes ``$.token`` and §2 file is off-limits)
- ``JSR223Assertion``          (Groovy: ``vars.get('rows').toInteger()
  >= <expected_rows>``; private helper — reuses the §2 JSR223Assertion
  element shape but with a different script body)

This module deliberately does NOT touch ``primary_tag`` columns: the
round-trip query is a ``count(*)`` over the whole measurement, so the
assertion only checks the ``rows`` field. P0 fixture (spec §9.3) sets
``expected_rows=1``; callers may raise it to e.g. ``num_threads *
device_per_thread * iterations`` for tighter SLAs.

Section-level design decisions live in ``.superpowers/sdd/task-4-brief.md``
sections A-H and are NOT repeated here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config_parser.models import TestModelConfig
from throughput_control import generate_query_timer
from utils.xml_helpers import (
    empty_hash_tree,
    http_request_sampler_element,
    make_element,
    string_prop,
    thread_group_element,
)


# JSR223 Assertion Groovy script template (Groovy syntax — JMeter JSR223).
# The ``{{expected_rows}}`` doubled-brace placeholder is baked at generation
# time via ``str.format(...)``: doubling escapes Groovy literal braces so
# ``.format()`` only sees the one named field. We do NOT leave the threshold
# as a JMeter variable reference: callers always know ``expected_rows`` at
# generation time, so baking is both simpler and avoids the
# ``${...}`` → default-value pitfall (cf. F-15).
_QUERY_RESPONSE_ASSERTION_SCRIPT = (
    "if (vars.get('data') == null) {literal_open}\n"
    "    throw new RuntimeException(\"Query response missing 'data' field\")\n"
    "{literal_close}\n"
    "int actual = vars.get('data').size()\n"
    "int expected = {expected_rows}\n"
    "if (actual >= {expected_rows}) {literal_open}\n"
    "    return\n"
    "{literal_close} else {literal_open}\n"
    "    throw new RuntimeException(\"Query data rows \" + actual + \" < expected \" + {expected_rows})\n"
    "{literal_close}\n"
)


def _build_json_extractor_element(
    name: str,
    testname: str,
    *,
    reference_name: str,
    jsonpath_expr: str,
    match_numbers: str = "1",
) -> Any:
    """构造 ``<JSONPostProcessor>`` 元素，参数化 reference / jsonpath。

    A2 私有副本：``ddl_setup._build_json_extractor_element`` 硬编码
    ``$.token`` → ``${token}``，§4 需要从响应 JSON 抽取任意字段
    （这里固定 ``$.rows`` → ``${rows}``）。§2 文件保持不动以维持
    §2 commit 边界纯净；重复 ~20 行可接受，P1+ 可重构到 ``xml_helpers``。
    """
    return make_element(
        "JSONPostProcessor",
        name=name,
        testname=testname,
        attributes={
            "guiclass": "JSONPostProcessorGui",
            "testclass": "JSONPostProcessor",
            "enabled": "true",
        },
        children=[
            string_prop("JSONPostProcessor.referenceNames", reference_name),
            string_prop("JSONPostProcessor.jsonPathExprs", jsonpath_expr),
            string_prop("JSONPostProcessor.match_numbers", match_numbers),
        ],
    )


def _build_jsr223_assertion_element(name: str, testname: str, script: str) -> Any:
    """构造 ``<JSR223Assertion>`` 元素（scriptLanguage=groovy）。

    私有副本：与 ``ddl_setup._build_jsr223_assertion_element`` 同形，
    但 JMX 命名空间下没有共享 helper；§4 单独维护一份以保持 §2 文件
    边界纯净。脚本内容互异（DDL 校验 ``code:0``；Query 校验 ``rows``
    数值），不抽共用函数。
    """
    return make_element(
        "JSR223Assertion",
        name=name,
        testname=testname,
        attributes={
            "guiclass": "TestBeanGUI",
            "testclass": "JSR223Assertion",
            "enabled": "true",
        },
        children=[
            string_prop("cacheKey", "true"),
            string_prop("filename", ""),
            string_prop("parameters", ""),
            string_prop("script", script),
            string_prop("scriptLanguage", "groovy"),
        ],
    )


def generate_rest_query_thread_group(
    test_model_config: TestModelConfig,
    rest_api_config: Dict[str, Any],
    *,
    name: str = "REST Query Round-Trip",
    query_throughput: float = 1.0,
    expected_rows: int = 1,
) -> List:
    """Generate one ThreadGroup per TsTableConfig, each with:

    - ConstantThroughputTimer (literal float ``query_throughput``)
    - HTTPSamplerProxy (P0-B POST + HeaderManager,
      body = ``select count(*) from <db>.<table>;``)
    - JSONPostProcessor (``.rows`` → ``${rows}``)
    - JSR223Assertion (``${rows} >= expected_rows`` via Groovy)

    Parameters
    ----------
    test_model_config:
        TestModelConfig instance; iterated over
        ``test_model_config.ts_dbs`` (list of TsDbConfig), then each
        ``TsDbConfig.tables`` (list of TsTableConfig). Each TsTableConfig
        produces 1 ThreadGroup. Skip ts_dbs when empty.
    rest_api_config:
        Required keys: ``query_url_path`` (default caller convention:
        ``/restapi/query``), ``ca_cert_path`` (TLS 模式强制；2026-07-27
        起 insecure 路径移除：schemaless Login 需非空密码用户，非空密码用户
        只能通过安全模式创建）。Optional: ``pre_create_tables`` — Query TG
        is NOT skipped on its value (the field belongs to the DDL SetupTG,
        not the Query TG).
    name:
        ThreadGroup display name prefix (default ``"REST Query Round-Trip"``).
    query_throughput:
        Literal float QPS for ConstantThroughputTimer (default 1.0).
        Passed verbatim to ``throughput_control.generate_query_timer`` —
        NOT routed through any UDV (round-trip verification keeps
        per-TG literal throughput per spec §9.3).
    expected_rows:
        Minimum expected row count baked into the JSR223Assertion
        script (default 1). P0 §9.3 fixture passes 1 ("any data present
        = pass"); tighter callers pass
        ``num_threads * device_per_thread * iterations``.

    Returns
    -------
    Flat list ``[ThreadGroup, hashTree, ThreadGroup, hashTree, ...]``
    with one TG per TsTableConfig. Empty list when ``ts_dbs`` is empty.
    """
    ssl_context: Optional[str] = "${__P(rest_api.ca_cert_path,)}"
    query_url_path = rest_api_config["query_url_path"]
    protocol = "https"

    headers = {
        "Content-Type": "text/plain",
        "Accept": "application/json",
        "Authorization": "Basic ${__property(rest_token)}",
    }

    out: List = []
    if not test_model_config.ts_dbs:
        return out

    # Bake expected_rows once; assertion script template uses one placeholder.
    # Groovy literal braces are emitted via two named placeholders
    # (``literal_open`` / ``literal_close``) so we don't collide with the
    # ``{expected_rows}`` numeric placeholder.
    baked_script = _QUERY_RESPONSE_ASSERTION_SCRIPT.format(
        expected_rows=expected_rows,
        literal_open="{",
        literal_close="}",
    )

    for ts_db in test_model_config.ts_dbs:
        for ts_table in ts_db.tables:
            # Qualified measurement name: KaiwuDB SQL allows ``<db>.<table>``
            # (see task-4-brief.md §E). Each TG owns one measurement; the
            # count(*) covers the whole table and is independent of ptag.
            measurement = f"{ts_db.name}.{ts_table.name}"
            body = f"select count(*) from {measurement};"

            sampler_name = f"REST_Query_{ts_table.name}"
            sampler, sampler_hash = http_request_sampler_element(
                method="POST",
                path=query_url_path,
                headers=headers,
                body=body,
                ssl_context=ssl_context,
                name=sampler_name,
                testname=sampler_name,
            )
            # Insert domain / port / protocol (http_request_sampler_element
            # does not emit these — see Task 1 contract §"协议 / 端口 / 域名由调用方注入").
            sampler.insert(0, string_prop("HTTPSampler.domain", "${__P(rest_api.hostname,127.0.0.1)}"))
            sampler.insert(0, string_prop("HTTPSampler.port", "${__P(rest_api.http_port,8080)}"))
            sampler.insert(0, string_prop("HTTPSampler.protocol", protocol))

            # JSONPostProcessor: $.rows → ${rows}. Reference variable name
            # is exactly ``rows`` (not ``<table>_rows``) because the
            # assertion script uses ``vars.get('rows')`` literal.
            extractor = _build_json_extractor_element(
                name=f"{sampler_name}_data",
                testname=f"{sampler_name}_data",
                reference_name="data",
                jsonpath_expr="$.data",
            )

            # JSR223Assertion: vars.get('rows').toInteger() >= expected_rows.
            # expected_rows is BAKED into the Groovy script literal at
            # generation time — do not route through any UDV (cf. F-15).
            assertion = _build_jsr223_assertion_element(
                name=f"{sampler_name}_assert",
                testname=f"{sampler_name}_assert",
                script=baked_script,
            )

            timer, timer_hash = generate_query_timer(
                query_throughput=float(query_throughput),
            )

            # JSONPostProcessor + JSR223Assertion 必须挂在 HTTPSamplerProxy 的
            # 配对 hashTree (sampler_hash) 内 —— 与 HeaderManager 同一约定
            # (ref doc §HTTPSamplerProxy: post-processor / assertion 作为
            # sampler 配对 hashTree 的子节点)。放在 TG 级会被 JMeter 5.x 忽略，
            # 导致既不抽取 rows 也不跑断言。sampler_hash 已含 HeaderManager +
            # 其配对 hashTree；这里把 extractor / assertion 追加为其兄弟子节点。
            sampler_hash.append(extractor)
            sampler_hash.append(empty_hash_tree())
            sampler_hash.append(assertion)
            sampler_hash.append(empty_hash_tree())

            tg_name = f"{name}_{ts_table.name}"
            tg_testname = f"[{name}] {ts_table.name}"
            tg, tg_hash = thread_group_element(
                name=tg_name,
                testname=tg_testname,
                num_threads=1,
                ramp_time=1,
                duration="${test_duration}",
                loops="-1",
                scheduler=True,
                children=[
                    timer, timer_hash,
                    sampler, sampler_hash,
                ],
            )
            out.extend([tg, tg_hash])

    return out


__all__ = ["generate_rest_query_thread_group"]