"""REST Write ThreadGroup generators (InfluxDB Line via HTTPSamplerProxy).

Design: openspec/changes/rest-schemaless-write/design.md
Spec:    openspec/changes/rest-schemaless-write/specs/schemaless-write/spec.md

For every ``TsTableConfig`` in ``test_model_config.ts_dbs`` this module
emits one JMeter ``ThreadGroup`` whose children are:

- ``ConstantThroughputTimer``  (write_throughput UDV; reused from
  ``throughput_control.generate_write_timer``)
- ``JSR223PreProcessor``       (per-row InfluxDB Line builder; helpers
  ``escapeLineValue`` / ``escapeTagValue`` / ``formatFieldValue`` /
  ``buildLine`` are emitted inline so each measurement is independent)
- ``HTTPSamplerProxy``         (P0-B: POST + raw body + HeaderManager;
  ``body=${request_body}`` — runtime variable reference, never baked)

The Groovy script reads rows + column names from
``JMeterUtils.getJMeterProperties()`` (global properties) under the keys
``__SHARED_MEM_{db}_{table}`` and ``__SHARED_MEM_{db}_{table}_columns``
populated by the shared-memory loader.

Note on ``throughput_qps``: the existing
``throughput_control.generate_write_timer`` signature has no
``throughput_qps`` kwarg and uses the literal ``${write_throughput}``
UDV. To keep this task scope-tight (no edits to ``throughput_control/``)
``throughput_qps`` is reserved for future use; an integer value logs a
warning and is otherwise ignored — callers should pass
``-Jwrite_throughput=N`` on the JMeter CLI.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config_parser.models import TestModelConfig
from seed_data_generator.reference import iter_table_columns
from throughput_control import generate_write_timer
from utils.xml_helpers import (
    http_request_sampler_element,
    jsr223_preprocessor_element,
    string_prop,
    thread_group_element,
    empty_hash_tree,
    make_element,
)


logger = logging.getLogger(__name__)


# §6.4.2 B1: JSR223Assertion 构造器 — 与 ddl_setup 同款，独立 copy 避免
# 跨模块 import 干扰生成器抽象。
def _build_write_jsr223_assertion(name: str, testname: str, script: str):
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


# ---------------------------------------------------------------------------
# InfluxDB Line Groovy helpers (emitted inline per measurement)
#
# escape rules per kaiwudb-schemaless-write-reference §5.2:
#   - tag value: escape ',' / '=' / ' '
#   - field key: escape ',' / '=' / ' '
#   - field value: numbers → bare literal, strings → quoted + escape '"' / '\\'
#   - measurement: always double-quoted
# ---------------------------------------------------------------------------

_GROOVY_HELPERS = (
    "def escapeLineValue(s) { "
    "s.replaceAll('\\\\\\\\', '\\\\\\\\\\\\\\\\').replaceAll(',', '\\\\\\\\,').replaceAll('=', '\\\\\\\\=').replaceAll(' ', '\\\\\\\\ ') "
    "}\n"
    "def escapeTagValue(s) { "
    "s.replaceAll(',', '\\\\\\\\,').replaceAll('=', '\\\\\\\\=').replaceAll(' ', '\\\\\\\\ ') "
    "}\n"
    "def formatFieldValue(v) {\n"
    "    if (v == null) { return '' }\n"
    "    if (v instanceof Number || v instanceof Boolean) { return v.toString() }\n"
    "    def s = v.toString()\n"
    "    if (s == 'true' || s == 'false') { return s }\n"
    "    if (s ==~ /^-?\\d+$/) { return s }\n"
    "    if (s ==~ /^-?\\d+\\.\\d+([eE][-+]?\\d+)?$/) { return s }\n"
    "    if (s ==~ /^-?\\d+[eE][-+]?\\d+$/) { return s }\n"
    "    return '\"' + s.replaceAll('\\\\\\\\', '\\\\\\\\\\\\\\\\').replaceAll('\"', '\\\\\\\\\"') + '\"'\n"
    "}\n"
    "def buildLine(measurement, tags, fields) {\n"
    "    if (fields.isEmpty()) { throw new RuntimeException('buildLine: empty fields, skipping row') }\n"
    "    def sb = new StringBuilder()\n"
    "    sb.append(measurement)\n"
    "    tags.each { k, v -> sb.append(',').append(k).append('=').append(v) }\n"
    "    sb.append(' ')\n"
    "    boolean first = true\n"
    "    fields.each { k, v ->\n"
    "        if (!first) sb.append(',')\n"
    "        sb.append(k).append('=').append(v)\n"
    "        first = false\n"
    "    }\n"
    "    return sb.toString()\n"
    "}\n"
)


def _build_rest_write_preprocessor_script(
    db: str,
    table: str,
    ts_table: Any,
) -> str:
    """Compose the Groovy script for one measurement's PreProcessor.

    The script:

    1. Loads ``rows`` and ``columns`` from JMeter global properties (keys
       populated by the shared-memory loader).
    2. Pops one row per iteration (so threads consume distinct rows
       when the pool is large enough).
    3. Splits columns by group baked by the generator (``ptagNames``,
       ``tagNames``, ``fieldNames`` sets).
    4. Calls the inline helpers ``escapeTagValue`` / ``formatFieldValue``
       / ``buildLine`` to assemble one InfluxDB Line.
    5. Stores the line in ``vars.put('request_body', line)`` for the
       subsequent HTTPSamplerProxy to read.
    """
    ptag_names: List[str] = []
    tag_names: List[str] = []
    field_names: List[str] = []
    for _index, name, _col, group, _base_type in iter_table_columns(ts_table):
        if group == "primary_tags":
            ptag_names.append(name)
        elif group == "regular_tags":
            tag_names.append(name)
        else:
            field_names.append(name)

    ptag_names_groovy = ", ".join(f'"{n}"' for n in ptag_names)
    tag_names_groovy = ", ".join(f'"{n}"' for n in tag_names)
    field_names_groovy = ", ".join(f'"{n}"' for n in field_names)

    return (
        "// === helpers (per-measurement inline) ===\n"
        f"{_GROOVY_HELPERS}\n"
        "// === measurement-specific constants ===\n"
        f'def db = "{db}"\n'
        f'def measurement = "{table}"\n'
        f'def rowsKey = "__SHARED_MEM_{db}_{table}"\n'
        f'def colsKey = "__SHARED_MEM_{db}_{table}_columns"\n'
        "\n"
        "// === per-iteration body ===\n"
        "def globalProps = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()\n"
        "def rows = globalProps.get(rowsKey) as List\n"
        "def columns = globalProps.get(colsKey) as List\n"
        "if (rows == null || rows.isEmpty() || columns == null) {\n"
        "    // §6.4.2 B5 fix: stop thread instead of sending empty body.\n"
        "    // ctx.stopThread() exists in JMeter 5.6.3 (no args).\n"
        "    log.warn('REST_Write_meters_prep: rows empty (rowsKey=' + rowsKey + '), stopping thread')\n"
        "    ctx.stopThread()\n"
        "    return\n"
        "}\n"
        "def row = rows.remove(0)\n"
        "\n"
        "// === column group classification (baked by generator) ===\n"
        f"def ptagNames = [{ptag_names_groovy}] as Set\n"
        f"def tagNames = [{tag_names_groovy}] as Set\n"
        f"def fieldNames = [{field_names_groovy}] as Set\n"
        "\n"
        "// === assemble tags + fields ===\n"
        "def tagMap = [:]\n"
        "def fieldMap = [:]\n"
        "for (int i = 0; i < columns.size(); i++) {\n"
        "    def name = columns[i]\n"
        "    def value = row[i]\n"
        "    if (name in ptagNames || name in tagNames) {\n"
        "        tagMap[name] = escapeTagValue(value.toString())\n"
        "    } else if (name in fieldNames) {\n"
        "        fieldMap[name] = formatFieldValue(value)\n"
        "    }\n"
        "}\n"
        "\n"
        "def tsMillis = System.currentTimeMillis()\n"
        "fieldMap['ts'] = tsMillis.toLong()\n"
        "\n"
        "// §6.4.2 B7b fix: seed CSV bakes ptag as ${device_code} literal\n"
        "// (JDBC path replaces it inside sampler); schemaless prep must\n"
        "// compute device_id from JMeter property + thread iteration,\n"
        "// then substitute. device_start=1, device_per_thread=2 cycles\n"
        "// device_1, device_2 per iteration.\n"
        "def deviceStart = (globalProps.get('device_start') ?: '1') as int\n"
        "def devicePerThread = (globalProps.get('device_per_thread') ?: '2') as int\n"
        "def iterNum = ctx.getVariables().getIteration() + 1\n"
        "def deviceId = ((iterNum - 1) % devicePerThread) + deviceStart\n"
        "def deviceCode = 'device_' + deviceId\n"
        "tagMap.replaceAll { k, v -> v == '\\${device_code}' ? deviceCode : v }\n"
        "\n"
        "def line = buildLine(measurement, tagMap, fieldMap)\n"
        "vars.put('request_body', line)\n"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_rest_write_thread_group(
    test_model_config: TestModelConfig,
    rest_api_config: Dict[str, Any],
    *,
    name: str = "REST Write",
    throughput_qps: Optional[int] = None,
) -> List:
    """Generate one ThreadGroup per TsTableConfig, each with:

    - ConstantThroughputTimer (write_throughput UDV)
    - JSR223PreProcessor (per-row InfluxDB Line builder)
    - HTTPSamplerProxy (P0-B POST + HeaderManager, body=${request_body})

    Parameters
    ----------
    test_model_config:
        TestModelConfig instance; iterated over
        ``test_model_config.ts_dbs`` (list of TsDbConfig), then each
        ``TsDbConfig.tables`` (list of TsTableConfig). Each TsTableConfig
        produces 1 ThreadGroup. Skip ts_dbs when empty.
    rest_api_config:
        Required keys: ``write_url_path``, ``default_db``, ``ca_cert_path``
        （TLS 模式强制；2026-07-27 起 insecure 路径移除：schemaless Login
        需非空密码用户，非空密码用户只能通过安全模式创建）。
        Optional: ``timezone`` (when set, ``&tz=`` appended to path).
    name:
        ThreadGroup display name prefix (default ``"REST Write"``).
    throughput_qps:
        Reserved for future use. ``None`` uses ``write_throughput`` UDV;
        integer value is currently **ignored** (warning logged) — extend
        ``throughput_control.generate_write_timer`` to honor it. Do not
        modify throughput_control/ in this task.

    Returns
    -------
    Flat list ``[ThreadGroup, hashTree, ThreadGroup, hashTree, ...]``
    with one TG per TsTableConfig. Empty list when ``ts_dbs`` is empty.
    """
    if throughput_qps is not None:
        logger.warning(
            "throughput_qps=%d is currently ignored by "
            "rest_write_groups.generate_rest_write_thread_group "
            "(extend throughput_control.generate_write_timer to honor it); "
            "use -Jwrite_throughput=%d on the JMeter CLI to override the UDV.",
            throughput_qps,
            throughput_qps,
        )

    ssl_context: Optional[str] = "${__P(rest_api.ca_cert_path,)}"
    write_url_path = rest_api_config["write_url_path"]
    default_db = rest_api_config["default_db"]
    timezone = rest_api_config.get("timezone")

    path = f"{write_url_path}?db={default_db}"
    if timezone:
        path = f"{path}&tz={timezone}"

    protocol = "https"

    headers = {
        "Content-Type": "text/plain",
        "Accept": "application/json",
        "Authorization": "Basic ${__property(rest_token)}",
    }

    out: List = []
    if not test_model_config.ts_dbs:
        return out

    for ts_db in test_model_config.ts_dbs:
        for ts_table in ts_db.tables:
            script = _build_rest_write_preprocessor_script(
                db=ts_db.name,
                table=ts_table.name,
                ts_table=ts_table,
            )

            timer, timer_hash = generate_write_timer()

            tg_name = f"{name}_{ts_table.name}"
            tg_testname = f"[{name}] {ts_table.name}"

            prep_name = f"REST_Write_{ts_table.name}_prep"
            preproc, preproc_hash = jsr223_preprocessor_element(
                name=prep_name,
                script=script,
                script_language="groovy",
                testname=prep_name,
                enabled=True,
            )

            sampler_name = f"REST_Write_{ts_table.name}"
            sampler, sampler_hash = http_request_sampler_element(
                method="POST",
                path=path,
                headers=headers,
                body="${request_body}",
                ssl_context=ssl_context,
                name=sampler_name,
                testname=sampler_name,
            )

            # Insert domain / port / protocol (http_request_sampler_element
            # does not emit these — see Task 1 contract §"协议 / 端口 / 域名由调用方注入").
            sampler.insert(0, string_prop("HTTPSampler.domain", "${__P(rest_api.hostname,127.0.0.1)}"))
            sampler.insert(0, string_prop("HTTPSampler.port", "${__P(rest_api.http_port,8080)}"))
            sampler.insert(0, string_prop("HTTPSampler.protocol", protocol))

            # §6.4.2 B1 fix: JSR223Assertion 检查 body ``code:0`` —
            # KaiwuDB REST 协议契约：HTTP 永远 200，业务成功在 body code 字段。
            # 无 assertion 时 server 返 code:-1 也算 success，掩盖真失败。
            assert_script = (
                "if (prev.getResponseDataAsString().contains('\"code\":0')) return;\n"
                "else throw new RuntimeException(\"Write failed: \" + prev.getResponseDataAsString())"
            )
            assert_elem = _build_write_jsr223_assertion(
                name=f"{sampler_name}_assert",
                testname=f"{sampler_name}_assert",
                script=assert_script,
            )
            # 挂在 sampler_hash 内（与 DDL 同款），保证 JMeter 解析为 sibling 配对
            sampler_hash.append(assert_elem)
            sampler_hash.append(empty_hash_tree())

            tg, tg_hash = thread_group_element(
                name=tg_name,
                testname=tg_testname,
                num_threads=1,
                ramp_time=1,
                duration="${test_duration}",
                loops="-1",
                scheduler=True,
                children=[timer, timer_hash, preproc, preproc_hash, sampler, sampler_hash],
            )

            out.extend([tg, tg_hash])

    return out


__all__ = ["generate_rest_write_thread_group"]