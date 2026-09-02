"""Tests for `WriteConfig` after mode enum consolidation (2026-09-02).

The 5-mode enum collapsed to 3 (`direct` / `prepare` / `schemaless`).
Single vs batch is now expressed purely via `batch_lines` (1 = single-row
semantics; >1 = MultiRowInsert / addBatch dispatch). The old R-PAR-016
symmetric "single_* requires batch_lines=1" validator was removed along
with the single_* literals.
"""

from __future__ import annotations

from config_parser.models import WriteConfig


def _build(mode: str, batch_lines: int) -> WriteConfig:
    """Build a minimal `WriteConfig` for validation testing."""
    return WriteConfig(tbl_name="t_smoke", mode=mode, batch_lines=batch_lines)


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