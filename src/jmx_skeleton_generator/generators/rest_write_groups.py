"""REST Write ThreadGroup generators (InfluxDB Line via HTTPSamplerProxy).

Design: openspec/changes/rest-schemaless-write/design.md
Spec:    openspec/changes/rest-schemaless-write/specs/schemaless-write/spec.md

For every ``TsTableConfig`` in ``test_model_config.ts_dbs`` this module
emits one JMeter ``ThreadGroup`` whose children are:

- ``ConstantThroughputTimer``  (cfg ``wc.throughput`` literal; reused
  from ``throughput_control.generate_write_timer``)
- ``JSR223PreProcessor``       (per-row InfluxDB Line builder; helpers
  ``escapeLineValue`` / ``escapeTagValue`` / ``formatFieldValue`` /
  ``buildLine`` are emitted inline so each measurement is independent)
- ``HTTPSamplerProxy``         (P0-B: POST + raw body + HeaderManager;
  ``body=${request_body}`` — runtime variable reference, never baked)

The Groovy script reads rows + column names from
``JMeterUtils.getJMeterProperties()`` (global properties) under the keys
``__SHARED_MEM_{db}_{table}`` and ``__SHARED_MEM_{db}_{table}_columns``
populated by the shared-memory loader.

Note on ``throughput_qps``: per-table ``WriteConfig.throughput`` is the
source of truth — ``throughput_qps`` is reserved for future use; an
integer value logs a warning and is otherwise ignored.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config_parser.models import MissingConfig, TestModelConfig, WriteConfig
from seed_data_generator.reference import iter_table_columns
from throughput_control import generate_write_timer
from utils.preprocessor_helpers import (
    all_groovy_decls,
    groovy_missing_data_block,
)
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
    "    // D-22 (2026-08-14): 用 String.replace(字面量)而非 replaceAll(正则)\n"
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
    # write-missing-data DCR: 表级缺失配置。None / probability=0 时
    # 不注入任何缺失逻辑(生成结果与未声明该段逐字节一致,见 design D6)。
    missing: Optional[MissingConfig] = None,
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
    # Derive ptag_names / tag_names Groovy literals up-front so both
    # the bind-mode early return and the main path can reference them.
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
    # ts column name follows model ``ts_col.name``; InfluxDB Line Protocol puts it at line tail to avoid server `pq: multiple assignments to the same column`.
    ts_col_name = (
        ts_table.ts_col.name
        if (ts_table is not None and ts_table.ts_col is not None and ts_table.ts_col.name)
        else "ts"
    )

    # write-missing-data DCR: 缺失逻辑块 —— 未声明段 / probability=0 时
    # 为空串,拼接后脚本与改动前逐字节一致(design D6)。
    missing_block = groovy_missing_data_block(missing)
    # 内层循环的跳过判定行 —— 设备循环起点变量是 deviceStart。
    skip_line = ""
    marker_setup = ""
    marker_guard = ""
    if missing_block:
        # schemaless 需要区分"因缺失而空"与"其它原因而空"(D7):前者放行
        # B1 断言,后者仍被捕获 —— 故统计被跳过的格子数。
        skip_line = (
            "        if (applyMissing && skipMissingRow((int)(d - deviceStart), b)) "
            "{ missingSkipped++; continue }\n"
        )
        marker_setup = "int missingSkipped = 0\nvars.remove('__missing_skipped')\n"
        marker_guard = (
            "if (missingSkipped > 0 && sb.length() == 0) "
            "{ vars.put('__missing_skipped', 'true') }\n"
        )

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
            f"def ptagNames = [{ptag_names_groovy}] as Set\n"
            f"def tagNames = [{tag_names_groovy}] as Set\n"
            "\n"
            "def globalProps = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()\n"
            "def bindGroups = globalProps.get(rowsKey) as Map\n"
            "if (bindGroups == null || bindGroups.isEmpty()) {\n"
            "    // write-missing-data D11: 空种子池抛业务异常,不静默降级\n"
            "    throw new RuntimeException(\n"
            "        'SharedMemory pool empty for table ' + db + '.' + measurement\n"
            "            + ' (key ' + rowsKey + '): seed CSV load failed or produced no rows'\n"
            "    )\n"
            "}\n"
            "\n"
            "// === deviceCode = inline GString (matches SetupTG bind sampler) ===\n"
            "// 每 body 共 device_per_thread × batch_lines 行\n"
            "def deviceStart = (globalProps.get('device_start') ?: '1') as int\n"
            "def threadNum = ctx.getThreadNum()\n"
            "if (threadNum < 0) { threadNum = (vars.get('__threadNum') as Integer) ?: 0 }\n"
            "long msStep = " + str(getattr(ts_table.ts_col, "ms_step", 1000) if ts_table is not None and ts_table.ts_col is not None else 1000) + "L\n"
            "long baseTime = System.currentTimeMillis()\n"
            "int batchLines = " + str(batch_lines) + "\n"
            + missing_block
            + marker_setup
            + "def randomGen = java.util.concurrent.ThreadLocalRandom.current()\n"
            "def sb = new StringBuilder()\n"
            "boolean firstLine = true\n"
            "for (int d = deviceStart; d < deviceStart + devicePerThread; d++) {\n"
            "    def deviceCode = threadNum.toString() + \"_\" + d.toString()\n"
            "    def group = bindGroups.get(deviceCode) as Map\n"
            "    if (group == null) {\n"
            "        log.warn('REST_Write_bind_prep: no row for deviceCode ' + deviceCode + ' in ' + rowsKey)\n"
            "        continue\n"
            "    }\n"
            "    def colNames = group.get('col_names') as List\n"
            "    def rowValues = group.get('row_values') as List\n"
            "    def ptagNamesOrdered = group.get('ptag_names') as List\n"
            "    def ptagValuesByRow = group.get('ptag_values') as List\n"
            "    if (ptagValuesByRow == null || ptagValuesByRow.isEmpty()) {\n"
            "        ptagValuesByRow = [[deviceCode]]\n"
            "    }\n"
            "    int rowStartIdx = randomGen.nextInt(rowValues.size())\n"
            "    for (int b = 0; b < batchLines; b++) {\n"
            + skip_line
            + "        int idx = (rowStartIdx + b) % rowValues.size()\n"
            "        def cells = rowValues.get(idx) as List\n"
            "        def ptagCells = ptagValuesByRow.get(idx % ptagValuesByRow.size()) as List\n"
            "        def tagMap = [:]\n"
            "        for (int p = 0; p < ptagNamesOrdered.size(); p++) {\n"
            "            tagMap[ptagNamesOrdered[p]] = escapeTagValue(ptagCells[p].toString())\n"
            "        }\n"
        "        // write-batch-mode-semantics DCR (2026-08-31) gap #2: rtag 列也进 tag_set\n"
            "        for (String tname : tagNames) {\n"
            "            if (!tagMap.containsKey(tname)) { tagMap[tname] = '' }\n"
            "        }\n"
            "        def fieldMap = [:]\n"
            "        for (int i = 0; i < colNames.size(); i++) {\n"
            "            fieldMap[colNames[i]] = formatFieldValue(cells[i])\n"
            "        }\n"
            f"        def tsValue = (baseTime + (long)(b * msStep)) * 1000 * 1000 \n"
            "        if (!firstLine) { sb.append('\\n') }\n"
            "        sb.append(buildLine(measurement, tagMap, fieldMap))\n"
            "        sb.append(' ').append(tsValue)\n"
            "        firstLine = false\n"
            "    }\n"
            "}\n"
            + marker_guard
            + "vars.put('request_body', sb.toString())\n"
        )

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
        "if (rows == null || rows.isEmpty()) {\n"
        "    // write-missing-data D11: 空种子池抛业务异常,不静默降级\n"
        "    throw new RuntimeException(\n"
        "        'SharedMemory pool empty for table ' + db + '.' + measurement\n"
        "            + ' (key ' + rowsKey + '): seed CSV load failed or produced no rows'\n"
        "    )\n"
        "}\n"
        "if (columns == null) {\n"
        "    throw new RuntimeException(\n"
        "        'SharedMemory column header missing for table ' + db + '.' + measurement\n"
        "            + ' (key ' + colsKey + '): seed CSV load failed or produced no rows'\n"
        "    )\n"
        "}\n"
        "// D-23/D-24 (2026-08-14): 行池只按下标读不弹出,种子耗尽后仍能凑满 batch_lines 行\n"
        "\n"
        "// === column group classification (baked by generator) ===\n"
        f"def ptagNames = [{ptag_names_groovy}] as Set\n"
        f"def tagNames = [{tag_names_groovy}] as Set\n"
        f"def fieldNames = [{field_names_groovy}] as Set\n"
        "\n"
        "// === assemble dpt × batch_lines InfluxDB Line bodies ===\n"
        "// 每 body 共 device_per_thread × batch_lines 行;deviceCode 用 inline GString\n"
        "int batchLines = " + str(batch_lines) + "\n"
        "def deviceStart = (globalProps.get('device_start') ?: '1') as int\n"
        "def devicePerThread = (globalProps.get('device_per_thread') ?: '2') as int\n"
        + missing_block
        + marker_setup
        + "int threadNum = ctx.getThreadNum()\n"
        "if (threadNum < 0) { threadNum = (vars.get('__threadNum') as Integer) ?: 0 }\n"
        "long msStep = " + str(getattr(ts_table.ts_col, "ms_step", 1000) if ts_table is not None and ts_table.ts_col is not None else 1000) + "L\n"
        "long baseTime = System.currentTimeMillis()\n"
        "def randomGen = java.util.concurrent.ThreadLocalRandom.current()\n"
        "int rowCursor = randomGen.nextInt(rows.size())\n"
        "def sb = new StringBuilder()\n"
        "boolean firstLine = true\n"
        "for (int d = deviceStart; d < deviceStart + devicePerThread; d++) {\n"
        "    def deviceCode = threadNum.toString() + \"_\" + d.toString()\n"
        "    for (int b = 0; b < batchLines; b++) {\n"
        + skip_line
        + "        int rowIdx = (rowCursor + b) % rows.size()\n"
        "        def row = rows.get(rowIdx)\n"
        "        def tagMap = [:]\n"
        "        def fieldMap = [:]\n"
        "        for (int i = 0; i < columns.size(); i++) {\n"
        "            def name = columns[i]\n"
        "            def value = row[i]\n"
        "            if (name in ptagNames || name in tagNames) {\n"
        "                tagMap[name] = escapeTagValue(value.toString())\n"
        "            } else if (name in fieldNames) {\n"
        "                fieldMap[name] = formatFieldValue(value)\n"
        "            }\n"
        "        }\n"
        f"        def tsValue = (baseTime + (long)(b * msStep)) * 1000 * 1000\n"
        "        tagMap.replaceAll { k, v -> v == '\\${device_code}' ? deviceCode : v }\n"
        "        if (!firstLine) { sb.append('\\n') }\n"
        "        sb.append(buildLine(measurement, tagMap, fieldMap))\n"
        "        sb.append(' ').append(tsValue)\n"
        "        firstLine = false\n"
        "    }\n"
        "}\n"
        + marker_guard
        + "vars.put('request_body', sb.toString())\n"
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

    - ConstantThroughputTimer (cfg ``wc.throughput`` literal)
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
        Reserved for future use. ``None`` uses ``cfg.write_config[].throughput``
        for the per-table write sampler; integer value is currently
        **ignored** (warning logged) — extend this module to honor it.

    Returns
    -------
    Flat list ``[ThreadGroup, hashTree, ThreadGroup, hashTree, ...]``
    with one TG per TsTableConfig. Empty list when ``ts_dbs`` is empty.

    Raises
    ------
    ValueError:
        When a ``TsTableConfig`` from ``test_model_config`` has no
        matching entry in ``write_configs``. The schemaless write path
        requires every ts_table to have a per-table ``WriteConfig``
        because the ``ConstantThroughputTimer`` now bakes the cfg
        ``throughput`` literal (no UDV fallback).
    """
    if throughput_qps is not None:
        logger.warning(
            "throughput_qps=%d is currently ignored by "
            "rest_write_groups.generate_rest_write_thread_group; "
            "the per-table WriteConfig.throughput is the source of truth.",
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
    # write-missing-data D12(b): 建索引与查询统一用小写 —— JDBC 路径早已
    # 用 ``.lower()`` 归一,schemaless 缺这一步会让 cfg 写大写表名时匹配
    # 失败(``missing write_config for ts_table``)。
    write_cfg_by_table: Dict[str, WriteConfig] = {}
    if write_configs:
        for wc in write_configs:
            write_cfg_by_table[wc.tbl_name.lower()] = wc

    for ts_db in test_model_config.ts_dbs:
        for ts_table in ts_db.tables:
            fqn = f"{ts_db.name}.{ts_table.name}".lower()
            wc = write_cfg_by_table.get(fqn)
            if wc is None:
                raise ValueError(
                    f"missing write_config for ts_table {fqn}; "
                    f"rest_write_groups requires every ts_table to have a WriteConfig entry"
                )
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
                missing=(wc.missing if wc else None),
            )

            timer, timer_hash = generate_write_timer(throughput=wc.throughput)

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
            if wc.missing is not None and wc.missing.probability > 0.0:
                # D7 缺整轮:preprocessor 因缺失跳过全部格子时 body 为空,
                # 放行该批次(不判为写入失败);种子数据为空导致的空 body
                # 不置标记,仍被下面的断言捕获。
                assert_script = (
                    "if (vars.get('__missing_skipped') == 'true') return;\n"
                    + assert_script
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