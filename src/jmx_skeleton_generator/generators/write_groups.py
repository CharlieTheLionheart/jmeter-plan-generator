"""Write ThreadGroup generators."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from config_parser.models import TestModelConfig, WriteConfig
from direct_insert_write.preprocessor_generator import (
    _groovy_str_literal,
    _safe_key_token,
)
from throughput_control import generate_write_timer
from utils.preprocessor_helpers import all_groovy_decls
from utils.xml_helpers import (
    argument_element,
    collection_prop,
    element_prop,
    jdbc_sampler_element,
    jsr223_preprocessor_element,
    jsr223_sampler_element,
    string_prop,
    thread_group_element,
)

logger = logging.getLogger(__name__)

# Mode → (JMeter sampler tag, JDBC usePrepared flag).
# `prepare` mode (PreparedStatement.addBatch + executeBatch): typed-binding
# dispatch lives in _build_batch_prepared_sampler_body. The sampler is a
# JSR223Sampler regardless of `batch_lines` (1-row vs N-rows is purely a
# business-level batch size; the JMeter-side sampler shape is identical).
_PREPARED_MODE_SAMPLER: Dict[str, Tuple[str, bool]] = {
    "prepare": ("JSR223Sampler", False),
}


# ---------------------------------------------------------------------------
# Inline-SQL preprocessor generator (single_insert / batch_insert)
# ---------------------------------------------------------------------------

def _build_inline_sql_preprocessor_script(
    *,
    db: str,
    table: str,
    columns: List[str],
    first_ptag_column: Optional[str],
    device_per_thread: int,
    column_types: Optional[List[str]] = None,
    ms_step: int = 1000,
    batch_lines: int = 1,
    # col-tag-bind-write (2026-08-05): per-table column-subset INSERT.
    # When ``col_tag_bind_mode=True`` the preprocessor reads the
    # ``__SHARED_MEM_{db}_{table}_bind`` map (SetupTG bind sampler),
    # computes ``group_id = hash(ptag_tuple) mod num_threads``, and
    # emits an inline INSERT that includes only the ptag-bound subset
    # of data columns (plus every explicit NOT NULL data column).
    col_tag_bind_mode: bool = False,
    col_num_per_tag: int = 0,
    num_threads: int = 1,
    not_null_data_cols: Optional[List[str]] = None,
) -> str:
    """Render a Groovy script that builds a fully-inline INSERT statement
    into ``vars.put("insert_sql", ...)``.

    Why inline (vs. ``?`` placeholders):
    - JMeter's ``Update Statement`` JDBC mode does not bind ``?`` to
      ``queryArguments`` — it executes the SQL literally. Inline values
      work in this mode.
    - The ``Prepared Update Statement`` path coerces per-cell types via
      ``queryArgumentsTypes``; KaiwuDB's ``Timestamp.valueOf`` rejects
      the locale-dependent string format that Groovy's
      ``Timestamp.toString()`` emits, so type coercion fails for ts.
    - Inline-substituted single-quoted strings (KaiwuDB implicitly
      casts to TIMESTAMP) sidestep both issues.

    Column mapping:
    - ``columns`` is the full SQL column list with ``ts`` prepended
      (e.g. ``[ts, col_int8_1, ptag_varchar_1]``).
    - The SharedMemory row CSV header does NOT include ``ts`` (it is
      generated at write time). For each SQL column we look up its
      position in the CSV and fetch the cell; ``ts`` and the first
      primary tag are projected (formatted timestamp / device id).
    """
    safe_db = "'" + db.replace("\\", "\\\\").replace("'", "\\'") + "'"
    safe_table = "'" + table.replace("\\", "\\\\").replace("'", "\\'") + "'"
    rows_key = f"__SHARED_MEM_{db}_{table}"
    cols_list = ", ".join(f"'{c}'" for c in columns)
    # write-batch-mode-semantics DCR (2026-08-31): deviceCode is the
    # inline GString `${threadNum}_${d}` (Groovy `JSR223 built-in
    # `ctx.getThreadNum()` + the dpt loop index `d`). We escape both
    # names with `{{name}}` so the surrounding Python f-string
    # does NOT try to resolve them as Python identifiers.
    ptag_index = (
        columns.index(first_ptag_column)
        if first_ptag_column and first_ptag_column in columns
        else -1
    )
    # Map SQL column index → KaiwuDB/JDBC type. Used to decide which
    # cells can be emitted unquoted (numeric / bool) vs. as string
    # literals. Empty list = treat every cell as a string.
    # NOTE: stored in UDV ``column_types`` (comma-separated, line 444),
    # NOT baked as Groovy list literal — 20000 cols would overflow
    # Java/Groovy single-string 65535 char limit. Prep body reads via
    # ``vars.get('column_types').split(',')``.
    # col-tag-bind-write (2026-08-05): bind-mode Groovy branch.
    if col_tag_bind_mode:
        # Single-ptag alignment (commit 4 fix 2): the first ptag IS the
        # device column; both SetupTG and Write TG compute
        # ``deviceCode`` inline.
        ptag_names_groovy = f"'{first_ptag_column}'" if first_ptag_column else "'device_id'"
        not_null_groovy = ", ".join(f"'{c}'" for c in (not_null_data_cols or []))
        bind_rows_key = f"__SHARED_MEM_{db}_{table}_bind"
        safe_bind_db = "'" + db.replace("\\", "\\\\").replace("'", "\\'") + "'"
        safe_bind_table = "'" + table.replace("\\", "\\\\").replace("'", "\\'") + "'"
        return f"""\
{all_groovy_decls()}

def db = {safe_bind_db}
def table = {safe_bind_table}
def rowsKey = '{bind_rows_key}'
def ptagNames = [{ptag_names_groovy}]
def colNumPerTag = {col_num_per_tag}
def numThreads = {num_threads}
def notNullDataCols = [{not_null_groovy}]
def devicePerThread = (vars.get('device_per_thread') as Integer) ?: {device_per_thread}
def msStep = {ms_step}

// write-batch-mode-semantics DCR (2026-08-31) bind branch — same
// shape as the main path: outer dpt for-loop iterates
// `d in [deviceStart, deviceStart + devicePerThread - 1]` so each
// sampler tick covers all devices assigned to the current thread;
// inner rbatch-loop iterates `r in [0, batchLines)` to accumulate
// `batch_lines` rows per device. Total rows per tick =
// `device_per_thread × batch_lines`. The bind map is looked up by
// literal deviceCode (no hash — D-21). ts is the per-tick
// `baseTime + r × msStep` (整步语义 gap #6 fix).
def bindGroups = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()
    .get(rowsKey) as Map
