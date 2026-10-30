"""Tests for ``utils.preprocessor_helpers``."""

from __future__ import annotations

import pytest

from utils.preprocessor_helpers import (
    PreprocessorHelperError,
    all_groovy_decls,
    build_device_identifier,
    calculate_device_number,
    calculate_timestamps,
    clone_rows,
    groovy_missing_data_decl,
    should_skip_row,
)


class TestCalculateTimestamps:
    def test_basic_progression(self):
        out = calculate_timestamps(
            base_time_ms=1_000_000,
            batch_seq=2,
            ms_step=1000,
            batch_lines=10,
            row_count=10,
        )
        # base + batch_seq*ms_step + i*(ms_step/batch_lines)
        assert out[0] == 1_002_000
        assert out[9] == 1_002_000 + 9 * 100

    def test_row_count_smaller_than_batch_lines(self):
        out = calculate_timestamps(
            base_time_ms=0,
            batch_seq=0,
            ms_step=1000,
            batch_lines=10,
            row_count=4,
        )
        assert out == [0, 100, 200, 300]

    def test_integer_division_when_ms_step_lt_batch_lines(self):
        # ms_step < batch_lines ⇒ intra-step rounds down to 0.
        out = calculate_timestamps(
            base_time_ms=0,
            batch_seq=0,
            ms_step=5,
            batch_lines=10,
            row_count=3,
        )
        assert out == [0, 0, 0]

    def test_long_arithmetic_avoids_overflow(self):
        # batch_seq=10M × ms_step=10k ⇒ 10^11 ms ⇒ exceeds int32 range,
        # must be produced via long arithmetic without overflow.
        out = calculate_timestamps(
            base_time_ms=0,
            batch_seq=10_000_000,
            ms_step=10_000,
            batch_lines=10,
            row_count=2,
        )
        # intra_step = ms_step // batch_lines = 10_000 // 10 = 1_000
        assert out[0] == 10_000_000 * 10_000
        assert out[1] == 10_000_000 * 10_000 + 1_000

    def test_zero_batch_lines_raises(self):
        with pytest.raises(PreprocessorHelperError):
            calculate_timestamps(
                base_time_ms=0,
                batch_seq=0,
                ms_step=1000,
                batch_lines=0,
                row_count=1,
            )

    def test_negative_row_count_raises(self):
        with pytest.raises(PreprocessorHelperError):
            calculate_timestamps(
                base_time_ms=0,
                batch_seq=0,
                ms_step=1000,
                batch_lines=5,
                row_count=-1,
            )


class TestCalculateDeviceNumber:
    def test_basic_formula(self):
        assert (
            calculate_device_number(
                thread_num=2,
                device_start=0,
                device_per_thread=3,
                row_index=5,
            )
            == 8
        )

    def test_device_start_offset(self):
        assert (
            calculate_device_number(
                thread_num=0,
                device_start=100,
                device_per_thread=4,
                row_index=2,
            )
            == 102
        )

    def test_row_index_wraps_at_device_per_thread(self):
        assert (
            calculate_device_number(
                thread_num=1,
                device_start=0,
                device_per_thread=4,
                row_index=6,
            )
            == 6
        )

    def test_zero_device_per_thread_raises(self):
        with pytest.raises(PreprocessorHelperError):
            calculate_device_number(
                thread_num=0,
                device_start=0,
                device_per_thread=0,
                row_index=0,
            )

    def test_negative_row_index_raises(self):
        with pytest.raises(PreprocessorHelperError):
            calculate_device_number(
                thread_num=0,
                device_start=0,
                device_per_thread=1,
                row_index=-1,
            )


class TestBuildDeviceIdentifier:
    def test_default_format(self):
        assert build_device_identifier(42) == "device_42"


class TestCloneRows:
    def test_independent_rows(self):
        rows = [[1, 2, 3], [4, 5, 6]]
        cloned = clone_rows(rows)
        cloned[0][0] = 99
        assert rows[0][0] == 1

    def test_preserves_length(self):
        cloned = clone_rows([["a", "b"], ["c", "d"], ["e", "f"]])
        assert len(cloned) == 3


