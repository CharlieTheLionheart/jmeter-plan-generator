"""Tests for ``direct_insert_write.sql_generator``."""

from __future__ import annotations

import pytest

from direct_insert_write import DirectInsertGenerationError
from direct_insert_write.sql_generator import generate_batch_insert_sql


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