if (bindGroups == null || bindGroups.isEmpty()) {{
    log.warn("DirectInsertPrep: empty bind groups for " + rowsKey)
    vars.put("insert_sql", "SELECT 1")
    return
}}

def threadNum = ctx.getThreadNum()
if (threadNum < 0) {{
    threadNum = (vars.get('__threadNum') as Integer) ?: 0
}}
def deviceStart = (vars.get('device_start') != null ?
    (vars.get('device_start') as Integer) : 1)
// write-batch-mode-semantics DCR (2026-08-31): baseTime MUST be
// re-sampled on every sampler tick — same reasoning as the main path.
def baseTime = System.currentTimeMillis()

def tsFmt = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSSSSSSSS")
def qualifiedTable = db + "." + table

// dpt × batch_lines lines 拼接为 MultiRowInsert 单 SQL（与 main path 一致）。
// dpt 条 deviceCode 用 inline GString（双花括号转义见 shared_memory_setup.py）。
def allSqls = []
for (int d = deviceStart; d < deviceStart + devicePerThread; d++) {{
    // Python f-string double-brace escape outputs the literal Groovy
// GString syntax that the surrounding f-string would otherwise try
// to resolve as Python identifiers.
    def deviceCode = threadNum.toString() + "_" + d.toString()
    def group = bindGroups.get(deviceCode) as Map
    if (group == null) {{
        log.warn("DirectInsertPrep: no group " + deviceCode + " in " + rowsKey)
        continue
    }}
    def colNames = group.get("col_names") as List
    def rowValues = group.get("row_values") as List

    // Column list (LinkedHashSet preserves first-occurrence order).
    def seenLocal = new LinkedHashSet()
    seenLocal.add('ts')
    ptagNames.each {{ seenLocal.add(it) }}
    colNames.each {{ seenLocal.add(it) }}
    notNullDataCols.each {{ colName -> if (colName) seenLocal.add(colName) }}
    def insertCols = seenLocal.toList()

    // Inner loop: batch_lines rows per device (整步 ts gap #6 fix).
    def valsRows = []
    for (int r = 0; r < batchLines; r++) {{
        int rowIdx = new Random().nextInt(rowValues.size())
        def cells = rowValues.get(rowIdx) as List
        // write-batch-mode-semantics DCR (2026-08-31) gap #6 fix: ts
        // is `baseTime + r × msStep` (整步语义 — single SQL covers
        // `batch_lines × msStep` window).
        long ts = baseTime + r * msStep
        def tsStr = "'" + tsFmt.format(new java.util.Date(ts)) + "'"
        def insertVals = [tsStr] + ["'" + deviceCode + "'"] + cells
        notNullDataCols.each {{ colName ->
            if (!colNames.contains(colName)) {{
                insertVals.add("NULL")
            }}
        }}
        valsRows.add("(" + insertVals.join(", ") + ")")
    }}

    def colsSql = insertCols.join(", ")
    def valsSql = valsRows.join(", ")
    allSqls.add("INSERT INTO " + qualifiedTable + " (" + colsSql + ") VALUES " + valsSql)
}}
vars.put("insert_sql", String.join("; ", allSqls))
"""

    script = f"""\
{all_groovy_decls()}

def db = {safe_db}
def table = {safe_table}
def rowsKey = '{rows_key}'
// SetupThreadGroup per-context props 在线程结束时销毁；SharedMemory loader
// 通过 JMeterUtils 全局单例写入，读取也必须经它
def allRows = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()
    .get(rowsKey) as ArrayList
def columns = [{cols_list}]
def typeList = (vars.get('column_types') ?: '').split(',')
def nCols = columns.size()
def ptagIndex = {ptag_index}
def batchLines = {batch_lines}
def devicePerThread = (vars.get('device_per_thread') as Integer) ?: {device_per_thread}
def msStep = {ms_step}

if (allRows == null || allRows.isEmpty()) {{
    log.warn("DirectInsertPrep: shared memory empty for " + rowsKey)
    vars.put("insert_sql", "-- no rows in shared memory")
    return
}}

def threadNum = ctx.getThreadNum()
if (threadNum < 0) {{
    threadNum = (vars.get('__threadNum') as Integer) ?: 0
}}
def localDeviceStart = vars.get('device_start') != null ?
    (vars.get('device_start') as Integer) : 0
// 每个 sampler tick 取一次 baseTime，使本 tick 所有 ts 落在当前 ms 窗口
def baseTime = System.currentTimeMillis()

def tsFmt = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSSSSSSSS")
def total = allRows.size()

def rows = []
// 外层 device_per_thread for：每 device 拼 batch_lines 行；
// 总行数 = device_per_thread × batch_lines（单 SQL MultiRowInsert）
for (int d = localDeviceStart; d < localDeviceStart + devicePerThread; d++) {{
    def deviceCode = threadNum.toString() + "_" + d.toString()
    for (int r = 0; r < batchLines; r++) {{
        // SharedMemory loader 写入的每行是 Object[]（CSV 顺序 cell）
        def srcRow = allRows.get(new Random().nextInt(total)) as Object[]
        // Object[] → List 以便 .get(csvIdx) 索引（ArrayList 无 (Object[]) 构造器）
        def rowCells = srcRow.toList()
        // 整步：每行 ts 间隔一个 msStep，覆盖 batch_lines × msStep 窗口
        long ts = baseTime + (long) r * msStep
        def values = new ArrayList()
        // columns[0] = ts（运行时合成），columns[1..] = CSV 顺序列
        for (int c = 0; c < nCols; c++) {{
            if (c == 0) {{
                values.add("'" + tsFmt.format(new java.util.Date(ts)) + "'")
            }} else if (c == ptagIndex) {{
                values.add("'" + deviceCode + "'")
            }} else {{
                int csvIdx = c - 1
                if (csvIdx < 0 || csvIdx >= rowCells.size()) {{
                    values.add("NULL")
                }} else {{
                    def raw = rowCells.get(csvIdx)
                    def s = raw == null ? "" : raw.toString()
                    // strip CSV 残留引号 + null literal
                    if (s.length() >= 2 && s.startsWith('"') && s.endsWith('"')) {{
                        s = s.substring(1, s.length() - 1)
                    }}
                    if (s.equalsIgnoreCase("null") || s.isEmpty()) {{
                        values.add("NULL")
                    }} else {{
                        // 数值 / bool 列不加引号（KaiwuDB 拒绝 '62' 这种 quoted literal）
                        def colType = (c < typeList.size()) ? typeList.get(c) : ""
                        def needsQuoting = !(colType in ["int2", "int4", "int8", "int",
                                                         "tinyint", "smallint", "bigint",
                                                         "float4", "float8", "double", "real",
                                                         "numeric", "decimal",
                                                         "bool", "boolean"])
                        if (needsQuoting) {{
                            values.add("'" + s.replace("'", "''") + "'")
                        }} else {{
                            values.add(s)
                        }}
                    }}
                }}
            }}
        }}
        rows.add("(" + String.join(", ", values) + ")")
    }}
}}