class TestGroovyDecls:
    def test_all_groovy_decls_contains_aligned_helpers(self):
        decls = all_groovy_decls()
        # 当前 generator 仍调用的 Groovy helper
        assert "calculateDeviceNumber" in decls
        assert "deviceIdentifier" in decls
        assert "cloneRows" in decls

    def test_helper_declares_long_types(self):
        # calculateDeviceNumber 接受 long 参数避免运行时 overflow
        decls = all_groovy_decls()
        assert "long thread_num" in decls
        assert "long device_start" in decls
        assert "long device_per_thread" in decls

    def test_helper_includes_division_guard(self):
        decls = all_groovy_decls()
        # 至少一个 helper 含 >0 边界守卫
        assert "must be > 0" in decls

    def test_calculate_local_device_start_decl_is_emitted(self):
        """multi-end tasks §2.1: helper appears in all_groovy_decls()."""
        from utils.preprocessor_helpers import (
            groovy_calculate_local_device_start_decl,
        )
        decl = groovy_calculate_local_device_start_decl()
        assert "long calculateLocalDeviceStart" in decl
        assert "long deviceStart, int threadNum, long devicePerThread" in decl

    def test_calculate_local_device_start_in_all_groovy_decls(self):
        decls = all_groovy_decls()
        assert "calculateLocalDeviceStart" in decls

    def test_calculate_local_device_start_guard_is_present(self):
        from utils.preprocessor_helpers import (
            groovy_calculate_local_device_start_decl,
        )
        assert "must be > 0" in groovy_calculate_local_device_start_decl()


# ---------------------------------------------------------------------------
# write-missing-data D10: Python / Groovy 同构的缺失判定 helper
# ---------------------------------------------------------------------------


