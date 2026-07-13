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
        # Tasks.md §0.5 / §4 mandates these names.
        assert "calculateTimestamps" in decls
        assert "calculateDeviceNumber" in decls
        assert "deviceIdentifier" in decls
        assert "cloneRows" in decls

    def test_helper_declares_long_types(self):
        # Closes review.md §1 阻塞项 #1: long arithmetic for batch_seq*ms_step.
        decls = all_groovy_decls()
        assert "long base_time_ms" in decls
        assert "long ms_step" in decls
        assert "long batch_seq" in decls

    def test_helper_includes_division_guard(self):
        decls = all_groovy_decls()
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
