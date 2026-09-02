"""Tests for ``direct_insert_write.preprocessor_generator``."""

from __future__ import annotations

import pytest

from direct_insert_write import DirectInsertGenerationError
from direct_insert_write.preprocessor_generator import (
    generate_relational_init_preprocessor_script,
)


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
