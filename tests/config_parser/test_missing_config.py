"""Tests for the write-missing-data ``MissingConfig`` model.

OpenSpec change ``write-missing-data`` tasks §4.1 — the ``missing`` 段 is
a **table-level** nested block under ``write_config[].missing``:

- ``probability`` is REQUIRED when the 段 exists (段存在则必填);
- ``ts_count`` / ``device_count`` default to ``0`` and MUST be non-negative;
- the 段 MUST NOT carry any field beyond those three;
- the two counts are bounded by the **same entry's** ``batch_lines`` /
  ``device_per_thread`` (取等合法 = 缺整轮,超过总数 → ``ValueError``).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config_parser.models import MissingConfig, WriteConfig


def _write(**kwargs) -> WriteConfig:
    """Build a ``WriteConfig`` with sensible defaults for the missing tests."""
    params = {
        "tbl_name": "iot_monitor.t_cnc",
        "mode": "prepare",
        "batch_lines": 5,
        "device_per_thread": 4,
    }
    params.update(kwargs)
    return WriteConfig(**params)


# ---------------------------------------------------------------------------
# §4.1(a) MissingConfig 自身字段
# ---------------------------------------------------------------------------

class TestMissingConfigFields:
    def test_probability_is_required(self):
        """``probability`` 必填 —— 段存在却漏配 = 静默失效,必须解析期拒绝。"""
        with pytest.raises(ValidationError) as exc:
            MissingConfig(ts_count=2)

        assert "probability" in str(exc.value), (
            f"error message must name the missing field; got:\n{exc.value}"
        )

    def test_probability_bounds(self):
        """``probability`` 取值域 [0.0, 1.0] —— 越界语义无定义。"""
        MissingConfig(probability=0.0)
        MissingConfig(probability=1.0)
        MissingConfig(probability=0.5)

        for bad in (1.5, -0.1):
            with pytest.raises(ValidationError) as exc:
                MissingConfig(probability=bad)
            assert "probability" in str(exc.value), (
                f"probability={bad} must be rejected; got:\n{exc.value}"
            )

    def test_counts_default_to_zero(self):
        cfg = MissingConfig(probability=0.5)
        assert cfg.ts_count == 0
        assert cfg.device_count == 0

    def test_counts_must_be_non_negative(self):
        for field in ("ts_count", "device_count"):
            with pytest.raises(ValidationError) as exc:
                MissingConfig(probability=0.5, **{field: -1})
            assert field in str(exc.value), (
                f"{field}=-1 must be rejected; got:\n{exc.value}"
            )

    def test_extra_field_is_forbidden(self):
        """段内出现其它字段 → ValueError(段内字段白名单)。"""
        with pytest.raises(ValidationError) as exc:
            MissingConfig(probability=0.5, ts_count=2, device_count=1, extra_field=7)

        assert "extra_field" in str(exc.value), (
            f"error message must name the offending field; got:\n{exc.value}"
        )

    def test_declared_values_are_preserved(self):
        cfg = MissingConfig(probability=0.5, ts_count=2, device_count=1)
        assert cfg.probability == 0.5
        assert cfg.ts_count == 2
        assert cfg.device_count == 1


# ---------------------------------------------------------------------------
# §4.1(b) WriteConfig.missing 挂载
# ---------------------------------------------------------------------------

class TestWriteConfigMissingField:
    def test_missing_defaults_to_none(self):
        assert _write().missing is None

    def test_missing_section_is_accepted(self):
        cfg = _write(missing={"probability": 0.5, "ts_count": 2, "device_count": 1})
        assert isinstance(cfg.missing, MissingConfig)
        assert cfg.missing.probability == 0.5
        assert cfg.missing.ts_count == 2
        assert cfg.missing.device_count == 1

    def test_missing_section_without_probability_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _write(missing={"ts_count": 2})

        assert "probability" in str(exc.value), (
            f"error message must name 'probability'; got:\n{exc.value}"
        )

    def test_both_counts_zero_is_accepted(self):
        """段存在但两个 count 都是 0 → 校验通过(合法,但无缺失效果)。"""
        cfg = _write(missing={"probability": 0.5})
        assert cfg.missing is not None
        assert cfg.missing.ts_count == 0
        assert cfg.missing.device_count == 0

    def test_probability_zero_is_accepted(self):
        """probability = 0.0 = 显式关闭缺失写入 → 解析期接受。"""
        cfg = _write(missing={"probability": 0.0, "ts_count": 2})
        assert cfg.missing.probability == 0.0


# ---------------------------------------------------------------------------
# §4.1(c) 跨字段校验:count 上界取自同条目的 batch_lines / device_per_thread
# ---------------------------------------------------------------------------

class TestMissingCountsBound:
    def test_ts_count_equal_to_batch_lines_is_accepted(self):
        """取等合法 = 缺整轮。"""
        cfg = _write(batch_lines=5, missing={"probability": 0.5, "ts_count": 5})
        assert cfg.missing.ts_count == 5

    def test_device_count_equal_to_device_per_thread_is_accepted(self):
        cfg = _write(device_per_thread=4, missing={"probability": 0.5, "device_count": 4})
        assert cfg.missing.device_count == 4

    def test_ts_count_over_batch_lines_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _write(batch_lines=5, missing={"probability": 0.5, "ts_count": 6})

        assert "ts_count" in str(exc.value), (
            f"error message must name 'ts_count'; got:\n{exc.value}"
        )

    def test_device_count_over_device_per_thread_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _write(device_per_thread=4, missing={"probability": 0.5, "device_count": 5})

        assert "device_count" in str(exc.value), (
            f"error message must name 'device_count'; got:\n{exc.value}"
        )

    def test_bounds_are_per_entry(self):
        """上界按各自条目的参数判定 —— 表 A 越界不影响表 B(此处只验 A 失败)。"""
        with pytest.raises(ValidationError) as exc:
            _write(batch_lines=3, missing={"probability": 0.5, "ts_count": 4})

        assert "ts_count" in str(exc.value)

    def test_no_missing_section_skips_cross_field_check(self):
        """未声明 missing 段时不做任何跨字段校验。"""
        cfg = _write(batch_lines=1, device_per_thread=1)
        assert cfg.missing is None
