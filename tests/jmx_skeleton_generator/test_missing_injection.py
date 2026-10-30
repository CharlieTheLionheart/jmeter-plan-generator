"""Tests for the missing-data Groovy injection (write-missing-data §6).

The missing-data rule is injected at **6 assembly points** — one per
write path (``direct`` / ``prepare`` / ``schemaless`` × bind / non-bind).
All 6 share the same decision rule (tail truncation on both dimensions,
intersection) and the same round-relative index semantics:

- the **device** index is the position inside *this round's* grid
  (``d - <device loop start>``), never the absolute device number;
- the **timestamp** index is the position inside the round's timestamp
  sequence (the inner loop variable).

Two properties are asserted here:

1. **Injection** — when the 段 is declared with ``probability > 0`` the
   generated script carries the decision block and the per-cell skip.
2. **Zero regression** (design D6) — when the 段 is absent, or declared
   with ``probability == 0``, the generated script is **byte-identical**
   to the not-declared one and carries none of the missing identifiers.
"""

from __future__ import annotations

import re

import pytest

from config_parser.models import (
    ColTypeConfig,
    MissingConfig,
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


# Identifiers that only exist when the missing logic is injected.
_MISSING_TOKENS = (
    "missingProbability",
    "missingTsCount",
    "missingDeviceCount",
    "applyMissing",
    "skipMissingRow",
    "deviceMissingHit",
    "tsMissingHit",
)


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


def _inline_direct(missing, col_tag_bind_mode: bool) -> str:
    return _build_inline_sql_preprocessor_script(
        db="iot_monitor",
        table="t_cnc",
        columns=["ts", "ptag_varchar_1", "col_int8_1"],
        first_ptag_column="ptag_varchar_1",
        device_per_thread=2,
        batch_lines=5,
        col_tag_bind_mode=col_tag_bind_mode,
        missing=missing,
    )


def _prepare_non_bind(missing) -> str:
    return _build_batch_prepared_preprocessor_body(
        table_name="iot_monitor.t_cnc",
        first_ptag="ptag_varchar_1",
        batch_lines=5,
        ms_step=1000,
        device_per_thread=2,
        missing=missing,
    )


def _prepare_bind(missing) -> str:
    return _build_batch_prepared_bind_preprocessor_body(
        table_name="iot_monitor.t_cnc",
        ptag_names=["ptag_varchar_1"],
        ptag_col_types=["varchar"],
        col_type_buckets={"col_int8": ["int8", "bigint"]},
        batch_lines=5,
        ms_step=1000,
        device_per_thread=2,
        missing=missing,
    )


def _rest_write(missing, col_tag_bind_mode: bool) -> str:
    return _build_rest_write_preprocessor_script(
        db="iot_monitor",
        table="meters",
        ts_table=_ts_table(),
        col_tag_bind_mode=col_tag_bind_mode,
        col_num_per_tag=2 if col_tag_bind_mode else 0,
        num_threads=4,
        device_per_thread=2,
        batch_lines=5,
        missing=missing,
    )


# (label, script factory, device-index expression, ts loop variable).
_SITES = [
    ("direct non-bind", lambda m: _inline_direct(m, False), "d - localDeviceStart", "r"),
    ("direct bind", lambda m: _inline_direct(m, True), "d - deviceStart", "r"),
    ("prepare non-bind", _prepare_non_bind, "d - deviceStart", "i"),
    ("prepare bind", _prepare_bind, "d - deviceStart", "r"),
    ("schemaless non-bind", lambda m: _rest_write(m, False), "d - deviceStart", "b"),
    ("schemaless bind", lambda m: _rest_write(m, True), "d - deviceStart", "b"),
]

_IDS = [s[0] for s in _SITES]

_ENABLED = MissingConfig(probability=1.0, ts_count=2, device_count=1)
_DISABLED = MissingConfig(probability=0.0, ts_count=2, device_count=1)


@pytest.mark.parametrize("label,factory,_dev_expr,_ts_var", _SITES, ids=_IDS)
def test_missing_block_is_injected(label, factory, _dev_expr, _ts_var) -> None:
    """启用缺失时,脚本必须含完整的缺失判定块。"""
    script = factory(_ENABLED)
    for token in _MISSING_TOKENS:
        assert token in script, f"{label}: 缺失块缺少标识符 {token}"


@pytest.mark.parametrize("label,factory,_dev_expr,_ts_var", _SITES, ids=_IDS)
def test_skip_line_is_injected(label, factory, _dev_expr, _ts_var) -> None:
    """内层循环必须含 ``if (applyMissing && skipMissingRow(...)) { continue }``。"""
    script = factory(_ENABLED)
    pattern = re.compile(
        r"if \(applyMissing && skipMissingRow\(.*\)\)\s*\{[^}]*continue[^}]*\}"
    )
    assert pattern.search(script), (
        f"{label}: 内层循环缺少缺失跳过判定; got:\n{script}"
    )


@pytest.mark.parametrize("label,factory,_dev_expr,_ts_var", _SITES, ids=_IDS)
def test_device_index_is_round_relative(label, factory, _dev_expr, _ts_var) -> None:
    """设备下标必须是本轮相对下标,不是绝对设备号 ``d``。"""
    script = factory(_ENABLED)
    call = re.search(r"skipMissingRow\(([^,]+),\s*([^)]+)\)", script)
    assert call, f"{label}: 找不到 skipMissingRow 调用"
    dev_arg, ts_arg = call.group(1), call.group(2)
    assert _dev_expr in dev_arg, (
        f"{label}: 设备下标应为相对下标 {_dev_expr!r},实际 {dev_arg!r}"
    )
    assert "d -" in dev_arg, f"{label}: 设备下标必须做相对换算,实际 {dev_arg!r}"
    assert ts_arg.strip() == _ts_var, (
        f"{label}: 时间戳下标应为内层循环变量 {_ts_var!r},实际 {ts_arg!r}"
    )


@pytest.mark.parametrize("label,factory,_dev_expr,_ts_var", _SITES, ids=_IDS)
def test_probability_is_baked(label, factory, _dev_expr, _ts_var) -> None:
    """缺失参数必须烘焙进脚本(表级隔离在生成期成立)。"""
    script = factory(_ENABLED)
    assert "missingProbability = 1.0d" in script, f"{label}: probability 未烘焙"
    assert "missingTsCount = 2" in script, f"{label}: ts_count 未烘焙"
    assert "missingDeviceCount = 1" in script, f"{label}: device_count 未烘焙"


@pytest.mark.parametrize("label,factory,_dev_expr,_ts_var", _SITES, ids=_IDS)
def test_zero_regression_without_missing_section(label, factory, _dev_expr, _ts_var) -> None:
    """未声明 missing 段 → 脚本不含任何缺失标识符(逐字节零回归)。"""
    script = factory(None)
    for token in _MISSING_TOKENS:
        assert token not in script, f"{label}: 未启用缺失却出现标识符 {token}"


@pytest.mark.parametrize("label,factory,_dev_expr,_ts_var", _SITES, ids=_IDS)
def test_zero_regression_probability_zero(label, factory, _dev_expr, _ts_var) -> None:
    """``probability = 0.0`` → 脚本与未声明 missing 段**逐字节一致**。"""
    disabled = factory(_DISABLED)
    baseline = factory(None)
    assert disabled == baseline, (
        f"{label}: probability=0.0 的脚本与未声明 missing 段不一致\n"
        f"--- disabled ---\n{disabled}\n--- baseline ---\n{baseline}"
    )
