"""Tests for ``_build_inline_sql_preprocessor_script`` col_tag_bind_mode branch.

Per OpenSpec change ``col-tag-bind-write`` (2026-08-05) tasks.md §4:
- When ``col_tag_bind_mode=True``, the preprocessor reads
  ``__SHARED_MEM_{db}_{table}_bind`` (the bind-namespaced map), computes
  ``group_id = hash(ptag_tuple) mod num_threads`` (where ``ptag_tuple``
  includes ``device_code`` from ``${device_start}`` + ``device_per_thread``),
  picks the subset column list + row values for that group, and emits an
  inline INSERT that includes ``ts`` + every ``primary_tag`` + the subset
  ``data_col`` + any explicitly ``NOT NULL`` ``data_col``.
- Empty / missing groups must produce a safe ``-- no group ...`` SQL
  (no exception), so the JDBC sampler logs a clean error rather than
  triggering a Groovy crash mid-batch.
- When ``col_tag_bind_mode`` is False the script body must be
  byte-identical to the pre-change behavior.
"""

from __future__ import annotations

from jmx_skeleton_generator.generators.write_groups import (
    _build_inline_sql_preprocessor_script,
)


# ---------------------------------------------------------------------------
# Minimal kwargs for the test suite. The default ``columns`` include a
# first ptag (``device_id``) plus 4 data columns to exercise the
# subset / NOT-NULL / group-id branches.
# ---------------------------------------------------------------------------


def _minimal_kwargs(**overrides) -> dict:
    base = {
        "db": "iot_monitor",
        "table": "meters",
        "columns": [
            "ts",
            "device_id",
            "col_int8_1",
            "col_int8_2",
            "col_int8_3",
            "col_varchar_1",
        ],
        "first_ptag_column": "device_id",
        "device_per_thread": 1,
        "column_types": None,
        "ms_step": 1000,
        "batch_lines": 1,
    }
    base.update(overrides)
    return base


def test_bind_mode_emits_subset_columns() -> None:
    """col_tag_bind_mode=True → script reads ``__SHARED_MEM_*_bind`` and
    builds an INSERT keyed on a ptag-bound column subset.
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=True, col_num_per_tag=3, num_threads=4)
    )

    assert "__SHARED_MEM_iot_monitor_meters_bind" in script, (
        "bind-mode script must read the bind-namespaced shared memory"
    )
    # The qualified INSERT is built at Groovy runtime via
    # ``qualifiedTable = db + "." + table``; check both halves separately.
    assert "INSERT INTO" in script, "INSERT literal must be present in script"
    assert "qualifiedTable" in script, "qualifiedTable assembly must be present"
    assert "iot_monitor" in script and "meters" in script
    # ptag column must appear in the column list (first ptag is part of
    # every INSERT regardless of subset).
    assert "device_id" in script


def test_bind_mode_emits_correct_group_id_lookup() -> None:
    """col_tag_bind_mode=True → script computes ``group_id`` via hash + mod."""
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=True, col_num_per_tag=2, num_threads=8)
    )

    assert "hashCode()" in script, script[:1500]
    assert "% 8" in script or "%numThreads" in script or "% numThreads" in script, (
        f"expected modulo-by-num_threads pattern; got snippet:\n{script[:2000]}"
    )


def test_bind_mode_includes_not_null_data_cols() -> None:
    """NOT-NULL data columns are appended to the INSERT column list even
    when they fall outside the per-group subset.
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(
            col_tag_bind_mode=True,
            col_num_per_tag=2,
            num_threads=4,
            not_null_data_cols=["col_int8_3"],
        )
    )

    # The NOT-NULL column must be referenced somewhere in the column-list
    # construction (we don't pin exact ordering because LinkedHashSet
    # iteration order matches insertion; the column name must simply appear).
    assert "col_int8_3" in script, (
        "explicit NOT NULL data column must appear in INSERT column list"
    )


def test_bind_mode_no_group_returns_safe_default() -> None:
    """When the bind groups map is empty, the script must produce a
    safe SQL (so the JDBC sampler records a clean error rather than a
    JDBC parse error from a ``-- no bind groups`` comment line).
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=True, col_num_per_tag=2, num_threads=4)
    )

    assert 'vars.put("insert_sql", "SELECT 1")' in script, (
        f"empty-groups guard must emit SELECT 1 fallback; snippet:\n{script[:2000]}"
    )


def test_default_mode_unchanged() -> None:
    """Regression: ``col_tag_bind_mode=False`` keeps the existing full-row
    INSERT behavior — must read ``__SHARED_MEM_*`` (not ``_bind``) and
    emit a script that does NOT contain the bind-namespaced read.
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=False, col_num_per_tag=0)
    )

    assert "__SHARED_MEM_iot_monitor_meters_bind" not in script, (
        "full-row mode must NOT read the bind namespace"
    )
    assert "__SHARED_MEM_iot_monitor_meters" in script
    # The full-row path still iterates over ``allRows`` (List<List<String>>);
    # confirm the legacy path is intact.
    assert "allRows" in script
