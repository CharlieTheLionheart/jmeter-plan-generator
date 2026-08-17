"""Tests for the col_tag_bind_mode branch of the REST Write preprocessor.

Per OpenSpec change ``col-tag-bind-write`` (2026-08-05) tasks.md §5:
- ``col_tag_bind_mode=True`` makes the REST Write PreProcessor read
  ``__SHARED_MEM_{db}_{table}_bind`` (the bind-namespaced map), pick the
  per-group column subset, and emit InfluxDB Line with only those
  ``field_set`` entries. The ``tag_set`` retains the first primary tag
  (device_id), and all regular tags fall back to the column-seed rows
  (consistent with the non-bind branch).
- Empty groups → ``Thread.currentThread().stop()`` (the existing B5 guard path;
  D-12 (2026-08-11) replaces the no-arg ``JMeterContext.stopThread()`` (absent in
  JMeter 5.6.3 — Method Summary on jmeter.apache.org has no stop method)).
- When ``col_tag_bind_mode`` is False the script body is unchanged from
  the pre-feature behavior (regression).
"""

from __future__ import annotations

import pytest

from config_parser.models import (
    ColTypeConfig,
    ConnConfig,
    PrimaryTagColTypeConfig,
    TestConfig,
    TestModelConfig,
    TsDbConfig,
    TsTableConfig,
    WriteConfig,
)
from jmx_skeleton_generator.generators.rest_write_groups import (
    _build_rest_write_preprocessor_script,
)


def _ts_table() -> TsTableConfig:
    # type_proportion sums must equal 1.0 (validator); split 3-way.
    return TsTableConfig(
        name="meters",
        data_col_count=3,
        primary_tag_count=1,
        regular_tag_count=0,
        data_cols=[
            ColTypeConfig(col_type="int8", type_proportion=0.34, val_range="[1,10]", seed_num=4),
            ColTypeConfig(col_type="int8", type_proportion=0.33, val_range="[1,10]", seed_num=4),
            ColTypeConfig(col_type="int8", type_proportion=0.33, val_range="[1,10]", seed_num=4),
        ],
        primary_tags=[
            PrimaryTagColTypeConfig(
                col_type="varchar(32)", type_proportion=1.0, val_range="enum:X,Y", seed_num=4
            )
        ],
    )


def test_bind_mode_emits_subset_fields_in_line() -> None:
    """Bind-mode PreProcessor reads ``__SHARED_MEM_*_bind`` and looks up the
    per-group ``col_names`` + ``row_values`` to assemble a subset
    ``field_set``.
    """
    ts = _ts_table()
    script = _build_rest_write_preprocessor_script(
        db="iot_monitor",
        table="meters",
        ts_table=ts,
        col_tag_bind_mode=True,
        col_num_per_tag=2,
        num_threads=4,
    )

    assert "__SHARED_MEM_iot_monitor_meters_bind" in script, (
        "bind-mode script must read the bind-namespaced shared memory"
    )
    # D-21 (2026-08-14): no hash-based group_id lookup — SetupTG keys
    # the row dict by literal deviceCode, so the Write TG prep looks
    # up by the same deviceCode.
    assert "hashCode" not in script, (
        f"D-21 removed hashCode-based group_id lookup; got:\n{script}"
    )
    assert "%numThreads" not in script and "% numThreads" not in script, (
        f"D-21 removed mod-numThreads grouping; got:\n{script}"
    )
    assert "bindGroups.get(deviceCode)" in script, (
        f"D-21 Write TG must lookup row dict by deviceCode; got:\n{script}"
    )
    # Field-set values are read from the bind row dict, not the
    # legacy __SHARED_MEM_*_columns header.
    assert "__SHARED_MEM_iot_monitor_meters_columns" not in script


def test_bind_mode_keeps_all_tags_in_line() -> None:
    """Bind-mode still emits ``device_id`` as a tag (first ptag) so the
    InfluxDB Line keeps the tag_set populated.
    """
    ts = _ts_table()
    script = _build_rest_write_preprocessor_script(
        db="iot_monitor",
        table="meters",
        ts_table=ts,
        col_tag_bind_mode=True,
        col_num_per_tag=2,
        num_threads=4,
    )

    assert "deviceIdentifier" in script or "deviceCode" in script, (
        "bind-mode script must compute deviceCode for the first ptag"
    )
    assert "tagMap" in script, "tagMap construction must be present"


def test_default_mode_unchanged() -> None:
    """Regression: ``col_tag_bind_mode=False`` keeps the legacy full-row
    read path (``__SHARED_MEM_*_columns`` header + per-row data).
    """
    ts = _ts_table()
    script = _build_rest_write_preprocessor_script(
        db="iot_monitor",
        table="meters",
        ts_table=ts,
        col_tag_bind_mode=False,
        col_num_per_tag=0,
        num_threads=1,
    )

    assert "__SHARED_MEM_iot_monitor_meters_bind" not in script, (
        "non-bind mode must NOT read the bind namespace"
    )
    assert "__SHARED_MEM_iot_monitor_meters_columns" in script, (
        "non-bind mode must still read the legacy columns header"
    )
    # D-23 (2026-08-14): non-bind mode now uses spec §4 L327 cyclic-fill
    # (random start index, never pop) instead of ``rows.remove(0)``.
    # D-24 (2026-08-14): batch_lines lines per prep call (default 1).
    assert "rows.remove(0)" not in script, (
        "D-23 removed rows.remove(0) — cyclic-fill picks random start + wrap"
    )
    assert "nextInt(rows.size())" in script, (
        "D-23 non-bind prep picks a random start row index"
    )
    assert "int batchLines = 1" in script, (
        "D-24 default batch_lines=1 preserves single-line per prep"
    )


def test_bind_mode_no_group_returns_safe_default() -> None:
    """When the bind groups map is empty, the PreProcessor must stop the
    thread (consistent with the B5 fix for the legacy path) rather than
    emit a half-populated InfluxDB Line.
    """
    ts = _ts_table()
    script = _build_rest_write_preprocessor_script(
        db="iot_monitor",
        table="meters",
        ts_table=ts,
        col_tag_bind_mode=True,
        col_num_per_tag=2,
        num_threads=4,
    )

    assert "vars.put('request_body', '')" in script, (
        "bind-mode script must guard against empty groups via empty-body sentinel "
        "(JMeter 5.6.3 has no stopThread API; Thread.stop() throws on Java 21+)"
    )
    assert "ctx.stopThread" not in script, (
        "bind-mode script must NOT use ctx.stopThread() (absent in JMeter 5.6.3 JMeterContext)"
    )
    assert "Thread.currentThread().stop" not in script, (
        "bind-mode script must NOT use Thread.currentThread().stop() (Java 21+ throws)"
    )
