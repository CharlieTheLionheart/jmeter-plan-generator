"""JSR223PreProcessor Groovy script generator for direct-insert write samplers.

Design: openspec/changes/direct-insert-write/design.md
Spec:    openspec/changes/direct-insert-write/specs/direct-insert-write/spec.md

The generated script — write path (single_insert / batch_insert):

1. Reads rows from ``props.get("__SHARED_MEM_{tableName}")`` — design §5.2
   single key, bare table name (e.g. ``__SHARED_MEM_t_cnc``). No companion
   columns key; column order comes from ``table_config['columns']``
   injected at script-emission time.
2. Randomly picks a start row, copies ``batch_lines`` consecutive rows,
   wrapping at the row total.
3. Clones rows via ``cloneRows`` so the shared memory stays untouched.
4. Resolves ``__threadNum`` and computes per-row device numbers via
   :func:`calculateDeviceNumber`.
5. Replaces the first primary tag value with
   ``device_{device_number}`` for every row.
6. Computes per-row timestamps via :func:`calculateTimestamps` and
   exposes the prepared batch to the subsequent ``JDBCSampler`` via
   thread-local ``vars``:

   - ``param_0..param_{N*batch_lines-1}`` — per-cell value strings in
     row-major order (column 0 of row 0, column 1 of row 0, ...,
     column N-1 of row 0, column 0 of row 1, ...). The JDBCSampler's
     ``queryArguments`` references each via ``${param_N}``.

The relational init path emits a *separate* PreProcessor that:

1. Reads column seed files (per-iterator batch index in
   ``__rel_batch_idx``).
2. Assembles one ``batch_lines`` batch of cells in row-major order.
3. Sets ``param_0..param_{N*batch_lines-1}`` so the JDBCSampler
   (``Prepared Update Statement``) can bind.

Numeric type policy (closes review.md §1 阻塞项 #1):

- All timestamp and device-number arithmetic uses Groovy ``long`` at
  runtime to avoid ``batch_seq * ms_step`` overflow on long runs.
- Inter-timestamp step uses integer division (``ms_step / batch_lines``).
  When ``ms_step < batch_lines`` the per-row intra-step rounds to 0;
  callers wanting finer intra-batch separation should ensure
  ``ms_step >= batch_lines``.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from direct_insert_write.errors import DirectInsertGenerationError
from utils.preprocessor_helpers import all_groovy_decls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_positive(name: str, value: int) -> None:
    if not isinstance(value, int) or value <= 0:
        raise DirectInsertGenerationError(
            f"{name} must be a positive int, got {value!r}"
        )


def _safe_key_token(s: str) -> str:
    """Sanitize for use inside a JMeter props key (non-alnum → _)."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", s)


def _groovy_str_literal(s: str) -> str:
    """Single-quoted Groovy string literal with internal quotes escaped."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _make_rows_key(db: str, table: str) -> str:
    """Shared-memory key for the row aggregate.

    Format mirrors :mod:`shared_memory_initializer`: non-alnum chars
    in ``db``/``table`` are folded to ``_``; ``db`` and ``table`` are
    then joined with a single ``_`` separator.

    NOTE: must NOT contain ``.`` — JMeter's ``JMeterProperties``
    traverses dotted keys as nested Hashtable paths, so a key like
    ``__SHARED_MEM_db.table`` would not be retrievable from another
    thread group. See review 2026-07-15 smoke fix.
    """
    return f"__SHARED_MEM_{_safe_key_token(db)}_{_safe_key_token(table)}"


def _make_columns_key(db: str, table: str) -> str:
    """Shared-memory key for the column-name list (in table DDL order)."""
    return _make_rows_key(db, table) + "_columns"


# ---------------------------------------------------------------------------
# Write path (single_insert / batch_insert)
# ---------------------------------------------------------------------------

def generate_preprocessor_script(
    table_config: dict,
    device_per_thread: int,
    *,
    ms_step: int = 1000,
    batch_lines: int = 1,
    device_start: int = 0,
    batch_seq_init: int = 0,
) -> str:
    """Render a Groovy script that prepares one batch of INSERT values.

    Parameters
    ----------
    table_config:
        Dict with keys::

            {
                "db":       "iot_monitor",     # informational only
                "table":    "t_cnc",           # bare table name → key
                "columns":  ["ts", "ptag_int8_1", "col_int8_1"],
                "first_ptag_column": "ptag_int8_1",  # placeholder col
            }

        ``first_ptag_column`` is the column whose first-primary-tag value
        contains ``${device_code}`` and must be replaced with the runtime
        device identifier. The first column is assumed to be the
        timestamp column (design §3.5.1).
    device_per_thread:
        Number of devices owned by each thread. Must be > 0.
    ms_step:
        Milliseconds between consecutive batches (default 1000).
    batch_lines:
        Number of rows per batch. Must be > 0. The script copies
        ``batch_lines`` consecutive rows from shared memory.
    device_start:
        Global starting device id (default 0).
    batch_seq_init:
        Initial batch sequence when no thread var is set yet (default 0).

    Returns
    -------
    Groovy script source as a single string.

    Raises
    ------
    DirectInsertGenerationError
        On missing required keys or invalid ``device_per_thread`` /
        ``batch_lines`` / ``ms_step``.
    """
    _require_positive("device_per_thread", device_per_thread)
    _require_positive("batch_lines", batch_lines)
    _require_positive("ms_step", ms_step)

    db = table_config.get("db")
    table = table_config.get("table")
    columns = table_config.get("columns")
    first_ptag = table_config.get("first_ptag_column")
    if not db or not table or not columns:
        raise DirectInsertGenerationError(
            "table_config must contain 'db', 'table', and 'columns'"
        )

    columns = [str(c) for c in columns]
    if not columns:
        raise DirectInsertGenerationError(
            "table_config['columns'] must not be empty"
        )
    ptag_index: Optional[int] = None
    if first_ptag is not None:
        if first_ptag not in columns:
            raise DirectInsertGenerationError(
                f"first_ptag_column {first_ptag!r} must appear in columns"
            )
        if columns[0] == first_ptag:
            # Spec puts timestamp in first param slot; refuse mis-order so
            # the caller fixes config rather than silently misordering.
            raise DirectInsertGenerationError(
                "first column must be the timestamp column, not the first ptag"
            )
        ptag_index = columns.index(first_ptag)

    n_cols = len(columns)
    n_cells = n_cols * batch_lines
    rows_key = _make_rows_key(db, table)
    safe_db = _groovy_str_literal(db)
    safe_table = _groovy_str_literal(table)
    # Python-side columns list is the runtime fallback when the
    # ``_columns`` shared-memory key is missing (e.g. older
    # ``shared-memory-initializer`` build). When the key is present
    # the runtime order is authoritative — see design §3.6.
    columns_array_groovy = ", ".join(_groovy_str_literal(c) for c in columns)
    ptag_index_expr = str(ptag_index) if ptag_index is not None else "-1"

    script = f"""\
{all_groovy_decls()}

