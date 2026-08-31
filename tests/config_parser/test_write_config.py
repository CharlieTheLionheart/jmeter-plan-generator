"""Tests for `WriteConfig` write-batch-mode-semantics DCR (2026-08-31).

Verifies the symmetric R-PAR-016 constraint expansion:
- `single_insert` requires `batch_lines == 1` (original R-PAR-016)
- `single_prepared` requires `batch_lines == 1` (DCR expansion)
- `batch_insert`, `batch_prepared`, `schemaless` accept any `batch_lines >= 1`
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config_parser.models import WriteConfig


def _build(mode: str, batch_lines: int) -> WriteConfig:
    """Build a minimal `WriteConfig` for validation testing."""
    return WriteConfig(tbl_name="t_smoke", mode=mode, batch_lines=batch_lines)


def test_single_prepared_batch_lines_one_ok():
    """`single_prepared + batch_lines=1` MUST validate (DCR decision 5/已收敛 1).

    Single PreparedStatement writes 1 row per INSERT — 1 row + 1
    bind param set.
    """
    cfg = _build("single_prepared", 1)
    assert cfg.batch_lines == 1
    assert cfg.mode == "single_prepared"


def test_single_prepared_batch_lines_gt_one_raises():
    """`single_prepared + batch_lines>1` MUST raise `ValidationError`.

    Single semantic = 1 row; `batch_lines>1` violates the business
    semantic. fail-fast at schema layer per Decision 3.
    """
    with pytest.raises(ValidationError) as excinfo:
        _build("single_prepared", 5)
    msg = str(excinfo.value)
    assert "single_prepared" in msg or "single_insert / single_prepared" in msg
    assert "batch_lines=1" in msg


def test_single_insert_batch_lines_one_backward_compat():
    """`single_insert + batch_lines=1` MUST keep working (R-PAR-016 preserved)."""
    cfg = _build("single_insert", 1)
    assert cfg.batch_lines == 1


def test_batch_modes_accept_arbitrary_batch_lines():
    """`batch_insert / batch_prepared / schemaless` MUST accept any
    `batch_lines >= 1` (DCR decision 5/已收敛 2).
    """
    for mode in ("batch_insert", "batch_prepared", "schemaless"):
        for bl in (1, 10, 60):
            cfg = _build(mode, bl)
            assert cfg.batch_lines == bl, f"{mode} + batch_lines={bl}"