class TestShouldSkipRow:
    """尾部截断 + 设备×时间戳取交集的判定式(纯比较,无随机源)。"""

    def test_only_ts_count_skips_tail_ts_for_all_devices(self):
        """只配 missing_ts_count=2 → 尾部 2 个 ts 的**所有设备**行命中。"""
        def skipped(dev_idx: int, ts_idx: int) -> bool:
            return should_skip_row(
                dev_idx, ts_idx,
                missing_device_count=0, missing_ts_count=2,
                device_per_thread=4, batch_lines=5,
            )

        for dev_idx in range(4):
            assert skipped(dev_idx, 3), f"dev {dev_idx} ts 3 应命中"
            assert skipped(dev_idx, 4), f"dev {dev_idx} ts 4 应命中"
            assert not skipped(dev_idx, 0)
            assert not skipped(dev_idx, 1)
            assert not skipped(dev_idx, 2)

    def test_only_device_count_skips_tail_device_for_all_ts(self):
        """只配 missing_device_count=1 → 尾部 1 个设备的**所有 ts** 行命中。"""
        def skipped(dev_idx: int, ts_idx: int) -> bool:
            return should_skip_row(
                dev_idx, ts_idx,
                missing_device_count=1, missing_ts_count=0,
                device_per_thread=4, batch_lines=5,
            )

        for ts_idx in range(5):
            assert skipped(3, ts_idx), f"dev 3 ts {ts_idx} 应命中"
        for dev_idx in range(3):
            assert not skipped(dev_idx, 4), f"dev {dev_idx} 不应命中"

    def test_both_counts_take_intersection(self):
        """两个都配 → 交集(设备尾部 ∩ ts 尾部)。"""
        def skipped(dev_idx: int, ts_idx: int) -> bool:
            return should_skip_row(
                dev_idx, ts_idx,
                missing_device_count=2, missing_ts_count=2,
                device_per_thread=4, batch_lines=5,
            )

        # 命中设备尾部 {2,3} 且 命中 ts 尾部 {3,4}
        assert skipped(2, 3) and skipped(2, 4)
        assert skipped(3, 3) and skipped(3, 4)
        # 只命中一个维度 → 照常写入
        assert not skipped(2, 0)
        assert not skipped(0, 3)

    def test_intersection_skips_exactly_m_times_n_cells(self):
        """丢弃格数恒为 M × N —— 与 spec 的 Scenario 一致。"""
        m, n = 2, 2
        skipped = sum(
            1
            for dev_idx in range(4)
            for ts_idx in range(5)
            if should_skip_row(
                dev_idx, ts_idx,
                missing_device_count=m, missing_ts_count=n,
                device_per_thread=4, batch_lines=5,
            )
        )
        assert skipped == m * n

    def test_zero_counts_skip_nothing(self):
        """两个 count 都是 0 → 段合法但无缺失效果,一格都不丢。"""
        assert not should_skip_row(
            0, 0,
            missing_device_count=0, missing_ts_count=0,
            device_per_thread=4, batch_lines=5,
        )

    def test_ts_count_equal_batch_lines_skips_everything(self):
        """ts_count == batch_lines → 全部命中(缺整轮)。"""
        for dev_idx in range(3):
            for ts_idx in range(4):
                assert should_skip_row(
                    dev_idx, ts_idx,
                    missing_device_count=0, missing_ts_count=4,
                    device_per_thread=3, batch_lines=4,
                )

    def test_device_count_equal_device_per_thread_skips_everything(self):
        """device_count == device_per_thread → 全部命中(缺整轮)。"""
        for dev_idx in range(3):
            for ts_idx in range(4):
                assert should_skip_row(
                    dev_idx, ts_idx,
                    missing_device_count=3, missing_ts_count=0,
                    device_per_thread=3, batch_lines=4,
                )

    def test_device_index_is_round_relative(self):
        """设备下标是本轮相对下标 —— 绝对设备号不影响尾部语义。"""
        # 本轮第 3 个设备(相对下标 2)在 missing_device_count=1 时命中
        assert should_skip_row(
            2, 0,
            missing_device_count=1, missing_ts_count=0,
            device_per_thread=3, batch_lines=5,
        )
        assert not should_skip_row(
            1, 0,
            missing_device_count=1, missing_ts_count=0,
            device_per_thread=3, batch_lines=5,
        )


class TestGroovyMissingDataDecl:
    """Groovy 版声明块 —— 注入到 6 处装配点的同一段代码。"""

    def _decl(self, **kwargs) -> str:
        params = {
            "probability": 0.5,
            "missing_ts_count": 2,
            "missing_device_count": 1,
        }
        params.update(kwargs)
        return groovy_missing_data_decl(**params)

    def test_decl_contains_all_identifiers(self):
        decl = self._decl()
        for token in (
            "missingProbability",
            "missingTsCount",
            "missingDeviceCount",
            "applyMissing",
            "skipMissingRow",
            "deviceMissingHit",
            "tsMissingHit",
        ):
            assert token in decl, f"Groovy 块必须含 {token}"

    def test_decl_bakes_the_three_parameters(self):
        decl = self._decl(probability=0.25, missing_ts_count=3, missing_device_count=2)
        assert "missingProbability = 0.25d" in decl
        assert "missingTsCount = 3" in decl
        assert "missingDeviceCount = 2" in decl

    def test_probability_one_uses_constant_branch(self):
        """probability == 1.0 → 常量分支,不产生随机调用。"""
        decl = self._decl(probability=1.0)
        assert "missingProbability = 1.0d" in decl
        assert "missingProbability == 1.0d" in decl

    def test_decl_uses_thread_local_random(self):
        decl = self._decl()
        assert "java.util.concurrent.ThreadLocalRandom.current()" in decl

    def test_decl_uses_runtime_device_count(self):
        """D7:设备阈值取**运行时** devicePerThread —— 设备数被改小时阈值非正,
        设备维退化为全集(不约束),只剩 ts 维截断。"""
        decl = self._decl()
        assert "devIdx >= devicePerThread - missingDeviceCount" in decl
