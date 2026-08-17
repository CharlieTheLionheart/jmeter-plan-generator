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

from config_parser.models import TestModelConfig, WriteConfig
from seed_data_generator.reference import iter_table_columns
from throughput_control import generate_write_timer
from utils.preprocessor_helpers import all_groovy_decls
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
    # D-22 (2026-08-14): remove dead-code escapeLineValue. It was never
    # invoked anywhere (buildLine only uses sb.append on already-formatted
    # values), and the Python double-escape chain
    # ('\\\\\\\\' → '\\\\\\\\\\\\\\\\') produced an Unescaped trailing
    # backslash in JMeter 5.6.3 Groovy after the numThreads fix exposed
    # the path. formatFieldValue already handles string escaping
    # (quote-wrap + backslash/quote escape inside the else branch) so
    # no protocol-layer escape is needed.
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
    "    // D-22 (2026-08-14): use String.replace (literal) instead of replaceAll\n"
    "    // (regex). The previous chain '\\\\\\\\'→'\\\\\\\\\\\\\\\\' produced\n"
    "    // PatternSyntaxException: Unescaped trailing backslash in JMeter\n"
    "    // 5.6.3 Groovy once the numThreads=2 fix (D-21) exposed this path.\n"
    "    def bs = ((char) 92).toString()\n"
    "    return '\"' + s.replace(bs, bs + bs).replace('\"', bs + '\"') + '\"'\n"
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
    *,
    # col-tag-bind-write (2026-08-05): per-table column-subset bind mode.
    # When ``col_tag_bind_mode=True``, the PreProcessor reads
    # ``__SHARED_MEM_{db}_{table}_bind`` (the bind-namespaced map),
    # computes ``group_id = hash(ptag_tuple) mod num_threads``,
    # picks the per-group ``col_names`` + ``row_values``, and emits
    # InfluxDB Line with only those ``field_set`` entries. The
    # ``tag_set`` retains the first primary tag (device_id); regular
    # tags fall back to runtime defaults (multi-ptag deferred to a
    # follow-up commit — see commit 4 fix 2 notes).
    col_tag_bind_mode: bool = False,
    # D-24 (2026-08-14): spec §4 L327 — each prep emits
    # ``batch_lines`` InfluxDB Lines per call. Default 1 preserves
    # the original per-call single-line behavior.
    batch_lines: int = 1,
    col_num_per_tag: int = 0,
    num_threads: int = 1,
    # Per-table ``WriteConfig.device_per_thread`` baked into the script
    # so the device-N range matches the SetupTG bind sampler (which
    # bakes ``device_per_thread`` into its own Groovy template at
    # generation time); defaults to 1 to align with WriteConfig.
    device_per_thread: int = 1,
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

    Bind mode (``col_tag_bind_mode=True``) takes an early-return path that
    reads ``__SHARED_MEM_{db}_{table}_bind`` and emits a subset-column
    InfluxDB Line. In that path ``num_threads`` and ``device_per_thread``
    are **baked at generation time** (mirrors the SetupTG bind sampler for
    hash-bucket alignment); runtime UDV overrides are NOT supported on
    this path.
    """
    # col-tag-bind-write (2026-08-05): bind-mode early return.
    # Replaces steps 1-5 with: read ``__SHARED_MEM_*_bind``, look up
    # group_id → {col_names, row_values, ptag_values, ptag_names},
    # build tag_map (all ptag baked by SetupTG) + field_map (subset cols)
    # → InfluxDB Line. tag_set keeps all ptag per ref §5.5.
    if col_tag_bind_mode:
        return (
            f"{all_groovy_decls()}\n"
            "// === helpers (per-measurement inline) ===\n"
            f"{_GROOVY_HELPERS}\n"
            "// === measurement-specific constants (bind mode) ===\n"
            f'def db = "{db}"\n'
            f'def measurement = "{table}"\n'
            f'def rowsKey = "__SHARED_MEM_{db}_{table}_bind"\n'
            f'def numThreads = {num_threads}\n'
            f'def devicePerThread = {device_per_thread}\n'
            "\n"
            "def globalProps = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()\n"
            "def bindGroups = globalProps.get(rowsKey) as Map\n"
            "if (bindGroups == null || bindGroups.isEmpty()) {\n"
            "    log.warn('REST_Write_bind_prep: bind groups empty (rowsKey=' + rowsKey + '), stopping thread')\n"
            "    // D-12 (2026-08-11): JMeter 5.6.3 has no JMeterContext.stopThread().\n"
            "    // on Java 21+ — silently exit with empty body so B1 assertion catches it.\n"
            "    vars.put('request_body', '')\n"
            "    return\n"
            "    return\n"
            "}\n"
            "\n"
            "// === deviceCode mirrors SetupTG bind sampler (commit 4 fix 2) ===\n"
            "// ``device_per_thread`` is baked at generation time so the device-N\n"
            "// range matches the SetupTG sampler (which also bakes it).\n"
            "def deviceStart = (globalProps.get('device_start') ?: '1') as int\n"
            "def threadNum = ctx.getThreadNum()\n"
            "if (threadNum < 0) { threadNum = (vars.get('__threadNum') as Integer) ?: 0 }\n"
            "long deviceNumber = calculateDeviceNumber(threadNum as long, deviceStart as long, devicePerThread as long, 0)\n"
            "def deviceCode = deviceIdentifier(deviceNumber)\n"
            "\n"
            "// === per-deviceCode row dict lookup (D-21) ===\n"
            "// D-21 (2026-08-14): no Object.hash call anywhere — key is the\n"
            "// literal deviceCode. SetupTG baked one entry per deviceCode\n"
            "// (no aggregation, no collisions).\n"
            "def group = bindGroups.get(deviceCode) as Map\n"
            "if (group == null) {\n"
            "    log.warn('REST_Write_bind_prep: no row for deviceCode ' + deviceCode + ' in ' + rowsKey + ', stopping thread')\n"
            "    // D-12 (2026-08-11): JMeter 5.6.3 has no JMeterContext.stopThread().\n"
            "    // on Java 21+ — silently exit with empty body so B1 assertion catches it.\n"
            "    vars.put('request_body', '')\n"
            "    return\n"
            "}\n"
            "def colNames = group.get('col_names') as List\n"
            "def rowValues = group.get('row_values') as List\n"
            "def ptagNames = group.get('ptag_names') as List\n"
            "def ptagValues = group.get('ptag_values') as List\n"
            "\n"
            "// === assemble batch_lines InfluxDB Lines per spec §4 L327 ===\n"
            "// D-24 (2026-08-14): build ``batch_lines`` lines per prep call.\n"
            "// Each line picks one of the (single) row entries from this\n"
            "// deviceCode's row pool; wrap-around at pool end (cyclic fill).\n"
            "int batchLines = " + str(batch_lines) + "\n"
            "def rowPoolSize = rowValues.size()\n"
            "def ptagPoolSize = ptagValues.size()\n"
            "int rowStartIdx = new Random().nextInt(rowPoolSize)\n"
            "def sb = new StringBuilder()\n"
            "for (int b = 0; b < batchLines; b++) {\n"
            "    int idx = (rowStartIdx + b) % rowPoolSize\n"
            "    def cells = rowValues.get(idx) as List\n"
            "    def ptagCells = ptagValues.get(idx % ptagPoolSize) as List\n"
            "    def tagMap = [:]\n"
            "    for (int p = 0; p < ptagNames.size(); p++) {\n"
            "        tagMap[ptagNames[p]] = escapeTagValue(ptagCells[p].toString())\n"
            "    }\n"
            "    def fieldMap = [:]\n"
            "    for (int i = 0; i < colNames.size(); i++) {\n"
            "        fieldMap[colNames[i]] = formatFieldValue(cells[i])\n"
            "    }\n"
            "    fieldMap['ts'] = (System.currentTimeMillis() + b) as long\n"
            "    if (b > 0) { sb.append('\\n') }\n"
            "    sb.append(buildLine(measurement, tagMap, fieldMap))\n"
            "}\n"
            "vars.put('request_body', sb.toString())\n"
        )

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
        "    // D-12 (2026-08-11): JMeter 5.6.3 has no JMeterContext.stopThread().\n"
        "    // on Java 21+ — silently exit with empty body so B1 assertion catches it.\n"
        "    // D-23 (2026-08-14): this safety-net stays even though D-23\n"
        "    // restores spec §4 cyclic-fill (random start + wrap-around), so\n"
        "    // rows.isEmpty() should never trigger in normal config.\n"
        "    log.warn('REST_Write_meters_prep: rows empty (rowsKey=' + rowsKey + '), stopping thread')\n"
        "    vars.put('request_body', '')\n"
        "    return\n"
        "}\n"
        "// D-23/D-24 (2026-08-14): spec §4 L327 cyclic-fill — row pool is\n"
        "// never popped (only read by index), so batch_lines prep calls\n"
        "// all succeed even after the seed pool is exhausted. The batch\n"
        "// body is constructed inside the loop below.\n"
        "\n"
        "// === column group classification (baked by generator) ===\n"
        f"def ptagNames = [{ptag_names_groovy}] as Set\n"
        f"def tagNames = [{tag_names_groovy}] as Set\n"
        f"def fieldNames = [{field_names_groovy}] as Set\n"
        "\n"
        "// === assemble batch_lines InfluxDB Line bodies per spec §4 L327 ===\n"
        "// D-24 (2026-08-14): build ``batch_lines`` lines per prep call.\n"
        "// Each line picks a different random starting row from the pool;\n"
        "// wrap-around at pool end (cyclic fill per spec §4).\n"
        "int batchLines = " + str(batch_lines) + "\n"
        "def deviceStart = (globalProps.get('device_start') ?: '1') as int\n"
        "def devicePerThread = (globalProps.get('device_per_thread') ?: '2') as int\n"
        "def iterNum = ctx.getVariables().getIteration() + 1\n"
        "// D-26 (2026-08-14): bind path defines threadNum but full-row\n"
        "// path skipped it. Add here so deviceId derives from threadNum.\n"
        "int threadNum = ctx.getThreadNum()\n"
        "if (threadNum < 0) { threadNum = (vars.get('__threadNum') as Integer) ?: 0 }\n"
        "def randomGen = new Random()\n"
        "def sb = new StringBuilder()\n"
        "int rowCursor = randomGen.nextInt(rows.size())\n"
        "for (int b = 0; b < batchLines; b++) {\n"
        "    // Wrap-around: any index 0..rows.size()-1 is valid.\n"
        "    int rowIdx = (rowCursor + b) % rows.size()\n"
        "    def row = rows.get(rowIdx)\n"
        "    def tagMap = [:]\n"
        "    def fieldMap = [:]\n"
        "    for (int i = 0; i < columns.size(); i++) {\n"
        "        def name = columns[i]\n"
        "        def value = row[i]\n"
        "        if (name in ptagNames || name in tagNames) {\n"
        "            tagMap[name] = escapeTagValue(value.toString())\n"
        "        } else if (name in fieldNames) {\n"
        "            fieldMap[name] = formatFieldValue(value)\n"
        "        }\n"
        "    }\n"
        "    def tsMillis = System.currentTimeMillis() + b\n"
        "    fieldMap['ts'] = tsMillis.toLong()\n"
        "    // §6.4.2 B7b fix: seed CSV bakes ptag as ${device_code} literal\n"
        "    // (JDBC path replaces it inside sampler); schemaless prep\n"
        "    // computes device_id from JMeter property + thread iteration.\n"
        "    // D-26 (2026-08-14): use threadNum-derived deviceId so each\n"
        "    // thread writes distinct ptag values within a batch (avoids the\n"
        "    // mod-by-devicePerThread collapse to 0 when devicePerThread=1).\n"
        "    int _tnum = (threadNum != null ? threadNum : 0)\n"
        "    def deviceId = (_tnum * batchLines + b) + deviceStart\n"
        "    def deviceCode = 'device_' + deviceId\n"
        "    tagMap.replaceAll { k, v -> v == '\\${device_code}' ? deviceCode : v }\n"
        "    if (b > 0) { sb.append('\\n') }\n"
        "    sb.append(buildLine(measurement, tagMap, fieldMap))\n"
        "}\n"
        "vars.put('request_body', sb.toString())\n"
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
    # col-tag-bind-write (2026-08-05): when provided, ``write_configs`` is
    # indexed by ``{db}.{table}`` to look up per-table ``col_tag_bind_mode``
    # / ``col_num_per_tag`` / ``device_per_thread`` so the PreProcessor
    # can emit the bind-mode InfluxDB Line subset path. ``None`` (or a
    # table missing from the map) keeps the legacy full-row behavior.
    write_configs: Optional[List[WriteConfig]] = None,
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

    # col-tag-bind-write (2026-08-05): index write_configs by ``db.table``
    # for O(1) per-table lookup.
    write_cfg_by_table: Dict[str, WriteConfig] = {}
    if write_configs:
        for wc in write_configs:
            write_cfg_by_table[wc.tbl_name] = wc

    for ts_db in test_model_config.ts_dbs:
        for ts_table in ts_db.tables:
            fqn = f"{ts_db.name}.{ts_table.name}"
            wc = write_cfg_by_table.get(fqn)
            col_tag_bind_mode = bool(wc and wc.col_tag_bind_mode)
            col_num_per_tag = int(wc.col_num_per_tag) if wc else 0
            num_threads = int(wc.num_threads) if wc else 1
            device_per_thread = int(wc.device_per_thread) if wc else 1
            script = _build_rest_write_preprocessor_script(
                db=ts_db.name,
                table=ts_table.name,
                ts_table=ts_table,
                col_tag_bind_mode=col_tag_bind_mode,
                col_num_per_tag=col_num_per_tag,
                num_threads=num_threads,
                device_per_thread=device_per_thread,
                batch_lines=int(wc.batch_lines) if wc else 1,
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
                num_threads=num_threads,
                ramp_time=1,
                duration="${test_duration}",
                loops="-1",
                scheduler=True,
                children=[timer, timer_hash, preproc, preproc_hash, sampler, sampler_hash],
            )

            out.extend([tg, tg_hash])

    return out


__all__ = ["generate_rest_write_thread_group"]