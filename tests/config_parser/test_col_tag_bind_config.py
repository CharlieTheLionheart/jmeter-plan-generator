"""Tests for ``WriteConfig.col_tag_bind_mode`` and ``col_num_per_tag`` fields.

Per OpenSpec change ``col-tag-bind-write`` (2026-08-05):
- ``col_tag_bind_mode`` is per-table (WriteConfig), defaults to ``False``.
- ``col_num_per_tag`` must be > 0 when ``col_tag_bind_mode=True``.
- All 5 ``WriteMode`` values (including ``schemaless``) are accepted when
  ``col_tag_bind_mode=True``; no mode restriction.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config_parser.models import WriteConfig


def _minimal(mode: str = "prepare") -> dict:
    """Return the minimum required fields for a valid WriteConfig."""
    return {"tbl_name": "iot_monitor.meters", "mode": mode}


def test_default_mode_false_and_zero_per_tag() -> None:
    """Default values: ``col_tag_bind_mode=False`` + ``col_num_per_tag=0``."""
    cfg = WriteConfig(**_minimal())
    assert cfg.col_tag_bind_mode is False
    assert cfg.col_num_per_tag == 0


def test_explicit_false_accepted() -> None:
    """Explicit ``False`` + ``0`` is accepted (no validator kicks in)."""
    cfg = WriteConfig(**_minimal(), col_tag_bind_mode=False, col_num_per_tag=0)
    assert cfg.col_tag_bind_mode is False
    assert cfg.col_num_per_tag == 0


def test_true_with_positive_per_tag_accepted() -> None:
    """``True`` + positive ``col_num_per_tag`` is accepted."""
    cfg = WriteConfig(**_minimal(), col_tag_bind_mode=True, col_num_per_tag=5)
    assert cfg.col_tag_bind_mode is True
    assert cfg.col_num_per_tag == 5


def test_true_with_zero_per_tag_rejected() -> None:
    """``True`` + ``0`` is rejected: ``col_num_per_tag`` must be > 0."""
    with pytest.raises(ValidationError) as exc_info:
        WriteConfig(**_minimal(), col_tag_bind_mode=True, col_num_per_tag=0)
    msg = str(exc_info.value)
    assert "col_num_per_tag" in msg


def test_true_with_negative_per_tag_rejected() -> None:
    """``True`` + negative ``col_num_per_tag`` is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        WriteConfig(**_minimal(), col_tag_bind_mode=True, col_num_per_tag=-1)
    msg = str(exc_info.value)
    assert "col_num_per_tag" in msg


@pytest.mark.parametrize(
    "mode",
    [
        "direct",
        "direct",
        "prepare",
        "prepare",
        "schemaless",
    ],
)
def test_all_five_modes_accepted_when_bind_enabled(mode: str) -> None:
    """All 5 ``WriteMode`` values are accepted when ``col_tag_bind_mode=True``.

    Per OpenSpec Decision 7: ``col_tag_bind_mode`` is orthogonal to ``mode``.
    """
    cfg = WriteConfig(
        **_minimal(mode=mode), col_tag_bind_mode=True, col_num_per_tag=3
    )
    assert cfg.col_tag_bind_mode is True
    assert cfg.mode == mode
    assert cfg.col_num_per_tag == 3
