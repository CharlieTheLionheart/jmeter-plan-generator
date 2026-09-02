"""SQL generation for relational-table init batch INSERTs.

Design: openspec/changes/direct-insert-write/design.md
Spec:    openspec/changes/direct-insert-write/specs/direct-insert-write/spec.md

Produces the multi-row ``INSERT INTO ... VALUES (?, ?), (?, ?), ...``
template consumed by :mod:`jmx_skeleton_generator.generators.ddl_setup`
for the one-time relational init sampler. The write TG path
(``single_insert`` / ``batch_insert``) is wired through
:func:`jmx_skeleton_generator.generators.write_groups._build_inline_sql_preprocessor_script`
which emits an inline SQL string at runtime.

Conventions enforced here:

- Table names use the qualified form ``database.table``.
- All identifiers and SQL keywords are lower-cased.
- :class:`DirectInsertGenerationError` is raised on validation
  failures.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from direct_insert_write.errors import DirectInsertGenerationError


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------

def _split_qualified(table_name: str) -> tuple[str, str]:
    """Split a qualified name like ``iot_monitor.t_cnc`` into (db, table).

    Raises :class:`DirectInsertGenerationError` if the form is invalid.
    """
    if not isinstance(table_name, str) or "." not in table_name:
        raise DirectInsertGenerationError(
            f"table_name must be a qualified name 'db.table', got {table_name!r}"
        )
    db, _, table = table_name.partition(".")
    if not db or not table:
        raise DirectInsertGenerationError(
            f"table_name must be a qualified name 'db.table', got {table_name!r}"
        )
    return db, table


def _identifier_or_keyword(token: str) -> str:
    """Lower-case + sanity check a SQL identifier or keyword token."""
    if not token or not token.strip():
        raise DirectInsertGenerationError("identifier must not be empty")
    return token.strip().lower()


def _normalize_columns(columns: Iterable[str]) -> List[str]:
    """Return a lower-cased column list, preserving order, with validation."""
    out: List[str] = []
    for col in columns:
        if not isinstance(col, str):
            raise DirectInsertGenerationError(
                f"column must be a string, got {type(col).__name__}"
            )
        out.append(_identifier_or_keyword(col))
    return out


# ---------------------------------------------------------------------------
# Batch INSERT
# ---------------------------------------------------------------------------

def generate_batch_insert_sql(
    table_name: str,
    columns: Iterable[str],
    batch_lines: int,
    *,
    row_count: Optional[int] = None,
) -> str:
    """Generate batch INSERT with ``batch_lines`` placeholder rows.

    Parameters
    ----------
    table_name:
        Qualified table name ``db.table``.
    columns:
        Ordered column list.
    batch_lines:
        Configured batch size; controls column-placeholder repeat count.
    row_count:
        Number of value rows to actually emit. Defaults to ``batch_lines``
        for full batches; with the closed tail-batch policy this is unused
        for the relational init flow (see review.md 残尾批 resolution).

    Returns
    -------
    ``insert into db.table (col1, col2) values (?, ?),(?, ?),...``.

    Raises
    ------
    DirectInsertGenerationError
        When ``batch_lines <= 0``, ``columns`` is empty, or
        ``row_count`` exceeds ``batch_lines`` (defensive).
    """
    if not isinstance(batch_lines, int) or batch_lines <= 0:
        raise DirectInsertGenerationError(
            f"batch_lines must be a positive int, got {batch_lines!r}"
        )
    cols = _normalize_columns(columns)
    if not cols:
        raise DirectInsertGenerationError(
            "generate_batch_insert_sql requires at least one column"
        )
    n = batch_lines if row_count is None else row_count
    if not isinstance(n, int) or n <= 0 or n > batch_lines:
        raise DirectInsertGenerationError(
            f"row_count must be in (0, batch_lines], got {n} for batch_lines={batch_lines}"
        )

    db, table = _split_qualified(table_name)
    qualified = f"{_identifier_or_keyword(db)}.{_identifier_or_keyword(table)}"
    placeholders_inner = ", ".join(["?"] * len(cols))
    one_row = f"({placeholders_inner})"
    rows_clause = ", ".join([one_row] * n)
    cols_list = ", ".join(cols)
    return f"insert into {qualified} ({cols_list}) values {rows_clause}"
