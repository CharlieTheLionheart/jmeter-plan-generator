"""Tests for the empty shared-memory pool failure mode (write-missing-data D11).

Background
----------

``SharedMemoryLoader`` (SetupTG) used to swallow CSV-load failures:
``log.error`` + ``props.put(rowsKey, [])``. The write path then found an
empty pool and *silently degraded*:

- 5 consumption points did ``log.warn(...)`` + early ``return`` — the
  sampler reported success while writing nothing (test run green, zero
  rows in the table).
- 1 consumption point (``prepare`` non-bind) had no guard at all and hit
  ``ArithmeticException: / by zero`` at ``% totalRows``.

The new contract: an empty pool is a **business exception** — the
consumption point throws with table name + shared-memory key + a
"seed CSV load failed" hint, so the failure surfaces as a sampler error
instead of a silently green test.

The guard MUST cover both ``null`` (the loader no longer puts an empty
array, so the consumer may read ``null``) and an empty array.
"""

from __future__ import annotations

import re

import pytest

from config_parser.models import (
    ColTypeConfig,
    PrimaryTagColTypeConfig,
    TsTableConfig,
)
from jmx_skeleton_generator.generators.rest_write_groups import (
    _build_rest_write_preprocessor_script,
)
from jmx_skeleton_generator.generators.write_groups import (
    _build_batch_prepared_bind_preprocessor_body,
    _build_batch_prepared_preprocessor_body,
    _build_inline_sql_preprocessor_script,
)


# Guard form required by design D11: null AND empty array.
_GUARD_RE = re.compile(r"if \((\w+) == null \|\| \1\.isEmpty\(\)\)")

_MESSAGE_HEAD = "SharedMemory pool empty for table "
_MESSAGE_TAIL = "seed CSV load failed"


def _ts_table() -> TsTableConfig:
    return TsTableConfig(
        name="meters",
        data_col_count=1,
        primary_tag_count=1,
        regular_tag_count=0,
        data_cols=[
            ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="[1,10]", seed_num=4),
        ],
        primary_tags=[
            PrimaryTagColTypeConfig(
                col_type="varchar(32)", type_proportion=1.0, val_range="enum:X,Y", seed_num=4
            )
        ],
    )


def _inline_direct(col_tag_bind_mode: bool) -> str:
    return _build_inline_sql_preprocessor_script(
        db="iot_monitor",
        table="t_cnc",
        columns=["ts", "ptag_varchar_1", "col_int8_1"],
        first_ptag_column="ptag_varchar_1",
        device_per_thread=2,
        batch_lines=5,
        col_tag_bind_mode=col_tag_bind_mode,
    )


def _prepare_non_bind() -> str:
    return _build_batch_prepared_preprocessor_body(
        table_name="iot_monitor.t_cnc",
        first_ptag="ptag_varchar_1",
        batch_lines=5,
        ms_step=1000,
        device_per_thread=2,
    )


def _prepare_bind() -> str:
    return _build_batch_prepared_bind_preprocessor_body(
        table_name="iot_monitor.t_cnc",
        ptag_names=["ptag_varchar_1"],
        ptag_col_types=["varchar"],
        col_type_buckets={"col_int8": ["int8", "bigint"]},
        batch_lines=5,
        ms_step=1000,
        device_per_thread=2,
    )


def _rest_write(col_tag_bind_mode: bool) -> str:
    return _build_rest_write_preprocessor_script(
        db="iot_monitor",
        table="meters",
        ts_table=_ts_table(),
        col_tag_bind_mode=col_tag_bind_mode,
        col_num_per_tag=2 if col_tag_bind_mode else 0,
        num_threads=4,
        device_per_thread=2,
        batch_lines=5,
    )


# (label, script factory, table expression in the message, legacy markers
#  that must be gone).
_SITES = [
    (
        "direct non-bind",
        lambda: _inline_direct(False),
        'db + "." + table',
        ["log.warn(\"DirectInsertPrep: shared memory empty", "-- no rows in shared memory"],
    ),
    (
        "direct bind",
        lambda: _inline_direct(True),
        'db + "." + table',
        ["log.warn(\"DirectInsertPrep: empty bind groups", '"SELECT 1"'],
    ),
    (
        "prepare non-bind",
        _prepare_non_bind,
        "tableName",
        [],
    ),
    (
        "prepare bind",
        _prepare_bind,
        "tableName",
        ["log.warn(\"BatchPreparedBindPrep: bind groups empty"],
    ),
    (
        "schemaless non-bind",
        lambda: _rest_write(False),
        "db + '.' + measurement",
        ["log.warn('REST_Write_meters_prep: rows empty", "vars.put('request_body', '')"],
    ),
    (
        "schemaless bind",
        lambda: _rest_write(True),
        "db + '.' + measurement",
        ["log.warn('REST_Write_bind_prep: bind groups empty", "vars.put('request_body', '')"],
    ),
]

_IDS = [s[0] for s in _SITES]


@pytest.mark.parametrize("label,factory,_table_expr,_legacy", _SITES, ids=_IDS)
def test_empty_pool_raises_runtime_exception(label, factory, _table_expr, _legacy) -> None:
    """Every consumption point MUST throw a RuntimeException on an empty pool."""
    script = factory()
    assert "throw new RuntimeException" in script, (
        f"{label}: empty pool must raise a RuntimeException"
    )


@pytest.mark.parametrize("label,factory,_table_expr,_legacy", _SITES, ids=_IDS)
def test_guard_covers_null_and_empty(label, factory, _table_expr, _legacy) -> None:
    """The guard MUST check ``null`` AND the empty array."""
    script = factory()
    assert _GUARD_RE.search(script), (
        f"{label}: expected a 'if (X == null || X.isEmpty())' guard; got:\n{script}"
    )


@pytest.mark.parametrize("label,factory,_table_expr,_legacy", _SITES, ids=_IDS)
def test_message_carries_context(label, factory, _table_expr, _legacy) -> None:
    """The message MUST carry table name + shared-memory key + a hint."""
    script = factory()
    assert _MESSAGE_HEAD in script, f"{label}: missing message head"
    assert _table_expr in script, f"{label}: message must name the table ({_table_expr})"
    assert "rowsKey" in script, f"{label}: message must carry the shared-memory key"
    assert _MESSAGE_TAIL in script, f"{label}: message must carry the failure hint"


@pytest.mark.parametrize("label,factory,_table_expr,legacy", _SITES, ids=_IDS)
def test_no_silent_degradation(label, factory, _table_expr, legacy) -> None:
    """The old ``log.warn`` + early-return degradation must be gone."""
    script = factory()
    for marker in legacy:
        assert marker not in script, (
            f"{label}: silent-degradation marker still present: {marker}"
        )