// -------- shared memory --------
def db = {safe_db}
def table = {safe_table}
def rowsKey = '{rows_key}'
// JSR223's per-context ``props`` is destroyed when SetupThreadGroup ends;
// the SharedMemory loader writes through the global JMeterUtils singleton,
// so the read here must also go through that singleton.
def allRows = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()
    .get(rowsKey) as ArrayList
// Column-name order MUST match the SQL column list embedded in the
// JDBCSampler (``insert into db.t (ts, ...) values (?, ...)``). The
// shared-memory initializer's ``_columns`` key carries the seed-CSV
// header which is missing the leading ``ts`` column (ts is generated
// at write time) — using it here would mis-project ptagIndex and the
// per-cell loop count, so we use the Python-side list directly.
def columns = [{columns_array_groovy}]
def nCols = columns.size()
if (allRows == null || allRows.isEmpty()) {{
    log.warn("DirectInsertPrep: shared memory empty for " + rowsKey)
    for (int p = 0; p < {n_cells}; p++) {{
        vars.put("param_" + p, "")
    }}
    return
}}

// -------- device number setup --------
def threadNum = ctx.getThreadNum()
if (threadNum < 0) {{
    threadNum = (vars.get('__threadNum') as Integer) ?: 0
}}
def localDeviceStart = vars.get('device_start') != null ?
    (vars.get('device_start') as Integer) : {device_start}
def devicePerThread = {device_per_thread}

// -------- base time + batch sequence (thread-local, captured once) --------
def baseTimeKey = 'base_time_' + rowsKey
def batchSeqKey = 'batch_seq_' + rowsKey
if (vars.get(baseTimeKey) == null) {{
    vars.put(baseTimeKey, String.valueOf(System.currentTimeMillis()))
}}
def baseTime = (vars.get(baseTimeKey) as Long)
def batchSeq = vars.get(batchSeqKey) != null ?
    (vars.get(batchSeqKey) as Integer) : {batch_seq_init}
vars.put(batchSeqKey, String.valueOf(batchSeq + 1))

// -------- pick start row + copy batch_lines (wrap if needed) --------
def total = allRows.size()
def batchLines = {batch_lines}
def pickedStart = new Random().nextInt(total)
def picked = []
for (int i = 0; i < batchLines; i++) {{
    picked.add(allRows.get((pickedStart + i) % total))
}}
def cloned = cloneRows(picked)