def qualifiedTable = db + "." + table
def colsSql = String.join(", ", columns)
def valuesSql = String.join(", ", rows)
vars.put("insert_sql", "INSERT INTO " + qualifiedTable + " (" + colsSql + ") VALUES " + valuesSql)
"""
    return script


# ---------------------------------------------------------------------------
# Direct-INSERT metadata resolution
# ---------------------------------------------------------------------------

def _split_qualified_table(fqn: str) -> Tuple[str, str]:
    """Split ``"db.table"`` into ``(db, table)``. Lower-cased."""
    if "." not in fqn:
        raise ValueError(f"write config tbl_name must be qualified 'db.table', got {fqn!r}")
    db, _, table = fqn.partition(".")
    return db.lower(), table.lower()


# Per spec §3 "时序表数据类型" the supported data types are:
# int2 / int4 / int8 / float4 / float8 / bool / char / varchar /
# timestamp / timestamptz. numeric / decimal are NOT supported on
# ts tables (sparse_20k fixture maps them to float8 in the model).
_TYPE_BUCKETS: Dict[str, List[str]] = {
    "col_int8": ["int8", "bigint", "int", "int2", "int4", "tinyint", "smallint"],
    "col_int4": ["int4", "int", "int2", "int8", "bigint", "tinyint", "smallint"],
    "col_int2": ["int2", "smallint", "int", "int4", "int8", "bigint", "tinyint"],
    "col_int1": ["tinyint", "smallint", "int2", "int", "int4", "int8", "bigint"],
    "col_float4": ["float4", "real", "float", "float8", "double"],
    "col_float8": ["float8", "double", "real", "float", "float4"],
    "col_bool": ["bool", "boolean"],
    "col_char": ["char", "varchar"],
    "col_varchar": ["varchar", "char"],
    "col_text": ["text", "varchar"],
    "col_timestamp": ["timestamp", "timestamptz"],
    "col_timestamptz": ["timestamptz", "timestamp"],
}


def _col_name_prefix_type_buckets(
    data_col_names: List[str],
    col_types_by_name: Dict[str, str],
) -> Dict[str, List[str]]:
    """Return column-name prefix → JDBC type bucket list.

    For each data column, strip the trailing ``_<index>`` suffix and
    look up the prefix in :data:`_TYPE_BUCKETS`. If the prefix is
    unknown, fall back to the column's own declared type. The returned
    map contains at most one entry per unique prefix (typically 5-12
    for a ts table) — far smaller than baking the full per-name map
    (sparse_20k's 19998 col_types_by_name would overflow the JVM
    65 KB Groovy method-body limit).
    """
    out: Dict[str, List[str]] = {}
    for col_name in data_col_names:
        u = col_name.rfind("_")
        prefix = col_name[:u] if u > 0 else col_name
        if prefix in out:
            continue
        if prefix in _TYPE_BUCKETS:
            out[prefix] = list(_TYPE_BUCKETS[prefix])
        else:
            out[prefix] = [col_types_by_name.get(col_name, "varchar")]
    return out


def _resolve_ts_table_metadata(
    model: TestModelConfig,
    fqn: str,
) -> Tuple[List[str], Optional[str], Optional[str], List[str]]:
    """Resolve ordered column list + first-p-tag column for a TS table.

    Returns
    -------
    (columns, first_ptag_column, ts_col_jdbc_type, column_types)
        ``columns`` is the SQL column list (ts first); ``first_ptag_column``
        is the name of the first primary tag (or ``None``); ``ts_col_jdbc_type``
        is the upper-cased JDBC type for the ts column; ``column_types``
        is a parallel list of column types aligned with ``columns`` (used
        by the preprocessor to decide quoting for numeric values).
    """
    target_db, target_table = _split_qualified_table(fqn)
    for db in model.ts_dbs:
        if db.name.lower() != target_db:
            continue
        for table in db.tables:
            if table.name.lower() != target_table:
                continue
            ts_name = table.ts_col.name if table.ts_col else "ts"
            ts_jdbc_type = (
                table.ts_col.type.upper() if table.ts_col else None
            )
            first_ptag_name: Optional[str] = None
            if table.primary_tags:
                from column_namer.normalize import normalize_type
                first_ptag_name = f"ptag_{normalize_type(table.primary_tags[0].col_type)}_1"
            from column_namer import ColumnNamer
            namer = ColumnNamer(table)
            all_names, all_types_per_name, _idx = namer()
            columns: List[str] = [ts_name] + list(all_names)
            # ``all_types_per_name`` is already N-aligned with ``all_names``
            # because ColumnNamer allocates each entry into N names and
            # records the entry's base type for every produced name.
            # Rebuilding per group from ``table.{data_cols,primary_tags,
            # regular_tags}`` would re-introduce the under-count bug
            # (regression on 2026-07-17 shig smoke: data_col_count=8,
            # single float4 entry → only 1 type emitted for 8 names).
            column_types: List[str] = (
                [(ts_jdbc_type or "timestamp").lower()]
                + list(all_types_per_name)
            )
            return columns, first_ptag_name, ts_jdbc_type, column_types
    raise ValueError(f"time-series table {fqn!r} not found in model")


def _resolve_ts_ms_step(model: TestModelConfig, fqn: str) -> int:
    """Return ``ts_col.ms_step`` for the resolved time-series table.

    Falls back to ``1000`` when the table has no ``ts_col`` (preserves the
    Groovy-script default in ``BATCH_PREPARED_PREPROCESSOR_BODY``).
    """
    target_db, target_table = _split_qualified_table(fqn)
    for db in model.ts_dbs:
        if db.name.lower() != target_db:
            continue
        for table in db.tables:
            if table.name.lower() != target_table:
                continue
            if table.ts_col is None:
                return 1000
            return table.ts_col.ms_step
    raise ValueError(f"time-series table {fqn!r} not found in model")


def _resolve_first_ptag(model: TestModelConfig, fqn: str) -> str:
    """Return the first Primary Tag's column name for ``fqn``.

    Mirrors the convention used by :func:`_resolve_ts_table_metadata`
    (e.g. ``ptag_varchar_1`` for the first varchar primary tag). Returns
    an empty string when the table has no Primary Tags so the
    preprocessor falls back to its no-ptag path.
    """
    target_db, target_table = _split_qualified_table(fqn)
    for db in model.ts_dbs:
        if db.name.lower() != target_db:
            continue
        for table in db.tables:
            if table.name.lower() != target_table:
                continue
            if not table.primary_tags:
                return ""
            from column_namer.normalize import normalize_type
            return f"ptag_{normalize_type(table.primary_tags[0].col_type)}_1"
    raise ValueError(f"time-series table {fqn!r} not found in model")


def _build_write_udv(
    wc: WriteConfig,
    insert_sql: str,
    ms_step: int,
    first_ptag: str,
    *,
    column_types: Optional[List[str]] = None,
) -> Tuple:
    """Build per-write-ThreadGroup ``<Arguments>`` UDV.

    The prepared-mode Groovy scripts read these UDVs at runtime:
    ``vars.get("table_name")``, ``vars.get("insert_sql")``,
    ``vars.get("batch_lines")``, ``vars.get("ms_step")``,
    ``vars.get("first_ptag")``,
    ``vars.get("column_types")`` (comma-separated, aligned with the
    INSERT column order — used by batch_prepared to dispatch
    ``setLong`` / ``setDouble`` / ``setTimestamp`` / ``setString``
    instead of generic ``setObject``).

    Without this UDV the scripts fail with NPE on the first
    ``.size()`` / lookup call.
    """
    fields = {
        "table_name": wc.tbl_name,
        "insert_sql": insert_sql,
        "batch_lines": str(wc.batch_lines),
        "ms_step": str(ms_step),
        "first_ptag": first_ptag,
        "device_per_thread": str(wc.device_per_thread),
    }
    if column_types:
        # Comma-separated; the sampler does ``.split(',')`` at runtime
        # to index into the type list by column index. Empty list (or
        # ``None``) leaves the sampler to fall back to ``setString`` for
        # every cell — which works only for purely-varchar tables.
        fields["column_types"] = ",".join(column_types)
    arg_props = []
    for key, value in fields.items():
        arg_props.append(
            element_prop(
                name=key,
                element_type="Argument",
                testname=key,
                props=[
                    string_prop("Argument.name", key),
                    string_prop("Argument.value", value),
                    string_prop("Argument.metadata", "="),
                ],
            )
        )
    collection = collection_prop("Arguments.arguments", children=arg_props)
    # JMeter ignores a ConfigTestElement whose ``enabled`` attribute is
    # ``false``; explicitly emit ``enabled="true"`` so per-thread UDVs are
    # actually applied to JMeterVariables before samplers run.
    return argument_element(
        name=f"WriteUDV-{wc.tbl_name}",
        testname=f"[Write UDV] {wc.tbl_name}",
        guiclass="ArgumentsPanel",
        testclass="Arguments",
        props=[collection],
        attributes={"enabled": "true"},
    )


def _build_direct_insert_components(
    wc: WriteConfig,
    columns: List[str],
    first_ptag_column: Optional[str],
    ts_col_jdbc_type: Optional[str] = None,
    column_types: Optional[List[str]] = None,
) -> Tuple:
    """Build (JdbcSampler, hashTree, Jsr223Preprocessor, hashTree) for direct-insert write.

    The sampler uses ``Update Statement`` (NOT Prepared) with
    ``query=${insert_sql}`` and the preprocessor builds a fully
    inline-substituted INSERT statement into ``vars.put("insert_sql", ...)``.
    This sidesteps the JMeter limitation that ``?`` placeholders don't
    bind in ``Update Statement`` mode, and the string-coercion quirks
    of ``PreparedStatement.setObject`` for ``TIMESTAMP`` types.

    Returns four ET elements (sampler + hashTree + preprocessor + hashTree).
    Raises :class:`direct_insert_write.errors.DirectInsertGenerationError`
    on validation failure.
    """
    bind_mode = bool(getattr(wc, "col_tag_bind_mode", False))
    if wc.mode == "direct":
        # `direct` mode: inline SQL string (`INSERT ... VALUES (...), (...)`)
        # assembled by the JSR223PreProcessor and emitted via a
        # JDBCSampler `Update Statement`. `batch_lines` controls whether
        # the SQL emits a single VALUES tuple (=1) or N tuples (MultiRowInsert);
        # the sampler + preprocessor shape is identical regardless of N.
        sampler, samp_hash = jdbc_sampler_element(
            name=f"Write-{wc.tbl_name}",
            query="${insert_sql}",
            data_source="jdbcConfig",
            query_type="Update Statement",
            testname=f"[Write] {wc.tbl_name}",
        )
        db, table = _split_qualified_table(wc.tbl_name)
        script = _build_inline_sql_preprocessor_script(
            db=db,
            table=table,
            columns=columns,
            first_ptag_column=first_ptag_column,
            device_per_thread=wc.device_per_thread,
            column_types=column_types,
            batch_lines=wc.batch_lines,
            col_tag_bind_mode=bind_mode,
        )
        preproc, preproc_hash = jsr223_preprocessor_element(
            name=f"DirectInsertPrep-{wc.tbl_name}",
            script=script,
            script_language="groovy",
            cache_key="true",
            testname=f"[Write] {wc.tbl_name} - direct insert preprocessor",
        )
    else:
        raise ValueError(f"_build_direct_insert_components called with mode={wc.mode!r}")
    return sampler, samp_hash, preproc, preproc_hash


def _build_batch_prepared_bind_preprocessor_body(
    *,
    table_name: str,
    ptag_names: List[str],
    ptag_col_types: List[str],
    col_type_buckets: Dict[str, List[str]],
    batch_lines: int,
    ms_step: int,
    device_per_thread: int,
) -> str:
    """Per-device partial INSERT SQL for batch_prepared + col_tag_bind_mode.

    ``col_type_buckets`` maps a column-name prefix (e.g. ``"col_int8"``)
    to its JDBC type bucket (e.g. ``["int", "int2", "int4", "int8",
    "tinyint", "smallint", "bigint"]``). At runtime the prep body
    inspects each per-device column name, strips the trailing
    ``_<index>`` suffix, and looks up the prefix — this is
    O(prefix_count) baked in (typically 5-9 prefixes for a ts table)
    instead of O(data_col_count) full map. Avoids baking a 20000+ entry
    Groovy map literal that overflows the JVM 65 KB method-body limit
    (groovyjarjarasm MethodTooLargeException at compile time).
    """
    safe_table = table_name.replace("\\", "\\\\").replace("'", "\\'")
    safe_db = "'" + safe_table.split(".", 1)[0].replace("\\", "\\\\").replace("'", "\\'") + "'"
    safe_just_table = "'" + safe_table.split(".", 1)[1].replace("\\", "\\\\").replace("'", "\\'") + "'"
    rows_key = f"__SHARED_MEM_{safe_table.replace('.', '_')}_bind"
    ptag_names_groovy = "[" + ", ".join(f"'{p}'" for p in ptag_names) + "]"
    ptag_col_types_groovy = "[" + ", ".join(f"'{t}'" for t in ptag_col_types) + "]"
    # f-string expressions cannot contain backslashes (Python <3.12) — use
    # double-quoted Groovy literals via the %s format and assemble with str.join.
    bucket_items = ", ".join(
        "'{p}': [{inner}]".format(p=prefix, inner=", ".join('"%s"' % b for b in buckets))
        for prefix, buckets in sorted(col_type_buckets.items())
    )

    return f"""def tableName = '{safe_table}'
