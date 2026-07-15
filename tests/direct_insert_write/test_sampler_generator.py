"""Tests for ``direct_insert_write.sampler_generator``."""

from __future__ import annotations

import pytest

from direct_insert_write import DirectInsertGenerationError
from direct_insert_write.sampler_generator import (
    create_jdbc_sampler,
    create_jsr223_preprocessor_for_write,
    generate_jdbc_sampler_config,
    generate_relational_table_init_sampler,
)
from direct_insert_write.sql_generator import (
    generate_batch_insert_sql,
    generate_single_insert_sql,
)


class TestJdbcSamplerConfig:
    def test_single_insert_uses_prepared_update_statement_with_param_args(self):
        # JMeter's "Update Statement" mode does not bind ``?`` placeholders
        # to ``queryArguments`` — it executes the SQL literally. The
        # direct-insert samplers therefore use "Prepared Update Statement"
        # so the JSR223PreProcessor's per-cell ``vars.put("param_N", ...)``
        # calls bind through ``queryArguments=${param_N}``.
        cfg = generate_jdbc_sampler_config(
            "single_insert",
            sql=generate_single_insert_sql(
                "iot_monitor.t_cnc",
                ["ts", "ptag_int8_1", "col_int8_1"],
            ),
        )
        assert cfg["query_type"] == "Prepared Update Statement"
        assert cfg["query_arguments"] == "${param_0},${param_1},${param_2}"
        assert cfg["query_arguments_types"] == "VARCHAR,VARCHAR,VARCHAR"
        # batch_insert-only field absent
        assert cfg.get("batch_size") is None
        # Legacy field removed.
        assert "use_prepared" not in cfg

    def test_batch_insert_emits_param_args_and_batch_size(self):
        sql = generate_batch_insert_sql(
            "iot_monitor.t_cnc",
            ["ts", "c1"],
            batch_lines=10,
        )
        cfg = generate_jdbc_sampler_config("batch_insert", sql=sql, batch_lines=10)
        assert cfg["query_type"] == "Prepared Update Statement"
        # 2 cols × 10 rows = 20 params
        assert cfg["query_arguments"].count("${param_") == 20
        assert cfg["query_arguments"].endswith("${param_19}")
        assert cfg["batch_size"] == 10
        assert "use_prepared" not in cfg

    def test_explicit_query_arguments_types_override_default(self):
        cfg = generate_jdbc_sampler_config(
            "single_insert",
            sql=generate_single_insert_sql(
                "iot_monitor.t_cnc",
                ["ts", "ptag_int8_1"],
            ),
            query_arguments_types="TIMESTAMP,VARCHAR",
        )
        assert cfg["query_arguments_types"] == "TIMESTAMP,VARCHAR"

    def test_invalid_mode_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_jdbc_sampler_config("garbage", sql="")

    def test_empty_sql_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_jdbc_sampler_config("single_insert", sql="")

    def test_batch_insert_requires_batch_lines(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_jdbc_sampler_config("batch_insert", sql="insert into x values (?)")

    def test_batch_insert_zero_batch_lines_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_jdbc_sampler_config(
                "batch_insert",
                sql="insert into x values (?)",
                batch_lines=0,
            )


class TestCreateJdbcSampler:
    def test_returns_xml_element_pair(self):
        sampler, tree = create_jdbc_sampler(
            "single_insert",
            sql=generate_single_insert_sql(
                "iot_monitor.t_cnc",
                ["ts", "ptag_int8_1"],
            ),
            name="Sampler_X",
        )
        assert sampler.tag.endswith("JDBCSampler")
        assert sampler.attrib["name"] == "Sampler_X"


class TestJsr223Preprocessor:
    def test_returns_xml_element_pair(self):
        pre, tree = create_jsr223_preprocessor_for_write(
            db="iot_monitor",
            table="t_cnc",
            columns=["ts", "ptag_int8_1", "col_int8_1"],
            first_ptag_column="ptag_int8_1",
            device_per_thread=4,
            batch_lines=5,
        )
        assert pre.tag.endswith("JSR223PreProcessor")
        assert "DirectInsertPrep_iot_monitor_t_cnc" in pre.attrib["name"]


class TestRelationalInit:
    def test_loop_count_is_exact_quotient(self):
        cfg = generate_relational_table_init_sampler(
            table_name="iot_metadata.t_workshop",
            columns=["pk_int8_1", "col_varchar_1"],
            total_rows=1000,
            batch_lines=500,
            rel_col_seed_files=["1_pk_int8_1.csv", "2_col_varchar_1.csv"],
        )
        # 1000 / 500 = 2 full iterations, no residual concept.
        assert cfg["loop_count"] == 2
        assert cfg["batch_size"] == 500
        # residual/row_count_tail must NOT exist anymore.
        assert "residual" not in cfg
        assert "row_count_tail" not in cfg
        assert "full_batches" not in cfg

    def test_uses_prepared_update_statement(self):
        # Closes C5 — relational init path uses Prepared Update Statement
        # with ${param_N} binding.
        cfg = generate_relational_table_init_sampler(
            table_name="iot_metadata.t_workshop",
            columns=["pk_int8_1", "col_varchar_1"],
            total_rows=10,
            batch_lines=5,
            rel_col_seed_files=["1_pk_int8_1.csv", "2_col_varchar_1.csv"],
        )
        assert cfg["query_type"] == "Prepared Update Statement"
        # 2 cols × 5 rows = 10 params
        assert cfg["query_arguments"].count("${param_") == 10
        assert cfg["query_arguments"].endswith("${param_9}")

    def test_query_arguments_types_repeated_per_row(self):
        cfg = generate_relational_table_init_sampler(
            table_name="iot_metadata.t_workshop",
            columns=["pk_int8_1", "col_varchar_1"],
            total_rows=10,
            batch_lines=5,
            rel_col_seed_files=["1_pk_int8_1.csv", "2_col_varchar_1.csv"],
            column_types=["INTEGER", "VARCHAR"],
        )
        # 2 types × 5 rows = 10 entries
        types = cfg["query_arguments_types"].split(",")
        assert types == ["INTEGER", "VARCHAR"] * 5

    def test_rel_col_seed_files_round_trip(self):
        files = ["1_pk_int8_1.csv", "2_col_varchar_1.csv"]
        cfg = generate_relational_table_init_sampler(
            table_name="iot_metadata.t_workshop",
            columns=["pk_int8_1", "col_varchar_1"],
            total_rows=10,
            batch_lines=5,
            rel_col_seed_files=files,
        )
        assert cfg["rel_col_seed_files"] == files

    def test_preprocessor_script_sets_param_vars(self):
        # Closes C5 — relational init PreProcessor must set param_N
        # vars (NOT reuse the write-path JSON-blob path).
        cfg = generate_relational_table_init_sampler(
            table_name="iot_metadata.t_workshop",
            columns=["pk_int8_1", "col_varchar_1"],
            total_rows=10,
            batch_lines=5,
            rel_col_seed_files=["1_pk_int8_1.csv", "2_col_varchar_1.csv"],
        )
        script = cfg["preprocessor_script"]
        assert 'vars.put("param_" + paramIdx, value)' in script
        assert "paramIdx++" in script
        # No write-path markers
        assert "BATCH_ROW_VALUES_JSON" not in script
        assert "deviceIdentifier" not in script
        assert "calculateTimestamps" not in script

    def test_non_multiple_total_rows_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_table_init_sampler(
                table_name="iot_metadata.t_workshop",
                columns=["pk_int8_1", "col_varchar_1"],
                total_rows=1230,   # 1230 % 500 = 230
                batch_lines=500,
                rel_col_seed_files=["1_pk_int8_1.csv", "2_col_varchar_1.csv"],
            )

    def test_total_rows_zero_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_table_init_sampler(
                table_name="db.t",
                columns=["c1"],
                total_rows=0,
                rel_col_seed_files=["1_c1.csv"],
            )

    def test_total_rows_negative_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_table_init_sampler(
                table_name="db.t",
                columns=["c1"],
                total_rows=-10,
                rel_col_seed_files=["1_c1.csv"],
            )

    def test_batch_lines_zero_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_table_init_sampler(
                table_name="db.t",
                columns=["c1"],
                total_rows=10,
                batch_lines=0,
                rel_col_seed_files=["1_c1.csv"],
            )

    def test_sql_uses_qualified_name(self):
        cfg = generate_relational_table_init_sampler(
            table_name="iot_metadata.t_workshop",
            columns=["pk_int8_1", "col_varchar_1"],
            total_rows=10,
            batch_lines=5,
            rel_col_seed_files=["1_pk_int8_1.csv", "2_col_varchar_1.csv"],
        )
        assert cfg["sql"].startswith(
            "insert into iot_metadata.t_workshop (pk_int8_1, col_varchar_1) values "
        )

    def test_rel_col_seed_files_required(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_table_init_sampler(
                table_name="iot_metadata.t_workshop",
                columns=["pk_int8_1", "col_varchar_1"],
                total_rows=10,
                batch_lines=5,
            )

    def test_rel_col_seed_files_length_must_match_columns(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_table_init_sampler(
                table_name="iot_metadata.t_workshop",
                columns=["pk_int8_1", "col_varchar_1"],
                total_rows=10,
                batch_lines=5,
                rel_col_seed_files=["only_one.csv"],
            )

    def test_unqualified_table_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_relational_table_init_sampler(
                table_name="t_workshop",
                columns=["c1"],
                total_rows=10,
                batch_lines=5,
                rel_col_seed_files=["1_c1.csv"],
            )
