"""Relational-table init sampler config for direct-insert writes.

Design: openspec/changes/direct-insert-write/design.md
Spec:    openspec/changes/direct-insert-write/specs/direct-insert-write/spec.md

Produces the dictionary-shaped sampler config consumed by
:mod:`jmx_skeleton_generator.generators.ddl_setup` for the one-time
relational init DDL sampler. The write TG path (``single_insert`` /
``batch_insert``) is wired through
:func:`jmx_skeleton_generator.generators.write_groups._build_inline_sql_preprocessor_script`;
this module only serves the relational init sampler.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from direct_insert_write.errors import DirectInsertGenerationError

from .preprocessor_generator import generate_relational_init_preprocessor_script
from .sql_generator import generate_batch_insert_sql


def _count_placeholders(sql: str) -> int:
    """Count ``?`` placeholders outside string literals."""
    if not sql or not isinstance(sql, str):
        return 0
    count = 0
    in_string = False
    string_char = None
    for ch in sql:
        if ch in ("'", '"'):
            if not in_string:
                in_string = True
                string_char = ch
            elif string_char == ch:
                in_string = False
                string_char = None
        if not in_string and ch == "?":
            count += 1
    return count


def _param_args(n: int) -> str:
    """Comma-joined ``${param_N}`` references for ``n`` placeholders."""
    return ",".join(f"${{param_{i}}}" for i in range(n))


def _default_types(n: int) -> str:
    """Default ``queryArgumentsTypes`` — all ``VARCHAR``.

    With ``Prepared Update Statement`` JMeter's inline substitution
    forwards the value as a quoted string; the type tag primarily
    controls formatting for non-string columns. Callers that need
    tighter JDBC typing (e.g. ``TIMESTAMP``) should pass
    ``query_arguments_types`` explicitly.
    """
    return ",".join(["VARCHAR"] * n)


def generate_relational_table_init_sampler(
    table_name: str,
    columns: List[str],
    total_rows: int,
    *,
    batch_lines: int = 500,
    rel_col_seed_files: Optional[List[str]] = None,
    data_source: str = "jdbcConfig",
    column_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Configuration for the relational table one-time initialization sampler.

    The caller is expected to:

    1. Wrap this sampler in a ``LoopController`` whose loop count is
       ``total_rows // batch_lines``.
    2. Inject ``rel_col_seed_files`` (comma-separated) into the
       thread's UDV before the sampler runs.
    3. Mount the sampler inside a ``SetupThreadGroup``.

    - Every loop iteration emits the **same** fixed ``batch_lines``
      VALUES tuple. There is no tail batch.
    - ``total_rows`` must be a positive multiple of ``batch_lines``; a
      non-multiple is rejected with
      :class:`DirectInsertGenerationError`.

    Parameters
    ----------
    table_name:
        Qualified ``db.table``.
    columns:
        Ordered column list (relation-style; no first-ptag special case).
    total_rows:
        Total seed rows to insert; must be a multiple of ``batch_lines``.
    batch_lines:
        Rows per execution.
    rel_col_seed_files:
        Column seed file names (one per ``columns`` entry). Used by
        :func:`generate_relational_init_preprocessor_script` to assemble
        each batch. Required.
    column_types:
        Optional JDBC type list aligned with ``columns`` (e.g.
        ``["INTEGER", "VARCHAR"]``). When omitted, defaults to all
        ``VARCHAR``. The final ``queryArgumentsTypes`` is this list
        repeated ``batch_lines`` times.

    Returns
    -------
    Dict with keys: ``name``, ``sql``, ``loop_count``, ``batch_size``,
    ``data_source``, ``query_type`` (``Prepared Update Statement``),
    ``query_arguments`` (``${param_N}`` form), ``query_arguments_types``,
    ``rel_col_seed_files``, ``preprocessor_script``.
    """
    if not isinstance(total_rows, int) or total_rows <= 0:
        raise DirectInsertGenerationError(
            f"total_rows must be a positive int, got {total_rows!r}"
        )
    if not isinstance(batch_lines, int) or batch_lines <= 0:
        raise DirectInsertGenerationError(
            f"batch_lines must be a positive int, got {batch_lines!r}"
        )
    if total_rows % batch_lines != 0:
        raise DirectInsertGenerationError(
            f"total_rows ({total_rows}) must be a multiple of "
            f"batch_lines ({batch_lines}); residual rows are not supported"
        )
    if not rel_col_seed_files:
        raise DirectInsertGenerationError(
            "rel_col_seed_files is required (list of column seed file "
            "names, one per columns entry)"
        )
    if len(rel_col_seed_files) != len(columns):
        raise DirectInsertGenerationError(
            f"rel_col_seed_files length {len(rel_col_seed_files)} must "
            f"match columns length {len(columns)}"
        )

    if "." not in table_name:
        raise DirectInsertGenerationError(
            f"table_name must be a qualified 'db.table', got {table_name!r}"
        )
    db, _ = table_name.split(".", 1)

    n_cols = len(columns)
    n_params = n_cols * batch_lines
    loop_count = total_rows // batch_lines
    sql = generate_batch_insert_sql(table_name, columns, batch_lines)

    if column_types is None:
        types_per_row = ["VARCHAR"] * n_cols
    else:
        if len(column_types) != n_cols:
            raise DirectInsertGenerationError(
                f"column_types length {len(column_types)} must match "
                f"columns length {n_cols}"
            )
        types_per_row = list(column_types)
    query_arguments = _param_args(n_params)
    query_arguments_types = ",".join(types_per_row * batch_lines)

    pre_script = generate_relational_init_preprocessor_script(
        table_name=table_name,
        rel_col_seed_files=rel_col_seed_files,
        batch_lines=batch_lines,
    )

    return {
        "name": f"RelInit_{db}_{table_name.split('.', 1)[1]}",
        "sql": sql,
        "loop_count": loop_count,
        "batch_size": batch_lines,
        "data_source": data_source,
        "query_type": "Prepared Update Statement",
        "query_arguments": query_arguments,
        "query_arguments_types": query_arguments_types,
        "rel_col_seed_files": list(rel_col_seed_files),
        "preprocessor_script": pre_script,
    }


__all__ = [
    "generate_relational_table_init_sampler",
]