def dbName = {safe_db}
def tableOnly = {safe_just_table}
def rowsKey = '{rows_key}'
def ptagNames = {ptag_names_groovy}
def ptagColTypes = {ptag_col_types_groovy}
def colTypeBuckets = [{bucket_items}]
def devicePerThread = (vars.get('device_per_thread') as Integer) ?: {device_per_thread}
def batchLines = {batch_lines}
def msStep = {ms_step}L

def bindGroups = org.apache.jmeter.util.JMeterUtils.getJMeterProperties().get(rowsKey) as Map
if (bindGroups == null || bindGroups.isEmpty()) {{
    log.warn("BatchPreparedBindPrep: bind groups empty for " + rowsKey)
    vars.putObject("__BATCH_PREPS_${{tableName}}", new ArrayList())
    return
}}

def deviceStart = (vars.get('device_start') != null ? (vars.get('device_start') as Long) : 1L)
def threadNum = ctx.getThreadNum()
if (threadNum < 0) {{ threadNum = (vars.get('__threadNum') as Integer) ?: 0 }}
def baseTime = System.currentTimeMillis()

def allPreps = new ArrayList()
def randomGen = new Random()
def qualifiedTable = dbName + "." + tableOnly
for (int d = deviceStart; d < deviceStart + devicePerThread; d++) {{
    def deviceCode = threadNum.toString() + "_" + d.toString()
    def group = bindGroups.get(deviceCode) as Map
    if (group == null) {{
        log.warn("BatchPreparedBindPrep: no row for deviceCode " + deviceCode)
        continue
    }}
    def colNames = group.get("col_names") as List
    def rowValues = group.get("row_values") as List
    def ptagValuesByRow = group.get("ptag_values") as List
    if (ptagValuesByRow == null || ptagValuesByRow.isEmpty()) {{
        ptagValuesByRow = [[deviceCode]]
    }}

    def lookupType = {{ String n ->
        int u = n.lastIndexOf('_')
        String prefix = (u > 0) ? n.substring(0, u) : n
        def buckets = colTypeBuckets.get(prefix) as List
        return (buckets != null && !buckets.isEmpty()) ? buckets.get(0) : 'varchar'
    }}

    def insertCols = ['ts'] + ptagNames + colNames
    def insertColTypes = ['timestamp'] + ptagColTypes + colNames.collect(lookupType)
    def placeholders = (1..insertCols.size()).collect {{ '?' }}.join(', ')
    def sql = "insert into " + qualifiedTable + " (" + insertCols.join(', ') + ") values (" + placeholders + ")"

    def rows = new ArrayList()
    int rowStartIdx = randomGen.nextInt(rowValues.size())
    for (int r = 0; r < batchLines; r++) {{
        int idx = (rowStartIdx + r) % rowValues.size()
        def cells = rowValues.get(idx) as List
        def ptagRow = ptagValuesByRow.get(r % ptagValuesByRow.size()) as List
        if (ptagRow == null) {{ ptagRow = [deviceCode] }}
        def row = new ArrayList()
        row.add(new java.sql.Timestamp(baseTime + (long)(r * msStep)))
        row.add((ptagRow != null && !ptagRow.isEmpty()) ? ptagRow.get(0) : deviceCode)
        for (int i = 0; i < colNames.size(); i++) {{
            row.add((cells != null && i < cells.size()) ? cells.get(i) : null)
        }}
        rows.add(row)
    }}

    allPreps.add([deviceCode: deviceCode, sql: sql, colTypes: insertColTypes, rows: rows])
}}
vars.putObject("__BATCH_PREPS_${{tableName}}", allPreps)
"""




def _build_batch_prepared_preprocessor_body(
    table_name: str,
    first_ptag: str,
    batch_lines: int,
    ms_step: int,
    *,
    col_tag_bind_mode: bool = False,
    device_per_thread: int = 1,
    ptag_names: Optional[List[str]] = None,
    ptag_col_types: Optional[List[str]] = None,
    col_type_buckets: Optional[Dict[str, List[str]]] = None,
) -> str:
    """Compose the Groovy body for the batch_prepared JSR223PreProcessor.

    Per-ThreadGroup values (table_name, first_ptag, batch_lines, ms_step)
    are baked in as Groovy literals — JMeter's per-thread JMeterVariables
    does NOT scope UDV definitions inside a ThreadGroup, so two Write
    ThreadGroups would otherwise read each other's UDVs (F-3).
    """
    if col_tag_bind_mode:
        if not ptag_names or not ptag_col_types or not col_type_buckets:
            raise ValueError(
                "col_tag_bind_mode=True requires ptag_names, ptag_col_types, "
                "and col_type_buckets"
            )
        return _build_batch_prepared_bind_preprocessor_body(
            table_name=table_name,
            ptag_names=ptag_names,
            ptag_col_types=ptag_col_types,
            col_type_buckets=col_type_buckets,
            batch_lines=batch_lines,
            ms_step=ms_step,
            device_per_thread=device_per_thread,
        )
    return f"""// JSR223PreProcessor (groovy): batch_prepared 当前批次数据准备
