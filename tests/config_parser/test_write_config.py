"""Tests for `WriteConfig` after mode enum consolidation (2026-09-02).

The 5-mode enum collapsed to 3 (`direct` / `prepare` / `schemaless`).
Single vs batch is now expressed purely via `batch_lines` (1 = single-row
semantics; >1 = MultiRowInsert / addBatch dispatch). The old R-PAR-016
symmetric "single_* requires batch_lines=1" validator was removed along
with the single_* literals.

Also covers the write-missing-data D12(a) rule: one table ⇒ one
`write_config` entry (case-insensitive).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config_parser.models import ConnConfig, TestConfig, WriteConfig


def _build(mode: str, batch_lines: int) -> WriteConfig:
    """Build a minimal `WriteConfig` for validation testing."""
    return WriteConfig(tbl_name="t_smoke", mode=mode, batch_lines=batch_lines)


def _conn() -> ConnConfig:
    """``TestConfig.conn_config`` 是必填字段 —— 构造 TestConfig 时必须带上。

    它只是陪绑:同表唯一校验是**跨条目**约束,``WriteConfig`` 单条看不到
    同配置里的其它条目,所以只能挂在持有 ``write_config[]`` 的 ``TestConfig``
    上(见 ``TestConfig.check_write_config_unique_tables``)。
    """
    return ConnConfig(db_url="jdbc:kaiwudb://localhost:26257/defaultdb")


def _test_config(*tbl_names: str) -> TestConfig:
    return TestConfig(
        conn_config=_conn(),
        write_config=[
            WriteConfig(tbl_name=name, mode="prepare") for name in tbl_names
        ],
    )


def test_direct_accepts_batch_lines_one():
    """`direct + batch_lines=1` MUST validate (1-row INSERT)."""
    cfg = _build("direct", 1)
    assert cfg.batch_lines == 1
    assert cfg.mode == "direct"


def test_prepare_accepts_batch_lines_one():
    """`prepare + batch_lines=1` MUST validate (1 addBatch + executeBatch)."""
    cfg = _build("prepare", 1)
    assert cfg.batch_lines == 1
    assert cfg.mode == "prepare"


def test_all_modes_accept_arbitrary_batch_lines():
    """All 3 modes MUST accept any `batch_lines >= 1`."""
    for mode in ("direct", "prepare", "schemaless"):
        for bl in (1, 10, 60):
            cfg = _build(mode, bl)
            assert cfg.batch_lines == bl, f"{mode} + batch_lines={bl}"


# ---------------------------------------------------------------------------
# write-missing-data D12(a): one table ⇒ one write_config entry
# ---------------------------------------------------------------------------

def test_same_table_twice_is_rejected():
    """The same table MUST NOT be configured twice.

    The two write paths disagree on what "twice" means — the JDBC path
    generates two ThreadGroups writing the same table (doubling rows and
    throughput, stacking two missing policies), while the schemaless path
    silently lets the later entry overwrite the earlier one. Neither is
    the design intent: one entry per table.
    """
    with pytest.raises(ValidationError) as exc:
        _test_config("iot_monitor.t_cnc", "iot_monitor.t_cnc")

    assert "tbl_name" in str(exc.value), (
        f"error message must name the offending field; got:\n{exc.value}"
    )


def test_same_table_twice_different_case_is_rejected():
    """Table comparison MUST be case-insensitive.

    ``tbl_name`` is compared lower-cased elsewhere in the codebase
    (JDBC path normalises with ``.lower()``), so ``IOT_MONITOR.T_CNC``
    and ``iot_monitor.t_cnc`` are the same table.
    """
    with pytest.raises(ValidationError) as exc:
        _test_config("iot_monitor.t_cnc", "IOT_MONITOR.T_CNC")

    assert "tbl_name" in str(exc.value), (
        f"error message must name the offending field; got:\n{exc.value}"
    )


def test_distinct_tables_are_accepted():
    """Different tables MUST still be accepted."""
    cfg = _test_config("iot_monitor.t_cnc", "iot_monitor.t_motor")
    assert len(cfg.write_config) == 2