// -------- per-row timestamp + device number + cell projection --------
// ``columns`` and ``nCols`` defined above from shared memory.
def ptagIndex = {ptag_index_expr}
def msStepL = {ms_step} as long
def batchSeqL = batchSeq as long
def baseTimeL = baseTime as long
def paramIdx = 0
for (int r = 0; r < batchLines; r++) {{
    def row = cloned.get(r)
    long ts = calculateTimestamps(baseTimeL, batchSeqL, msStepL, batchLines as long, 1).get(0)
    long deviceNumber = calculateDeviceNumber(threadNum as long, localDeviceStart as long, devicePerThread as long, r)
    for (int c = 0; c < nCols; c++) {{
        def cell
        if (c == 0) {{
            // ts column — first per design §3.5.1. Use a fixed-width
            // millisecond format padded to nanoseconds so JDBC's
            // ``Timestamp.valueOf`` (called by the sampler when
            // ``queryArgumentsTypes=TIMESTAMP``) parses cleanly. Groovy's
            // ``Timestamp.toString()`` returns a locale-dependent string
            // that may omit the 9-digit fractional part.
            cell = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSSSSSSSS").format(new java.util.Date(ts))
        }} else if (c == ptagIndex) {{
            cell = deviceIdentifier(deviceNumber)
        }} else {{
            def raw = row.get(c)
            cell = (raw == null) ? "" : raw.toString()
        }}
        vars.put("param_" + paramIdx, cell)
        paramIdx++
    }}
}}
log.info("DirectInsertPrep: prepared " + batchLines + " rows for " + {safe_table} + " (batch_seq=" + batchSeq + ")")
"""
    return script


# ---------------------------------------------------------------------------
# Relational init path
# ---------------------------------------------------------------------------

def generate_relational_init_preprocessor_script(
    table_name: str,
    rel_col_seed_files: Sequence[str],
    batch_lines: int,
) -> str:
    """Groovy script that prepares a relational-table batch.

    Per design §3.6 关系表初始化采样器:

    - Each loop iteration reads the column seed files (one per
      relational column) and assembles a ``batch_lines`` batch in
      row-major order.
    - Cells are written to ``param_0..param_{N*batch_lines-1}`` for the
      JDBCSampler (``Prepared Update Statement``) to bind.
    - The loop index is read from ``__rel_batch_idx`` and incremented
      after each iteration.

    The caller is expected to:

    1. Inject ``rel_col_seed_files`` (comma-separated file names) into
       the thread's vars before this PreProcessor runs.
    2. Wrap the sampler in a ``LoopController`` with iteration count
       ``total_rows // batch_lines`` (no tail batch per review.md).
    """
    _require_positive("batch_lines", batch_lines)
    if not rel_col_seed_files:
        raise DirectInsertGenerationError(
            "rel_col_seed_files must not be empty"
        )

    safe_table = _groovy_str_literal(table_name)
    # Filesystem subfolder mirrors the seed writer's layout:
    # ``seeds/<db>/<table>/...`` (with slash separators, not dots). The
    # table name carries the form ``db.table``; split on ``.`` and join
    # with ``/`` so the path actually exists.
    fs_subdir = table_name.replace('.', '/')
    safe_fs_subdir = _groovy_str_literal(fs_subdir)
    files_groovy = ", ".join(
        _groovy_str_literal(f) for f in rel_col_seed_files
    )

    # Per-table batch index: scope the JMeter variable to this table so
    # multiple RelInit samplers within the same thread group don't
    # bleed counter state into each other (the pre-2026-07-17 single-name
    # ``__rel_batch_idx`` would skip rows after the first sampler). The
    # table name in the key also has its ``.`` replaced with ``_`` to
    # avoid JMeter's nested-Hashtable dotted-key quirk (same as the
    # SharedMemory loader uses).
    safe_table_key = table_name.replace('.', '_')
    safe_batch_idx_key = _groovy_str_literal(f"__rel_batch_idx_{safe_table_key}")

    script = f"""\
// -------- relational init: read column seed files --------
def tableName = {safe_table}
def fsSubdir = {safe_fs_subdir}
def seedDir = vars.get('seed_dir') ?: 'seeds'
def batchLines = {batch_lines}
def batchIdxKey = {safe_batch_idx_key}
def batchIdx = (vars.get(batchIdxKey) as Integer) ?: 0

def colFiles = vars.get('rel_col_seed_files')?.split(',') ?: [{files_groovy}]
def colSeeds = []
colFiles.each {{ filename ->
    def filepath = seedDir + '/' + fsSubdir + '/' + filename
    def file = new File(filepath)
    if (file.exists()) {{
        colSeeds.add(file.readLines())
    }} else {{
        log.warn("RelInit: seed file not found: " + filepath)
        colSeeds.add(["null"])
    }}
}}

// Row count = max seed_num across columns; row assembly uses modulo wrap.
def maxRows = colSeeds.collect {{ it.size() }}.max() ?: 0
def startRow = batchIdx * batchLines
def endRow = Math.min(startRow + batchLines, maxRows)

// -------- assemble param_0..param_N*batch_lines-1 in row-major order --------
def paramIdx = 0
for (int rowIdx = startRow; rowIdx < endRow; rowIdx++) {{
    for (int colIdx = 0; colIdx < colSeeds.size(); colIdx++) {{
        def seeds = colSeeds.get(colIdx)
        def rawValue = seeds.get(rowIdx % seeds.size())
        def value = (rawValue == null || "null".equalsIgnoreCase(rawValue.toString())) ? "" : rawValue.toString()
        vars.put("param_" + paramIdx, value)
        paramIdx++
    }}
}}

vars.put(batchIdxKey, String.valueOf(batchIdx + 1))
log.info("RelInit: table=" + tableName + " batch=" + batchIdx + " rows " + startRow + "-" + endRow + " params=" + paramIdx)
"""
    return script


__all__ = [
    "generate_preprocessor_script",
    "generate_relational_init_preprocessor_script",
]