def tableName = {_groovy_str_literal(table_name)}
// Use the global JMeterProperties singleton — JSR223's per-context
// ``props`` is destroyed when SetupThreadGroup ends, so the SharedMemory
// loader's per-context writes never reach this thread group.
// Note: the key has ``_`` (not ``.``) between db and table because
// JMeter's JMeterProperties splits dotted keys into nested Hashtable
// paths, making them invisible to subsequent ``get`` calls.
def sharedRows = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()
    .get("__SHARED_MEM_" + tableName.replace('.', '_')) as ArrayList
// Column-name list stored alongside the rows (CSV header order minus
// the leading ts column). The SQL ``INSERT`` template adds ``ts`` as
// the first column, so the prepared row must follow:
//   [ts, *columns in CSV order].
// ``firstPtag`` is the column name to overwrite with the device
// identifier; baked in by the generator (F-3 UDV-pollution fix).
def globalProps = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()
def columnNames = globalProps.get("__SHARED_MEM_" + tableName.replace('.', '_') + "_columns") as ArrayList
def firstPtag = {_groovy_str_literal(first_ptag)}
def ptagIdx = (columnNames == null) ? -1 : columnNames.indexOf(firstPtag)

def batchLines = {batch_lines}
def totalRows = sharedRows.size()
def startIdx = (int)(Math.random() * totalRows)

