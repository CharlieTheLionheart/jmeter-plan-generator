"""Write ThreadGroup generators."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from config_parser.models import TestModelConfig, WriteConfig
from direct_insert_write import (
    create_jdbc_sampler,
    create_jsr223_preprocessor_for_write,
)
from direct_insert_write.preprocessor_generator import (
    _groovy_str_literal,
    _safe_key_token,
)
from direct_insert_write.sql_generator import (
    generate_batch_insert_sql,
    generate_single_insert_sql,
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
from write_strategies import get_strategy

logger = logging.getLogger(__name__)


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
    ptag_index = (
        columns.index(first_ptag_column)
        if first_ptag_column and first_ptag_column in columns
        else -1
    )
    # Map SQL column index → KaiwuDB/JDBC type. Used to decide which
    # cells can be emitted unquoted (numeric / bool) vs. as string
    # literals. Empty list = treat every cell as a string.
    type_list_groovy = (
        "[" + ", ".join(f"'{t.lower()}'" for t in column_types) + "]"
        if column_types
        else "[]"
    )
    script = f"""\
{all_groovy_decls()}

def db = {safe_db}
def table = {safe_table}
def rowsKey = '{rows_key}'
// JSR223's per-context ``props`` is destroyed when SetupThreadGroup ends;
// the SharedMemory loader writes through the global JMeterUtils singleton,
// so the read here must also go through that singleton.
def allRows = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()
    .get(rowsKey) as ArrayList
def columns = [{cols_list}]
def typeList = {type_list_groovy}
def nCols = columns.size()
def ptagIndex = {ptag_index}
def batchLines = {batch_lines}
def devicePerThread = {device_per_thread}
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

def baseTimeKey = 'base_time_' + rowsKey
def batchSeqKey = 'batch_seq_' + rowsKey
if (vars.get(baseTimeKey) == null) {{
    vars.put(baseTimeKey, String.valueOf(System.currentTimeMillis()))
}}
def baseTime = (vars.get(baseTimeKey) as Long)
def batchSeq = vars.get(batchSeqKey) != null ?
    (vars.get(batchSeqKey) as Integer) : 0
vars.put(batchSeqKey, String.valueOf(batchSeq + 1))

def tsFmt = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSSSSSSSS")
def total = allRows.size()

