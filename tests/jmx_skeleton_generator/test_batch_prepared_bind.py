"""Tests for batch_prepared col_tag_bind_mode D-28 (per-device partial INSERT).

Per-device partial INSERT SQL — each (threadNum, d) device gets its
own ``insert into db.t (ts, ptag, c1..cN) values (?,?,…)`` template
(typically 5-7 columns) and the sampler body runs an independent
``prepareStatement → setXxx → addBatch → executeBatch → close`` cycle
per device. Replaces the D-27 single-template full-row + null-fill
path which OOM'd the JMeter client at 12 GB heap on sparse_20k
(metrics +60M-parameter batch buffer per tick).
"""

from __future__ import annotations

import pytest

from jmx_skeleton_generator.generators.write_groups import (
    _build_batch_prepared_bind_preprocessor_body,
    _build_batch_prepared_preprocessor_body,
    _build_batch_prepared_sampler_body,
    build_batch_prepared_preprocessor_script,
)


def _minimal_bind_kwargs(**overrides) -> dict:
    base = {
        "table_name": "iot_monitor.meters",
        "ptag_names": ["ptag_varchar_1"],
        "ptag_col_types": ["varchar"],
        "col_type_buckets": {
            "col_int8": ["int8", "bigint", "int", "int2", "int4", "tinyint", "smallint"],
        },
        "batch_lines": 1,
        "ms_step": 1000,
        "device_per_thread": 1,
    }
    base.update(overrides)
    return base


def _minimal_full_kwargs(**overrides) -> dict:
    """Legacy non-bind kwargs (no col_tag_bind_mode)."""
    base = {
        "table_name": "iot_monitor.meters",
        "first_ptag": "ptag_varchar_1",
        "batch_lines": 1,
        "ms_step": 1000,
        "device_per_thread": 1,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# D-28: per-device partial INSERT prep body
# ---------------------------------------------------------------------------

def test_bind_mode_writes_per_device_preps_not_legacy_batch_rows() -> None:
    """col_tag_bind_mode=True must emit per-device entries into
    ``__BATCH_PREPS_<tableName>`` (not the legacy
    ``__BATCH_ROWS_<tableName>``).
    """
    script = _build_batch_prepared_bind_preprocessor_body(
        **_minimal_bind_kwargs()
    )
    assert "__BATCH_PREPS_${tableName}" in script
    assert "__BATCH_ROWS" not in script


def test_bind_mode_reads_bind_namespaced_memory() -> None:
    """col_tag_bind_mode=True must read ``__SHARED_MEM_*_bind``."""
    script = _build_batch_prepared_bind_preprocessor_body(
        **_minimal_bind_kwargs()
    )
    assert "__SHARED_MEM_iot_monitor_meters_bind" in script


def test_bind_mode_uses_devicecode_key_no_hash_distribution() -> None:
    """bind map must be looked up by literal deviceCode (D-21), no
    hash distribution.
    """
    script = _build_batch_prepared_bind_preprocessor_body(
        **_minimal_bind_kwargs()
    )
    assert "bindGroups.get(deviceCode)" in script
    assert "groupId" not in script


def test_bind_mode_per_device_partial_sql_contains_subset_columns() -> None:
    """Per-device SQL must reference the per-deviceCode ``col_names``
    subset (no hard-coded full-column list).
    """
    script = _build_batch_prepared_bind_preprocessor_body(
        **_minimal_bind_kwargs()
    )
    # placeholders come from insertCols.size() (1 ts + 1 ptag + colNumPerTag data)
    assert "placeholders" in script
    # The script builds partial SQL via insertCols.join — proving the
    # per-device path is used (the legacy D-27 path hard-coded
    # allColumns.size()).
    assert "insertCols" in script
    assert "insert into " in script


def test_bind_mode_safe_default_when_groups_empty() -> None:
    """Empty / missing bind groups must produce a safe no-op."""
    script = _build_batch_prepared_bind_preprocessor_body(
        **_minimal_bind_kwargs()
    )
    assert "log.warn" in script
    assert "bindGroups == null" in script or "bindGroups.isEmpty" in script


def test_bind_mode_requires_ptag_names_and_col_type_buckets() -> None:
    """Missing ptag_names / ptag_col_types / col_type_buckets must raise (D-28)."""
    with pytest.raises(ValueError, match="ptag_names"):
        _build_batch_prepared_preprocessor_body(
            **_minimal_full_kwargs(col_tag_bind_mode=True)
        )


# ---------------------------------------------------------------------------
# D-28: per-device sampler body (independent prepareStatement→close cycle)
# ---------------------------------------------------------------------------

def test_sampler_bind_mode_iterates_per_device_with_withcloseable() -> None:
    """Sampler bind branch must run prepareStatement→withCloseable per
    device so the JDBC driver batch buffer is released immediately.
    """
    script = _build_batch_prepared_sampler_body(
        table_name="iot_monitor.meters",
        insert_sql="insert into iot_monitor.meters (ts) values (?)",
        col_tag_bind_mode=True,
    )
    # Outer for-loop over preps (one entry per device)
    assert "for (int d = 0; d < preps.size" in script
    # Per-device prepareStatement + withCloseable
    assert "conn.prepareStatement(sql).withCloseable" in script
    # The per-device entry is closed by withCloseable before the next
    # device's prepareStatement — the sampler never accumulates more
    # than one device's batch buffer at a time.
    assert script.count("withCloseable") >= 2  # conn + pstmt


def test_sampler_bind_mode_does_not_use_legacy_batch_rows() -> None:
    """Sampler bind branch must read ``__BATCH_PREPS_<table>``, not the
    legacy ``__BATCH_ROWS_<table>``.
    """
    script = _build_batch_prepared_sampler_body(
        table_name="iot_monitor.meters",
        insert_sql="insert into iot_monitor.meters (ts) values (?)",
        col_tag_bind_mode=True,
    )
    assert "__BATCH_PREPS" in script
    assert "__BATCH_ROWS" not in script


def test_sampler_default_mode_unchanged() -> None:
    """Backward compat: ``col_tag_bind_mode=False`` (or absent) must
    keep the existing single-pstmt full-row path.
    """
    script = _build_batch_prepared_sampler_body(
        table_name="iot_monitor.meters",
        insert_sql="insert into iot_monitor.meters (ts) values (?)",
    )
    assert "__BATCH_ROWS" in script
    assert "__BATCH_PREPS" not in script


# ---------------------------------------------------------------------------
# Wrapper signature
# ---------------------------------------------------------------------------

def test_wrapper_threads_bind_mode_with_new_kwargs() -> None:
    """``build_batch_prepared_preprocessor_script`` must accept the new
    ``ptag_names`` / ``ptag_col_types`` / ``col_type_buckets`` kwargs
    and thread bind mode through to the body builder.
    """
    script = build_batch_prepared_preprocessor_script(
        table_name="iot_monitor.meters",
        first_ptag="ptag_varchar_1",
        batch_lines=1,
        ms_step=1000,
        col_tag_bind_mode=True,
        ptag_names=["ptag_varchar_1"],
        ptag_col_types=["varchar"],
        col_type_buckets={"col_int8": ["int8", "bigint", "int", "int2", "int4", "tinyint", "smallint"]},
        device_per_thread=1,
    )
    assert "__BATCH_PREPS" in script
    assert "bindGroups.get(deviceCode)" in script
