"""Tests for seed CSV input/output."""

from __future__ import annotations

import csv
from pathlib import Path

from seed_data_generator.io import (
    build_row_aggregate,
    cleanup_table_seeds,
    discover_column_files,
    read_column_seed,
    write_column_seed,
    write_row_aggregate,
)


def test_write_and_read_column_seed(tmp_path: Path):
    path = tmp_path / "1_col_int8_1.int8"
    write_column_seed(path, [1, 2, None, 4])
    assert path.exists()
    values = read_column_seed(path)
    assert values == ["1", "2", "null", "4"]


def test_special_character_escaping(tmp_path: Path):
    path = tmp_path / "1_col_varchar_1.csv"
    write_column_seed(path, ["a,b", 'a"b', "a\nb"])
    values = read_column_seed(path)
    assert values == ["a,b", 'a"b', "a\nb"]

    # Verify Python csv.reader can parse it (no header row in seed files).
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    assert [row[0] for row in rows] == ["a,b", 'a"b', "a\nb"]


def test_discover_column_files_sorts_numerically(tmp_path: Path):
    (tmp_path / "1_col_int8_1.csv").write_text("value\n1\n")
    (tmp_path / "10_col_varchar_1.csv").write_text("value\na\n")
    (tmp_path / "2_col_float4_1.csv").write_text("value\n1.0\n")

    files = discover_column_files(tmp_path)
    indices = [idx for idx, _, _ in files]
    assert indices == [1, 2, 10]


def test_build_row_aggregate_cycles_short_columns(tmp_path: Path):
    write_column_seed(tmp_path / "1_pk_int8_1.csv", [1, 2])
    write_column_seed(tmp_path / "2_col_varchar_1.csv", ["a", "b", "c", "d"])

    header, rows = build_row_aggregate(tmp_path)
    assert header == ["pk_int8_1", "col_varchar_1"]
    assert len(rows) == 4
    assert rows[0] == ["1", "a"]
    assert rows[1] == ["2", "b"]
    assert rows[2] == ["1", "c"]
    assert rows[3] == ["2", "d"]


def test_write_row_aggregate_round_trip(tmp_path: Path):
    path = tmp_path / "db.table.csv"
    rows = [["1", "a,b"], ["2", 'c"d']]
    write_row_aggregate(path, ["id", "name"], rows)

    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        parsed = list(reader)

    assert parsed[0] == ["id", "name"]
    assert parsed[1:] == rows


def test_cleanup_table_seeds(tmp_path: Path):
    db_dir = tmp_path / "db"
    table_dir = db_dir / "table"
    table_dir.mkdir(parents=True)
    (table_dir / "1_col_int8_1.csv").write_text("value\n1\n")
    aggregate = db_dir / "table.csv"
    aggregate.write_text("col\n1\n")

    cleanup_table_seeds(tmp_path, "db", "table")
    assert not table_dir.exists()
    assert not aggregate.exists()