def rows = []
for (int r = 0; r < batchLines; r++) {{
    def srcRow = allRows.get(new Random().nextInt(total))
    def rowCopy = new ArrayList(srcRow)
    long ts = baseTime + batchSeq * msStep + r * (msStep / Math.max(1, batchLines))
    long deviceNumber = calculateDeviceNumber(threadNum as long, localDeviceStart as long, devicePerThread as long, r)
    def values = new ArrayList()
    // columns[0] is the ts column (synthesized at write time, not in CSV).
    // columns[1..] are the CSV columns in their original order. The CSV
    // header may include the first ptag column with the literal
    // ``${{device_code}}`` placeholder — we project over the
    // ptagIndex slot and ignore the CSV cell there.
    for (int c = 0; c < nCols; c++) {{
        if (c == 0) {{
            values.add("'" + tsFmt.format(new java.util.Date(ts)) + "'")
        }} else if (c == ptagIndex) {{
            values.add("'" + deviceIdentifier(deviceNumber) + "'")
        }} else {{
            // c=1 in SQL maps to rowCopy[0], c=2 in SQL maps to rowCopy[1], etc.
            int csvIdx = c - 1
            if (csvIdx < 0 || csvIdx >= rowCopy.size()) {{
                values.add("NULL")
            }} else {{
                def raw = rowCopy.get(csvIdx)
                def s = raw == null ? "" : raw.toString()
                if (s.length() >= 2 && s.startsWith('"') && s.endsWith('"')) {{
                    s = s.substring(1, s.length() - 1)
                }}
                if (s.equalsIgnoreCase("null") || s.isEmpty()) {{
                    values.add("NULL")
                }} else {{
                    // Numeric / bool columns: emit unquoted so KaiwuDB
                    // does not have to coerce a quoted literal
                    // (KaiwuDB rejects ``'62'`` for an INT8 column).
                    def colType = (c < typeList.size()) ? typeList.get(c) : ""
                    def needsQuoting = !(colType == "int2" || colType == "int4" || colType == "int8" || colType == "int" || colType == "tinyint" || colType == "smallint" || colType == "bigint" || colType == "float4" || colType == "float8" || colType == "double" || colType == "float" || colType == "bool" || colType == "boolean")
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

def qualifiedTable = db + "." + table
def colsSql = String.join(", ", columns)
def valuesSql = String.join(", ", rows)
def sql = "insert into " + qualifiedTable + " (" + colsSql + ") values " + valuesSql
vars.put("insert_sql", sql)
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
    if wc.mode == "single_insert":
        # Pre-built SQL (with ``?`` placeholders) is no longer used by the
        # sampler; the preprocessor builds a fully-inlined SQL into
        # ``vars.insert_sql`` and the sampler references ``${insert_sql}``.
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
        )
        preproc, preproc_hash = jsr223_preprocessor_element(
            name=f"DirectInsertPrep-{wc.tbl_name}",
            script=script,
            script_language="groovy",
            cache_key="true",
            testname=f"[Write] {wc.tbl_name} - direct insert preprocessor",
        )
    elif wc.mode == "batch_insert":
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
        )
        preproc, preproc_hash = jsr223_preprocessor_element(
            name=f"DirectInsertPrep-{wc.tbl_name}",
            script=script,
            script_language="groovy",
            cache_key="true",
            testname=f"[Write] {wc.tbl_name} - batch insert preprocessor",
        )
    else:
        raise ValueError(f"_build_direct_insert_components called with mode={wc.mode!r}")
    return sampler, samp_hash, preproc, preproc_hash


def _build_batch_prepared_preprocessor_body(
    table_name: str,
    first_ptag: str,
    batch_lines: int,
    ms_step: int,
) -> str:
    """Compose the Groovy body for the batch_prepared JSR223PreProcessor.

    All per-ThreadGroup values (table_name, first_ptag, batch_lines,
    ms_step) are baked into the script as Groovy literals so the script
    never has to read them from ``vars``. Reading them from a per-group
    ``Arguments`` UDV turned out to be unsafe: JMeter's per-thread
    ``JMeterVariables`` does NOT scope UDV definitions inside a
    ThreadGroup, so when two Write ThreadGroups both define
    ``table_name``/``insert_sql``/``column_types``, the second
    ThreadGroup's thread sees the first ThreadGroup's value
    (regression on 2026-07-20, F-3). Deriving ``table_name`` from
    ``ctx.getThreadGroup().getName()`` and baking the rest in removes
    the UDV dependency entirely.
    """
    # tableName comes from the ThreadGroup's own name (set by the
    # generator: ``Write-{qualified_table}``). This is the JMeter-side
    # identity for the running thread and is never shared.
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

// 基准时间（每个线程首次执行时一次性获取）
if (vars.get("base_time_{_safe_key_token(table_name)}") == null) {{
    vars.put("base_time_{_safe_key_token(table_name)}", String.valueOf(System.currentTimeMillis()))
}}
def baseTime = Long.parseLong(vars.get("base_time_{_safe_key_token(table_name)}"))
def batchSeq = Long.parseLong(vars.get("batch_seq_{_safe_key_token(table_name)}") ?: "0")
def msStep = {ms_step}L

// 设备号计算（本线程负责的设备范围）
def threadNum = ctx.getThreadNum()
def deviceStart = Long.parseLong(vars.get("device_start") ?: "1")
def devicePerThread = Integer.parseInt(vars.get("device_per_thread") ?: "1")
def localDeviceStart = calculateLocalDeviceStart(deviceStart, threadNum, devicePerThread)

def batchRows = new ArrayList<Object[]>()
for (int i = 0; i < batchLines; i++) {{
    def srcRow = sharedRows.get((startIdx + i) % totalRows)
    def rowCopy = srcRow.clone() as Object[]
    // Overwrite the first Primary Tag cell with the device identifier.
    if (ptagIdx >= 0) {{
        rowCopy[ptagIdx] = "device_${{localDeviceStart + (i % devicePerThread)}}".toString()
    }}
    // Build a [ts, *columns] row matching the SQL ``INSERT`` template
    // (which prepends ``ts`` to the column list). The CSV row contains
    // only the non-ts columns in the same order, so the result is
    // ``[ts, *srcRow]``.
    def ts = new java.sql.Timestamp(baseTime + batchSeq * msStep + (long)(i * msStep / batchLines))
    def outRow = new Object[rowCopy.length + 1]
    outRow[0] = ts
    System.arraycopy(rowCopy, 0, outRow, 1, rowCopy.length)
    batchRows.add(outRow)
}}

vars.putObject("__BATCH_ROWS_${{tableName}}", batchRows)
vars.put("batch_seq_{_safe_key_token(table_name)}", String.valueOf(batchSeq + 1))
"""

# Groovy scripts for batch_prepared JSR223Sampler (JDBC batch 执行).
#
# F-1 typed-binding fix: the sampler reads ``vars.get("column_types")``
# (comma-separated, aligned with the INSERT column order — populated
# by ``_build_write_udv``) and dispatches each cell to the matching
# JDBC ``setXxx``. Generic ``setObject(String)`` cannot let the
# KaiwuDB driver infer INT8/FLOAT4, so without this dispatch the
# sampler aborts every batch with ``could not resolve "20" as INT8
# type``. Type buckets:
#   - integer / bigint / smallint / tinyint / int2 / int4 / int8 →
#     ``setLong``
#   - float / float4 / float8 / double / real / numeric / decimal →
#     ``setDouble``
#   - timestamp / timestamptz → ``setTimestamp``
#   - bool / boolean → ``setBoolean``
#   - everything else (varchar, char, …) → ``setString``
#
# The ``column_types`` UDV is OPTIONAL — when missing, the sampler
# falls back to ``setString`` for every cell so unit tests / lightweight
# callers that don't supply a model still get a working (varchar-only)
# sampler. End-to-end smoke callers always supply it via the model.
def _build_batch_prepared_sampler_body(
    table_name: str,
    insert_sql: str,
    column_types: Optional[List[str]] = None,
) -> str:
    """Compose the Groovy body for the batch_prepared JSR223Sampler.

    ``table_name`` is derived from ``ctx.getThreadGroup().getName()``;
    ``insert_sql`` and ``column_types`` are baked in by the generator
    (F-3 UDV-pollution fix).
    """
    column_types_groovy = (
        _groovy_str_literal(",".join(column_types)) if column_types else "''"
    )
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

// Comma-separated type list aligned with INSERT column order. When
// absent, fall back to all-varchar (setString). Numeric cells then
// still work at the JDBC layer because setString(string) coerces
// only for some drivers — KaiwuDB does NOT coerce, so the typed
// list is required for INT8/FLOAT4 columns to resolve.
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
                    // varchar / char / unknown — stringify and bind.
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
) -> str:
    """Compose the Groovy body for the batch_prepared JSR223PreProcessor.

    Prepends :func:`utils.preprocessor_helpers.all_groovy_decls` so
    that ``calculateLocalDeviceStart`` and the rest of the shared
    helpers are visible at runtime. Single source of truth for
    device-number arithmetic — see tasks §2.3.

    All per-ThreadGroup values (table_name, first_ptag, batch_lines,
    ms_step) are baked into the script body so the script does not
    have to read them from ``vars``. F-3 UDV-pollution fix
    (regression on 2026-07-20).
    """
    body = _build_batch_prepared_preprocessor_body(
        table_name=table_name,
        first_ptag=first_ptag,
        batch_lines=batch_lines,
        ms_step=ms_step,
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

        if wc.mode in ("single_insert", "batch_insert"):
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

        if wc.mode not in ("single_prepared", "batch_prepared"):
            # Unknown / future modes (e.g. schemaless) are skipped here;
            # schema-level rejection happens in WriteConfig validator.
            logger.warning(
                "write_groups: skipping %s mode=%s — no handler for this mode",
                wc.tbl_name,
                wc.mode,
            )
            continue

        template = prepared_templates.get(fqn, f"-- placeholder for {wc.tbl_name}")

        # 通过策略注册表决定 sampler 类型与 scriptLanguage；
        # 单插入/批插入/无模式继续交给 SetupThreadGroup 路径，write_groups 不消费。
        strategy = get_strategy(wc.mode)
        sampler_type = strategy.get_sampler_type()
        script_language = strategy.get_config("scriptLanguage", "groovy")
        use_prepared = bool(strategy.get_config("usePrepared", False))

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
                column_types = _resolve_ts_table_metadata(model, fqn)[3]
            except ValueError:
                # table not in model — keep going with defaults
                ms_step = 1000
                first_ptag = "ptag_varchar_1"
                column_types = None
        else:
            ms_step = 1000
            first_ptag = "ptag_varchar_1"
            column_types = None
        udv, udv_hash = _build_write_udv(
            wc, template, ms_step, first_ptag,
            column_types=column_types,
        )

        if sampler_type == "JSR223Sampler":
            # batch_prepared 使用 JSR223Sampler + 预置 Groovy 体（设计文档 §3.6）；
            # 预置体由 strategy 注册表之外的 jmx_skeleton_generator 维护，
            # 体现 write_groups 与 strategy 的协作边界。
            preprocessor, preproc_hash = jsr223_preprocessor_element(
                name=f"batch_prepared-{wc.tbl_name}-pre",
                script=build_batch_prepared_preprocessor_script(
                    table_name=wc.tbl_name,
                    first_ptag=first_ptag,
                    batch_lines=wc.batch_lines,
                    ms_step=ms_step,
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