def msStep = {ms_step}L

// 设备号计算（本线程负责的设备范围）
def threadNum = ctx.getThreadNum()
def deviceStart = Long.parseLong(vars.get("device_start") ?: "1")
def devicePerThread = Integer.parseInt(vars.get("device_per_thread") ?: "1")
def localDeviceStart = calculateLocalDeviceStart(deviceStart, threadNum, devicePerThread)
// write-batch-mode-semantics DCR (2026-08-31): baseTime MUST be
// re-sampled on every sampler tick — same reasoning as the main path
// and bind path. batchSeq counter removed.
def baseTime = System.currentTimeMillis()

def batchRows = new ArrayList<Object[]>()
// write-batch-mode-semantics DCR (2026-08-31) gap #1 + dpt for fix:
// outer loop iterates `d in [deviceStart, deviceStart + devicePerThread - 1]`
// and inner loop iterates `i in [0, batchLines)` — same shape as bind
// path: per device, accumulate `batchLines` rows. Total rows per tick
// = `device_per_thread × batch_lines`.
for (int d = deviceStart; d < deviceStart + devicePerThread; d++) {{
    // inline GString — Python f-string double-brace escape outputs
    // the literal Groovy GString syntax.
    def deviceCode = threadNum.toString() + "_" + d.toString()
    for (int i = 0; i < batchLines; i++) {{
        def srcRow = sharedRows.get((startIdx + i) % totalRows)
        def rowCopy = srcRow.clone() as Object[]
        if (ptagIdx >= 0) {{
            rowCopy[ptagIdx] = deviceCode
        }}
        // write-batch-mode-semantics DCR (2026-08-31) gap #6 fix:
        // ts is `baseTime + i × msStep` (整步语义 — single SQL
        // covers `batchLines × msStep` window). Pre-fix used
        // `batchSeq * msStep + i * msStep / batchLines` which
        // accumulated per tick AND averaged time across rows.
        def ts = new java.sql.Timestamp(baseTime + (long)(i * msStep))
        def outRow = new Object[rowCopy.length + 1]
        outRow[0] = ts
        System.arraycopy(rowCopy, 0, outRow, 1, rowCopy.length)
        batchRows.add(outRow)
    }}
}}

vars.putObject("__BATCH_ROWS_${{tableName}}", batchRows)
"""

# Groovy scripts for batch_prepared JSR223Sampler (JDBC batch 执行).
# F-1 typed-binding fix: dispatch each cell to the matching JDBC
# ``setXxx`` because generic ``setObject(String)`` cannot let the
# KaiwuDB driver infer INT8/FLOAT4. Type buckets:
#   int / int2 / int4 / int8 / tinyint / smallint / bigint → setLong
#   float / float4 / float8 / double / real / numeric / decimal → setDouble
#   timestamp / timestamptz → setTimestamp
#   bool / boolean → setBoolean
#   everything else (varchar, char, …) → setString
def _build_batch_prepared_sampler_body(
    table_name: str,
    insert_sql: str,
    column_types: Optional[List[str]] = None,
    col_tag_bind_mode: bool = False,
) -> str:
    """Compose the Groovy body for the batch_prepared JSR223Sampler.

    ``table_name`` is derived from ``ctx.getThreadGroup().getName()``;
    ``insert_sql`` and ``column_types`` are baked in by the generator
    (F-3 UDV-pollution fix).
    """
    if col_tag_bind_mode:
        # Bind mode: per-device partial INSERT. The preprocessor stored
        # ``__BATCH_PREPS_<table>`` as List<Map{deviceCode, sql, colTypes,
        # rows}>. Each device gets its own prepareStatement→addBatch→
        # executeBatch→close cycle so the JDBC driver batch buffer is
        # bounded per-device instead of accumulating the whole tick.
        return f"""// batch_prepared sampler (bind mode: per-device partial INSERT)
import org.apache.jmeter.protocol.jdbc.config.DataSourceElement

def tableName = {_groovy_str_literal(table_name)}
def preps = vars.getObject("__BATCH_PREPS_${{tableName}}") as List
if (preps == null || preps.isEmpty()) {{
    log.warn("No bind preps for " + tableName)
    return
}}

DataSourceElement.getConnection("jdbcConfig").withCloseable {{ conn ->
    for (int d = 0; d < preps.size(); d++) {{
        def prep = preps.get(d) as Map
        def sql = prep.sql as String
        def colTypes = prep.colTypes as List<String>
        def rows = prep.rows as List
        conn.prepareStatement(sql).withCloseable {{ pstmt ->
            for (int r = 0; r < rows.size(); r++) {{
                def row = rows.get(r) as List
                for (int c = 0; c < row.size(); c++) {{
                    def value = row.get(c)
                    if (value == null) {{ pstmt.setObject(c + 1, null); continue }}
                    def type = (c < colTypes.size()) ? (colTypes.get(c) ?: "").trim().toLowerCase() : ""
                    if (type in ["int", "int2", "int4", "int8", "tinyint", "smallint", "bigint"]) {{
                        pstmt.setLong(c + 1, Long.parseLong(value.toString()))
                    }} else if (type in ["float", "float4", "float8", "double", "real", "numeric", "decimal"]) {{
                        pstmt.setDouble(c + 1, Double.parseDouble(value.toString()))
                    }} else if (type in ["timestamp", "timestamptz"]) {{
                        pstmt.setTimestamp(c + 1, value as java.sql.Timestamp)
                    }} else if (type in ["bool", "boolean"]) {{
                        pstmt.setBoolean(c + 1, Boolean.parseBoolean(value.toString()))
                    }} else {{
                        pstmt.setString(c + 1, value.toString())
                    }}
                }}
                pstmt.addBatch()
            }}
            pstmt.executeBatch()
        }}
    }}
}}
"""
    # F-3 UDV-pollution fix: sampler must NOT read column_types from vars.
    # Single Groovy string literal is capped at 65535 chars (Java
    # compiler limit), and 20000+ cols join string overflows. Same chunk
    # strategy as ``insert_sql`` below: split into 16k-char chunks.
    if column_types:
        joined_types = ",".join(column_types)
        type_chunks = [
            _groovy_str_literal(joined_types[start : start + 16_000])
            for start in range(0, len(joined_types), 16_000)
        ]
        column_types_groovy = "[\n        " + ",\n        ".join(type_chunks) + "\n    ].join('')"
    else:
        column_types_groovy = "''"
    insert_sql_chunks = [
        _groovy_str_literal(insert_sql[start : start + 16_000])
        for start in range(0, len(insert_sql), 16_000)
    ]
    insert_sql_literal = "[\n        " + ",\n        ".join(insert_sql_chunks) + "\n    ].join('')"
    return f"""// JSR223Sampler (groovy): batch_prepared JDBC batch 执行
