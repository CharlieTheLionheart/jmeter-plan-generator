"""Tests for ``direct_insert_write.preprocessor_generator``."""

from __future__ import annotations

import pytest

from direct_insert_write import DirectInsertGenerationError
from direct_insert_write.preprocessor_generator import (
    generate_preprocessor_script,
    generate_relational_init_preprocessor_script,
)


def _table_config(**overrides):
    base = {
        "db": "iot_monitor",
        "table": "t_cnc",
        "columns": ["ts", "ptag_int8_1", "col_int8_1"],
        "first_ptag_column": "ptag_int8_1",
    }
    base.update(overrides)
    return base


class TestGeneratePreprocessorScript:
    def test_returns_groovy_string(self):
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
        )
        assert isinstance(script, str)
        # tasks.md §4 mandates these Groovy-side names.
        assert "calculateTimestamps" in script
        assert "calculateDeviceNumber" in script
        assert "cloneRows" in script
        assert "deviceIdentifier" in script

    def test_long_cast_in_timestamp_calc(self):
        # Closes review.md §1 阻塞项 #1: long arithmetic.
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
        )
        assert "as long" in script

    def test_reads_shared_memory_with_qualified_key(self):
        # Aligns with ``shared-memory-initializer`` convention:
        # ``__SHARED_MEM_{db}.{table}`` (rows) +
        # ``__SHARED_MEM_{db}.{table}_columns`` (column order).
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
        )
        assert "'__SHARED_MEM_iot_monitor.t_cnc'" in script
        assert "'__SHARED_MEM_iot_monitor.t_cnc_columns'" in script
        assert "props.get(rowsKey)" in script
        assert "props.get(colsKey)" in script

    def test_column_order_read_from_shared_memory(self):
        # Column-name list comes from the columns key (set by
        # ``shared-memory-initializer``), not from a Python-side
        # hard-coded Groovy literal.
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
        )
        assert "props.get(colsKey) as List" in script
        # First column is still hard-coded as the ts slot (design §3.5.1).
        assert "c == 0" in script

    def test_uses_threadNum_for_device_calculation(self):
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
        )
        assert "threadNum" in script
        assert "ctx.getThreadNum" in script

    def test_replaces_device_code_with_device_identifier(self):
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
        )
        # first ptag index = 1 ⇒ cell at c == ptagIndex overwritten
        assert "deviceIdentifier(deviceNumber)" in script
        assert "device_" in script

    def test_emits_param_vars_for_each_cell(self):
        # Closes C3/C4 — preprocessor must bind per-cell param_N vars for
        # the JDBCSampler's ${param_N} queryArguments to resolve.
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
            batch_lines=10,
        )
        # 3 cols × 10 rows = 30 cells — paramIdx walks 0..29
        # Implementation uses `vars.put("param_" + paramIdx, cell)` and
        # an incrementing paramIdx; verify the loop and cell-name parts
        # are present.
        assert 'vars.put("param_" + paramIdx, cell)' in script
        assert "paramIdx++" in script
        # The cell project must cover ts (c==0), ptag (ptagIndex), and
        # the regular-data fall-through.
        assert "c == 0" in script
        assert "c == ptagIndex" in script
        # No JSON-blob path
        assert "BATCH_ROW_VALUES_JSON" not in script
        assert "BATCH_TIMESTAMPS" not in script
        assert "BATCH_DEVICE_IDS" not in script

    def test_ms_step_and_batch_lines_passed_independently(self):
        # Closes C2 — ms_step and batch_lines must NOT be collapsed.
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
            ms_step=2000,
            batch_lines=5,
        )
        # ms_step is rendered as a long literal (2000L via "as long" cast)
        assert "2000 as long" in script
        # batch_lines is rendered as its own literal
        assert "def batchLines = 5" in script
        # call site passes both args to calculateTimestamps, not a single
        # value repeated
        assert "msStepL, batchLines as long" in script or (
            "msStepL" in script and "batchLines as long" in script
        )

    def test_timestamp_column_uses_sql_timestamp(self):
        # Closes C6 — ts column emitted as java.sql.Timestamp string.
        script = generate_preprocessor_script(
            table_config=_table_config(),
            device_per_thread=4,
        )
        assert "java.sql.Timestamp" in script

    def test_zero_device_per_thread_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_preprocessor_script(
                table_config=_table_config(),
                device_per_thread=0,
            )

    def test_negative_device_per_thread_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_preprocessor_script(
                table_config=_table_config(),
                device_per_thread=-3,
            )

    def test_zero_batch_lines_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_preprocessor_script(
                table_config=_table_config(),
                device_per_thread=4,
                batch_lines=0,
            )

    def test_zero_ms_step_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_preprocessor_script(
                table_config=_table_config(),
                device_per_thread=4,
                ms_step=0,
            )

    def test_missing_keys_raise(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_preprocessor_script(
                table_config={"db": "iot_monitor"},
                device_per_thread=4,
            )

    def test_first_ptag_not_first_column_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_preprocessor_script(
                table_config=_table_config(
                    columns=["ptag_int8_1", "ts", "col_int8_1"],
                    first_ptag_column="ptag_int8_1",
                ),
                device_per_thread=4,
            )

    def test_first_ptag_must_be_in_columns(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_preprocessor_script(
                table_config=_table_config(first_ptag_column="nope"),
                device_per_thread=4,
            )

    def test_special_chars_in_table_name_escape_into_key(self):
        script = generate_preprocessor_script(
            table_config=_table_config(table="t_cnc-special"),
            device_per_thread=4,
        )
        assert "'__SHARED_MEM_iot_monitor.t_cnc_special'" in script
        assert "'__SHARED_MEM_iot_monitor.t_cnc_special_columns'" in script


class TestRelationalInitPreprocessorScript:
    def test_emits_param_vars_per_cell(self):
        script = generate_relational_init_preprocessor_script(
            table_name="iot_metadata.t_workshop",
            rel_col_seed_files=["1_pk_int8_1.csv", "2_col_varchar_1.csv"],
            batch_lines=5,
        )
        # 2 cols × 5 rows = 10 cells — paramIdx walks 0..9
        assert 'vars.put("param_" + paramIdx, value)' in script
        assert "paramIdx++" in script

    def test_uses_rel_batch_idx(self):
        script = generate_relational_init_preprocessor_script(
            table_name="iot_metadata.t_workshop",
            rel_col_seed_files=["1_pk.csv"],
            batch_lines=5,
        )
        assert "__rel_batch_idx" in script
        assert "batchIdx" in script

    def test_no_shared_memory_dependency(self):
        # Closes C5 — relational init reads column seed files directly,
        # not from the shared-memory row aggregate.
        script = generate_relational_init_preprocessor_script(
            table_name="iot_metadata.t_workshop",
            rel_col_seed_files=["1_pk.csv", "2_col.csv"],
            batch_lines=5,
        )
        assert "props.get" not in script
        assert "__SHARED_MEM" not in script

    def test_zero_batch_lines_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_init_preprocessor_script(
                table_name="iot_metadata.t_workshop",
                rel_col_seed_files=["1_pk.csv"],
                batch_lines=0,
            )

    def test_empty_col_seed_files_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_init_preprocessor_script(
                table_name="iot_metadata.t_workshop",
                rel_col_seed_files=[],
                batch_lines=5,
            )
