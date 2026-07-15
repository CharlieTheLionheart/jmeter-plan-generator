"""JDBCSampler config generation for direct-insert writes.

Design: openspec/changes/direct-insert-write/design.md
Spec:    openspec/changes/direct-insert-write/specs/direct-insert-write/spec.md

Produces dictionary-shaped samplers consumed by :mod:`utils.xml_helpers`'s
``jdbc_sampler_element``. Keeping the config step separate lets callers
inspect / override individual fields before assembling JMX XML.

Sampler binding model (closes review.md C3 / C4):

- Write path (``single_insert`` / ``batch_insert``): the
  ``JDBCSampler`` uses ``queryType=Update Statement`` with one ``?``
  placeholder per cell. The preceding ``JSR223PreProcessor`` sets
  thread-local ``param_0..param_{N*batch_lines-1}`` (row-major
  cell strings); the sampler ``queryArguments`` references them as
  ``${param_N}``.
- Relational init path: the ``JDBCSampler`` uses
  ``queryType=Prepared Update Statement`` with one ``?`` per cell,
  bound to the same ``param_N`` vars set by
  :func:`generate_relational_init_preprocessor_script`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from direct_insert_write.errors import DirectInsertGenerationError
from utils.xml_helpers import jdbc_sampler_element

from .preprocessor_generator import (
    generate_preprocessor_script,
    generate_relational_init_preprocessor_script,
)
from .sql_generator import (
    generate_batch_insert_sql,
    generate_single_insert_sql,
)


_VALID_MODES = frozenset({"single_insert", "batch_insert"})


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

    With ``Update Statement`` JMeter's inline substitution forwards the
    value as a quoted string; the type tag primarily controls formatting
    for non-string columns. Callers that need tighter JDBC typing
    (e.g. ``TIMESTAMP``) should pass ``query_arguments_types`` explicitly.
    """
    return ",".join(["VARCHAR"] * n)


def generate_jdbc_sampler_config(
    mode: str,
    sql: str,
    *,
    batch_lines: Optional[int] = None,
    data_source: str = "jdbcConfig",
    name: Optional[str] = None,
    query_arguments_types: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a JDBCSampler config dict for the requested write mode.

    Parameters
    ----------
    mode:
        ``"single_insert"`` or ``"batch_insert"``.
    sql:
        Pre-rendered INSERT SQL containing ``?`` placeholders. See
        :func:`generate_single_insert_sql` /
        :func:`generate_batch_insert_sql`.
    batch_lines:
        Required for ``batch_insert``; sets ``batch_size``. Ignored for
        ``single_insert``.
    data_source:
        Pool name (must match JDBCDataSource generator). Defaults to
        ``jdbcConfig``.
    query_arguments_types:
        Optional comma-separated JDBC type list. When omitted, defaults
        to all ``VARCHAR`` — appropriate for ``Update Statement`` inline
        substitution. Pass an explicit list (e.g. ``"TIMESTAMP,VARCHAR"``)
        when binding requires tighter typing.

    Returns
    -------
    Config dict consumable by ``jdbc_sampler_element(**config)``.

    The returned dict always contains ``query_type``,
    ``query_arguments`` (one ``${param_N}`` per ``?``), and
    ``query_arguments_types``.
    """
    if mode not in _VALID_MODES:
        raise DirectInsertGenerationError(
            f"mode must be one of {_VALID_MODES}, got {mode!r}"
        )
    if not sql or not isinstance(sql, str):
        raise DirectInsertGenerationError(
            "sql must be a non-empty string"
        )

    n_params = _count_placeholders(sql)

    config: Dict[str, Any] = {
        "name": name or f"DirectInsert_{mode}",
        "query": sql,
        "data_source": data_source,
        "query_type": "Prepared Update Statement",
        "query_arguments": _param_args(n_params),
        "query_arguments_types": query_arguments_types or _default_types(n_params),
        "variable_names": "",
        "result_variable": "",
        "result_set_handler": "Store as String",
    }

    if mode == "batch_insert":
        if not isinstance(batch_lines, int) or batch_lines <= 0:
            raise DirectInsertGenerationError(
                f"batch_insert requires batch_lines > 0, got {batch_lines!r}"
            )
        config["batch_size"] = batch_lines
    return config


def create_jdbc_sampler(
    mode: str,
    sql: str,
    *,
    batch_lines: Optional[int] = None,
    data_source: str = "jdbcConfig",
    name: Optional[str] = None,
    query_arguments_types: Optional[str] = None,
    testname: Optional[str] = None,
) -> Tuple[ET.Element, ET.Element]:
    """Return ``(JDBCSampler, hashTree)`` XML elements for the configured mode.

    Convenience wrapper around :func:`generate_jdbc_sampler_config` that
    hands the config to ``jdbc_sampler_element``. The config's
    ``query_arguments`` (e.g. ``${param_0},${param_1},...``) and
    ``query_arguments_types`` are propagated so the JSR223PreProcessor's
    per-cell ``vars.put("param_N", ...)`` calls bind to the INSERT
    placeholders.
    """
    config = generate_jdbc_sampler_config(
        mode=mode,
        sql=sql,
        batch_lines=batch_lines,
        data_source=data_source,
        name=name,
        query_arguments_types=query_arguments_types,
    )
    return jdbc_sampler_element(
        name=config["name"],
        query=config["query"],
        data_source=config["data_source"],
        query_type=config["query_type"],
        query_arguments=config["query_arguments"],
        query_arguments_types=config["query_arguments_types"],
        testname=testname,
    )


def create_jsr223_preprocessor_for_write(
    *,
    db: str,
    table: str,
    columns: List[str],
    first_ptag_column: str,
    device_per_thread: int,
    ms_step: int = 1000,
    batch_lines: int = 1,
    testname: Optional[str] = None,
) -> Tuple[ET.Element, ET.Element]:
    """Build a JSR223PreProcessor XML element wired for direct-insert writes.

    The PreProcessor reads from
    ``props.get("__SHARED_MEM_{table}")``, computes per-row timestamps
    + device ids, and exposes per-cell values via
    ``vars.put("param_N", ...)`` (see :mod:`preprocessor_generator`).

    Returns ``(JSR223PreProcessor element, hashTree element)`` consumed
    by :mod:`utils.xml_helpers`'s ``jsr223_preprocessor_element``.
    """
    table_config = {
        "db": db,
        "table": table,
        "columns": columns,
        "first_ptag_column": first_ptag_column,
    }
    script = generate_preprocessor_script(
        table_config=table_config,
        device_per_thread=device_per_thread,
        ms_step=ms_step,
        batch_lines=batch_lines,
    )
    from utils.xml_helpers import jsr223_preprocessor_element

    return jsr223_preprocessor_element(
        name=f"DirectInsertPrep_{db}_{table}",
        script=script,
        script_language="groovy",
        cache_key="true",
        testname=testname or f"DirectInsertPrep {db}.{table}",
    )


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

    Per review.md resolution closing the "残尾批" question:

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
    "create_jdbc_sampler",
    "create_jsr223_preprocessor_for_write",
    "generate_jdbc_sampler_config",
    "generate_relational_table_init_sampler",
]
