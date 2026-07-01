"""End-to-end tests for seed generation orchestrator."""

from __future__ import annotations

import csv
from pathlib import Path

from config_parser.models import (
    ColTypeConfig,
    DatabaseConfig,
    PrimaryTagColTypeConfig,
    TableConfig,
    TestModelConfig,
)
from seed_data_generator import generate_seeds


def _make_model() -> TestModelConfig:
    rel_table = TableConfig(
        name="t_workshop",
        primary_key_count=1,
        data_col_count=1,
        primary_tag_count=0,
        regular_tag_count=0,
        primary_keys=[
            ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="[1,100]", seed_num=5)
        ],
        data_cols=[
            ColTypeConfig(col_type="varchar(16)", type_proportion=1.0, val_range="enum:A,B,C", seed_num=5)
        ],
    )
    ts_table = TableConfig(
        name="t_cnc",
        primary_key_count=0,
        data_col_count=1,
        primary_tag_count=1,
        regular_tag_count=1,
        primary_keys=[],
        data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="[1,10]", seed_num=20)],
        primary_tags=[PrimaryTagColTypeConfig(col_type="varchar(32)", type_proportion=1.0, val_range="enum:X,Y", seed_num=20)],
        regular_tags=[ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="ref:iot_metadata.t_workshop.pk_int8_1", seed_num=20)],
    )
    return TestModelConfig(
        rel_dbs=[DatabaseConfig(name="iot_metadata", tables=[rel_table])],
        ts_dbs=[DatabaseConfig(name="iot_monitor", tables=[ts_table])],
    )


def test_generate_seeds_creates_files(tmp_path: Path):
    model = _make_model()
    results = generate_seeds(model, tmp_path, seed=42)

    rel_files = results["iot_metadata.t_workshop"]
    assert any(path.name == "1_pk_int8_1.int8.ref" for path in rel_files)
    assert any(path.name == "2_col_varchar_1.varchar" for path in rel_files)
    assert any(path.name == "iot_metadata.t_workshop.csv" for path in rel_files)

    ts_files = results["iot_monitor.t_cnc"]
    assert any(path.name == "1_col_int8_1.int8" for path in ts_files)
    assert any(path.name == "iot_monitor.t_cnc.csv" for path in ts_files)


def test_row_aggregate_header_and_rows(tmp_path: Path):
    model = _make_model()
    generate_seeds(model, tmp_path, seed=42)

    aggregate = tmp_path / "iot_metadata.t_workshop.csv"
    assert aggregate.exists()
    with aggregate.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    assert rows[0] == ["pk_int8_1", "col_varchar_1"]
    assert len(rows) == 6  # header + 5 data rows


def test_reference_values_come_from_ref_file(tmp_path: Path):
    model = _make_model()
    generate_seeds(model, tmp_path, seed=42)

    ref_path = tmp_path / "iot_metadata.t_workshop" / "1_pk_int8_1.int8.ref"
    tag_path = tmp_path / "iot_monitor.t_cnc" / "3_rtag_int8_1.int8"

    ref_values = set(ref_path.read_text(encoding="utf-8").splitlines()[1:])
    tag_values = set(tag_path.read_text(encoding="utf-8").splitlines()[1:])
    assert tag_values <= ref_values