import org.apache.jmeter.protocol.jdbc.config.DataSourceElement

def tableName = {_groovy_str_literal(table_name)}
def insertSql = {insert_sql_literal}
def batchRows = vars.getObject("__BATCH_ROWS_${{tableName}}") as ArrayList<Object[]>

def columnTypes = ({column_types_groovy}).split(',') as List<String>

def rowCount = batchRows.size()
if (rowCount == 0) {{
    log.warn("No batch rows prepared for table ${{tableName}}")
    return
}}

DataSourceElement.getConnection("jdbcConfig").withCloseable {{ conn ->
    conn.prepareStatement(insertSql).withCloseable {{ pstmt ->
        for (int rowIdx = 0; rowIdx < rowCount; rowIdx++) {{
            def row = batchRows.get(rowIdx)
            for (int colIdx = 0; colIdx < row.length; colIdx++) {{
                def value = row[colIdx]
                if (value == null) {{
                    pstmt.setObject(colIdx + 1, null)
                    continue
                }}
                def type = (colIdx < columnTypes.size()) ?
                    (columnTypes.get(colIdx) ?: "").trim().toLowerCase() : ""
                if (type in ["int", "int2", "int4", "int8", "tinyint", "smallint", "bigint"]) {{
                    pstmt.setLong(colIdx + 1, Long.parseLong(value.toString()))
                }} else if (type in ["float", "float4", "float8", "double", "real", "numeric", "decimal"]) {{
                    pstmt.setDouble(colIdx + 1, Double.parseDouble(value.toString()))
                }} else if (type in ["timestamp", "timestamptz"]) {{
                    pstmt.setTimestamp(colIdx + 1, value as java.sql.Timestamp)
                }} else if (type in ["bool", "boolean"]) {{
                    pstmt.setBoolean(colIdx + 1, Boolean.parseBoolean(value.toString()))
                }} else {{
                    pstmt.setString(colIdx + 1, value.toString())
                }}
            }}
            pstmt.addBatch()
        }}
        pstmt.executeBatch()
    }}
}}
"""


def build_batch_prepared_preprocessor_script(
    table_name: str,
    first_ptag: str,
    batch_lines: int,
    ms_step: int,
    *,
    col_tag_bind_mode: bool = False,
    device_per_thread: int = 1,
    ptag_names: Optional[List[str]] = None,
    ptag_col_types: Optional[List[str]] = None,
    col_type_buckets: Optional[Dict[str, List[str]]] = None,
) -> str:
    """Compose the batch_prepared JSR223PreProcessor Groovy body.

    Prepends ``all_groovy_decls()`` for shared helpers.
    """
    body = _build_batch_prepared_preprocessor_body(
        table_name=table_name,
        first_ptag=first_ptag,
        batch_lines=batch_lines,
        ms_step=ms_step,
        col_tag_bind_mode=col_tag_bind_mode,
        device_per_thread=device_per_thread,
        ptag_names=ptag_names,
        ptag_col_types=ptag_col_types,
        col_type_buckets=col_type_buckets,
    )
    return f"{all_groovy_decls()}\n{body}"


def generate_write_thread_groups(
    write_config: List[WriteConfig],
    prepared_templates: Dict[str, str],
    *,
    model: Optional[TestModelConfig] = None,
) -> List:
    """Generate write ThreadGroups for all configured table entries.

    Modes are dispatched to dedicated branches:

    - ``single_insert`` / ``batch_insert``: build a ThreadGroup with a
      JSR223PreProcessor (cell projection) + JDBCSampler (Update Statement
      with ``?`` placeholders bound via ``${param_N}``).
    - ``single_prepared`` / ``batch_prepared``: build a ThreadGroup
      backed by ``prepared_templates`` (JDBCSampler Prepared Update or
      JSR223Sampler JDBC batch).

    The ``single_insert`` / ``batch_insert`` branches require ``model``
    to resolve the table's column list + first primary-tag column. When
    ``model`` is ``None`` these entries are skipped with a logged warning
    (preserves the pre-2026-07-15 contract where ``write_groups`` only
    consumed prepared modes).

    Parameters
    ----------
    write_config:
        All write configuration entries from ``TestConfig``.
    prepared_templates:
        Dictionary mapping ``db.table`` to INSERT template strings (used
        only by ``*_prepared`` modes).
    model:
        Optional :class:`TestModelConfig`; required to render
        ``single_insert`` / ``batch_insert`` ThreadGroups.

    Returns
    -------
    A flat list of elements forming all write ThreadGroups.
    Each ThreadGroup is paired with its ``<hashTree>`` containing the
    throughput timer + sampler (+ preprocessor for batch_prepared /
    direct-insert modes).
    """
    results: List = []

    for wc in write_config:
        fqn = wc.tbl_name.lower()

        if wc.mode == "direct":
            # Direct-INSERT path: requires model metadata.
            if model is None:
                logger.warning(
                    "write_groups: skipping %s mode=%s — model is None; "
                    "pass TestModelConfig to render direct-insert thread groups",
                    wc.tbl_name,
                    wc.mode,
                )
                continue
            try:
                columns, first_ptag, ts_jdbc, column_types = _resolve_ts_table_metadata(model, fqn)
            except ValueError as exc:
                logger.warning(
                    "write_groups: cannot resolve columns for %s (%s); skipping",
                    wc.tbl_name,
                    exc,
                )
                continue

            timer, timer_hash = generate_write_timer()
            sampler, samp_hash, preproc, preproc_hash = _build_direct_insert_components(
                wc, columns, first_ptag, ts_col_jdbc_type=ts_jdbc, column_types=column_types,
            )
            tg, tg_hash = thread_group_element(
                name=f"Write-{wc.tbl_name}",
                testname=f"[Write] {wc.tbl_name}",
                num_threads=wc.num_threads,
                ramp_time=1,
                duration="${test_duration}",
                loops="-1",
                scheduler=True,
                children=[timer, timer_hash, preproc, preproc_hash, sampler, samp_hash],
            )
            results.extend([tg, tg_hash])
            continue

        if wc.mode != "prepare":
            # Unknown / future modes (e.g. schemaless) are skipped here;
            # schema-level rejection happens in WriteConfig validator.
            logger.warning(
                "write_groups: skipping %s mode=%s — no handler for this mode",
                wc.tbl_name,
                wc.mode,
            )
            continue

        template = prepared_templates.get(fqn, f"-- placeholder for {wc.tbl_name}")

        # Mode → sampler wiring (see _PREPARED_MODE_SAMPLER).
        # single_insert / batch_insert 走 _build_direct_insert_components 直调
        # direct_insert_write；无模式继续交给 SetupThreadGroup 路径。
        sampler_type, use_prepared = _PREPARED_MODE_SAMPLER[wc.mode]
        script_language = "groovy"

        tg, tg_hash = thread_group_element(
            name=f"Write-{wc.tbl_name}",
            testname=f"[Write] {wc.tbl_name}",
            num_threads=wc.num_threads,
            ramp_time=1,
            duration="${test_duration}",
            loops="-1",
            scheduler=True,
        )

        timer, timer_hash = generate_write_timer()

        # Per-thread-group UDV: prepared-mode Groovy reads
        # ``vars.get("table_name"|"insert_sql"|"batch_lines"|"ms_step")``.
        # Skipping the UDV makes every iteration NPE on the first
        # ``.size()`` / lookup (see review 2026-07-15 smoke run).
        #
        # ``model`` is required to resolve ``ms_step`` (UDV) and the
        # first Primary Tag's column name. When the caller hasn't
        # supplied a model (e.g. lightweight unit tests), fall back to
        # the default ``1000`` ms step and the conventional first-tag
        # name so the ThreadGroup is still generated.
        if model is not None:
            try:
                ms_step = _resolve_ts_ms_step(model, fqn)
                first_ptag = _resolve_first_ptag(model, fqn)
                # ``column_types`` drives the batch_prepared sampler's
                # ``setLong`` / ``setDouble`` / ``setTimestamp`` dispatch
                # (F-1 typed-binding fix). Without it the sampler falls
                # back to ``setString``, which KaiwuDB rejects for
                # INT8 / FLOAT4 columns with
                # ``could not resolve "20" as INT8 type``.
                columns, _first_ptag, _ts_jdbc, column_types = _resolve_ts_table_metadata(
                    model, fqn
                )
            except ValueError:
                # table not in model — keep going with defaults
                ms_step = 1000
                first_ptag = "ptag_varchar_1"
                column_types = None
                columns = None
        else:
            ms_step = 1000
            first_ptag = "ptag_varchar_1"
            column_types = None
            columns = None
        udv, udv_hash = _build_write_udv(
            wc, template, ms_step, first_ptag,
            column_types=column_types,
        )

        # col-tag-bind-write: when bind mode is on, derive per-device
        # prep parameters from the model. ``ptag_names`` / ``ptag_col_types``
        # are the per-ptag list baked into the per-device INSERT. The data
        # column types are bucketed by column-name prefix
        # (e.g. ``col_int8`` → ``["int","int2","int4","int8",...]``) and
        # looked up at runtime — avoids baking a 20000+ entry Groovy map
        # literal that overflows the JVM 65 KB method-body limit
        # (groovyjarjarasm MethodTooLargeException at compile time).
        bind_mode = bool(getattr(wc, "col_tag_bind_mode", False))
        bind_ptag_names: Optional[List[str]] = None
        bind_ptag_col_types: Optional[List[str]] = None
        bind_col_type_buckets: Optional[Dict[str, List[str]]] = None
        if bind_mode and columns is not None and column_types is not None:
            col_types_by_name = dict(zip(columns, column_types))
            ptag_names = [c for c in columns if c.startswith("ptag_")]
            bind_ptag_names = ptag_names
            bind_ptag_col_types = [col_types_by_name.get(p, "varchar") for p in ptag_names]
            bind_col_type_buckets = _col_name_prefix_type_buckets(
                [c for c in columns if not c.startswith("ptag_") and c != "ts"],
                col_types_by_name,
            )

        if sampler_type == "JSR223Sampler":
            preprocessor, preproc_hash = jsr223_preprocessor_element(
                name=f"batch_prepared-{wc.tbl_name}-pre",
                script=build_batch_prepared_preprocessor_script(
                    table_name=wc.tbl_name,
                    first_ptag=first_ptag,
                    batch_lines=wc.batch_lines,
                    ms_step=ms_step,
                    col_tag_bind_mode=bind_mode,
                    device_per_thread=wc.device_per_thread,
                    ptag_names=bind_ptag_names,
                    ptag_col_types=bind_ptag_col_types,
                    col_type_buckets=bind_col_type_buckets,
                ),
                script_language=script_language,
                testname=f"[Write] {wc.tbl_name} - batch_prepared preprocessor",
            )
            sampler, samp_hash = jsr223_sampler_element(
                name=f"Write-{wc.tbl_name}",
                script=_build_batch_prepared_sampler_body(
                    table_name=wc.tbl_name,
                    insert_sql=template,
                    column_types=column_types,
                    col_tag_bind_mode=bind_mode,
                ),
                script_language=script_language,
                testname=f"[Write] {wc.tbl_name}",
            )
            # Children pass into ThreadGroup's hashTree via the
            # ``children=`` argument — JMeter treats them as group
            # members instead of TestPlan siblings.
            inner_children = [
                udv, udv_hash,
                timer, timer_hash,
                preprocessor, preproc_hash,
                sampler, samp_hash,
            ]
            new_tg, new_tg_hash = thread_group_element(
                name=f"Write-{wc.tbl_name}",
                testname=f"[Write] {wc.tbl_name}",
                num_threads=wc.num_threads,
                ramp_time=1,
                duration="${test_duration}",
                loops="-1",
                scheduler=True,
                children=inner_children,
            )
            results.extend([new_tg, new_tg_hash])
        else:
            # single_prepared 走 JDBCSampler；usePrepared 由 strategy 提供。
            sampler, samp_hash = jdbc_sampler_element(
                name=f"Write-{wc.tbl_name}",
                query=template,
                data_source="jdbcConfig",
                query_type="Prepared Update Statement",
                use_prepared=use_prepared,
                testname=f"[Write] {wc.tbl_name}",
            )
            inner_children = [
                udv, udv_hash,
                timer, timer_hash,
                sampler, samp_hash,
            ]
            new_tg, new_tg_hash = thread_group_element(
                name=f"Write-{wc.tbl_name}",
                testname=f"[Write] {wc.tbl_name}",
                num_threads=wc.num_threads,
                ramp_time=1,
                duration="${test_duration}",
                loops="-1",
                scheduler=True,
                children=inner_children,
            )
            results.extend([new_tg, new_tg_hash])

    return results
