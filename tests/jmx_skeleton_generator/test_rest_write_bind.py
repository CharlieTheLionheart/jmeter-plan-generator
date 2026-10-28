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
    generate_rest_write_thread_group,
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


def test_bind_mode_no_group_raises_business_exception() -> None:
    """When the bind groups map is empty, the PreProcessor MUST throw.

    write-missing-data D11: 旧的"置空 body 静默退出"会让整轮测试
    "全绿但一行没写"——空种子池必须尽早暴露为 sampler error。
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

    assert "throw new RuntimeException" in script, (
        "bind-mode script must raise a RuntimeException on an empty pool"
    )
    assert "seed CSV load failed" in script, (
        "bind-mode script must carry the failure hint"
    )
    assert "vars.put('request_body', '')" not in script, (
        "bind-mode script must NOT silently degrade to an empty body"
    )
    assert "ctx.stopThread" not in script, (
        "bind-mode script must NOT use ctx.stopThread() (absent in JMeter 5.6.3 JMeterContext)"
    )
    assert "Thread.currentThread().stop" not in script, (
        "bind-mode script must NOT use Thread.currentThread().stop() (Java 21+ throws)"
    )


# ---------------------------------------------------------------------------
# write-missing-data D12(b): schemaless table lookup is case-insensitive
# ---------------------------------------------------------------------------

def _single_table_model() -> TestModelConfig:
    """Model with one lowercase table ``db_iot.meters``."""
    return TestModelConfig(
        ts_dbs=[
            TsDbConfig(
                name="db_iot",
                tables=[
                    TsTableConfig(
                        name="meters",
                        data_col_count=1,
                        data_cols=[
                            ColTypeConfig(
                                col_type="float4",
                                type_proportion=1.0,
                                val_range="0..100",
                                seed_num=100,
                            )
                        ],
                        primary_tag_count=1,
                        primary_tags=[
                            PrimaryTagColTypeConfig(
                                col_type="varchar(64)",
                                type_proportion=1.0,
                                val_range='"device_{1}"',
                            )
                        ],
                        regular_tag_count=0,
                        regular_tags=[],
                    )
                ],
            )
        ],
    )


def _rest_api_config() -> dict:
    return {
        "write_url_path": "/restapi/influxdb",
        "default_db": "db_iot",
        "https_mode": "tls",
        "ca_cert_path": "/etc/kaiwudb/certs/ca.crt",
        "timezone": None,
    }


def test_uppercase_tbl_name_matches_lowercase_model_table() -> None:
    """cfg's ``tbl_name`` case MUST NOT decide whether the table matches.

    The JDBC path normalises ``tbl_name`` with ``.lower()``; the
    schemaless path did not, so ``IOT_MONITOR.T_CNC`` in the cfg never
    matched the model's lowercase table and the generator raised
    ``missing write_config for ts_table``. Both paths must tolerate the
    same inputs.
    """
    elems = generate_rest_write_thread_group(
        _single_table_model(),
        rest_api_config=_rest_api_config(),
        write_configs=[
            WriteConfig(tbl_name="DB_IOT.METERS", throughput=60.0, mode="schemaless"),
        ],
    )

    assert elems, "uppercase tbl_name must still produce a write ThreadGroup"

