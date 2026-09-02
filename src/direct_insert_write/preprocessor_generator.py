"""JSR223PreProcessor Groovy script generator for relational-table init samplers.

Design: openspec/changes/direct-insert-write/design.md
Spec:    openspec/changes/direct-insert-write/specs/direct-insert-write/spec.md

The relational init path emits a PreProcessor that:

1. Reads column seed files (per-iterator batch index in
   ``__rel_batch_idx_{table}``).
2. Assembles one ``batch_lines`` batch of cells in row-major order.
3. Sets ``param_0..param_{N*batch_lines-1}`` so the JDBCSampler
   (``Prepared Update Statement``) can bind.

Numeric type policy:

- Timestamp and device-number arithmetic uses Groovy ``long`` to
  avoid overflow on long-running batches.
- All Groovy helpers injected via ``all_groovy_decls()`` share the
  same ``long`` policy.
"""

from __future__ import annotations

from typing import Sequence

from direct_insert_write.errors import DirectInsertGenerationError


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
    import re
    return re.sub(r"[^a-zA-Z0-9_]", "_", s)


def _groovy_str_literal(s: str) -> str:
    """Single-quoted Groovy string literal with internal quotes escaped."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


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
    "generate_relational_init_preprocessor_script",
]