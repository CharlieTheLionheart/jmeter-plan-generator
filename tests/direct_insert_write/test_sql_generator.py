"""Tests for ``direct_insert_write.sql_generator``."""

from __future__ import annotations

import pytest

from ddl_generator.generator import DdlGenerationError
from direct_insert_write import DirectInsertGenerationError
from direct_insert_write.sql_generator import (
    generate_batch_insert_sql,
    generate_single_insert_sql,
)


class TestSingleInsert:
    def test_basic_format_with_qualified_table(self):
        sql = generate_single_insert_sql(
            "iot_monitor.t_cnc",
            ["ts", "ptag_int8_1", "col_int8_1"],
        )
        assert sql == (
            "insert into iot_monitor.t_cnc "
            "(ts, ptag_int8_1, col_int8_1) values (?, ?, ?)"
        )

    def test_columns_lowercased(self):
        sql = generate_single_insert_sql(
            "iot_monitor.T_CNC",
            ["TS", "Ptag_INT8_1"],
        )
        assert sql.startswith("insert into iot_monitor.t_cnc")
        assert "(ts, ptag_int8_1)" in sql

    def test_keywords_lowercase(self):
        # confirm `INSERT INTO`/`VALUES` are lowercased
        sql = generate_single_insert_sql("db.t", ["c1"])
        assert "insert into" in sql
        assert "values" in sql
        assert "INSERT INTO" not in sql
        assert "VALUES" not in sql

    def test_empty_columns_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_single_insert_sql("iot_monitor.t_cnc", [])

    def test_unqualified_table_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_single_insert_sql("t_cnc", ["ts"])

    def test_missing_db_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_single_insert_sql(".t_cnc", ["ts"])

    def test_missing_table_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_single_insert_sql("iot_monitor.", ["ts"])


class TestBatchInsert:
    def test_row_count_equals_batch_lines(self):
        sql = generate_batch_insert_sql(
            "iot_monitor.t_cnc",
            ["col1", "col2", "col3"],
            batch_lines=10,
        )
        # 10 tuples of "(?, ?, ?)" joined
        assert sql.count("(?, ?, ?)") == 10
        assert sql.startswith(
            "insert into iot_monitor.t_cnc (col1, col2, col3) values "
        )

    def test_tail_row_count(self):
        sql = generate_batch_insert_sql(
            "iot_monitor.t_cnc",
            ["c1", "c2"],
            batch_lines=10,
            row_count=3,
        )
        assert sql.count("(?, ?)") == 3
        assert sql.count("(?, ?)") < 10

    def test_batch_lines_zero_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_batch_insert_sql("db.t", ["c1"], batch_lines=0)

    def test_batch_lines_negative_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_batch_insert_sql("db.t", ["c1"], batch_lines=-5)

    def test_row_count_exceeds_batch_lines_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_batch_insert_sql(
                "db.t",
                ["c1"],
                batch_lines=5,
                row_count=10,
            )

    def test_row_count_zero_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_batch_insert_sql(
                "db.t",
                ["c1"],
                batch_lines=5,
                row_count=0,
            )

    def test_empty_columns_raises(self):
        with pytest.raises(DirectInsertGenerationError):
            generate_batch_insert_sql("iot_monitor.t_cnc", [], batch_lines=10)
