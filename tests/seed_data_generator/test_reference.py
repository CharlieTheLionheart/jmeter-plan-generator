"""Tests for foreign-key reference sampling."""

from __future__ import annotations

from pathlib import Path

import pytest

from config_parser.models import ColTypeConfig, RelDbConfig, TsDbConfig, RelTableConfig, TsTableConfig, TestModelConfig
from seed_data_generator.adapter import SeedGenError
from seed_data_generator.io import write_column_seed
from seed_data_generator.reference import (
    build_column_registry,
    discover_references,
    pregenerate_reference_columns,
    sample_reference_values,
)


def _model_with_ref() -> TestModelConfig:
    rel_table = RelTableConfig(
        name="t_workshop",
        primary_key_count=1,
        data_col_count=0,
        primary_keys=[
            ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="[1,100]", seed_num=3)
        ],
        data_cols=[],
    )
    ts_table = TsTableConfig(
        name="t_cnc",
        data_col_count=1,
        primary_tag_count=0,
        regular_tag_count=1,
        data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="ref:iot_metadata.t_workshop.pk_int8_1", seed_num=10)],
        regular_tags=[ColTypeConfig(col_type="varchar(16)", type_proportion=1.0, val_range="enum:A,B", seed_num=10)],
    )
    return TestModelConfig(
        rel_dbs=[RelDbConfig(name="iot_metadata", tables=[rel_table])],
        ts_dbs=[TsDbConfig(name="iot_monitor", tables=[ts_table])],
    )


def test_discover_references():
    model = _model_with_ref()
    refs = discover_references(model)
    assert "iot_metadata.t_workshop.pk_int8_1" in refs
    assert len(refs) == 1


def test_build_registry():
    model = _model_with_ref()
    registry = build_column_registry(model)
    assert "iot_metadata.t_workshop.pk_int8_1" in registry
    assert "iot_monitor.t_cnc.col_int8_1" in registry


def test_pregenerate_reference_columns(tmp_path: Path):
    model = _model_with_ref()
    registry = build_column_registry(model)
    refs = discover_references(model)
    ref_paths = pregenerate_reference_columns(model, tmp_path, registry, refs)

    target = "iot_metadata.t_workshop.pk_int8_1"
    assert target in ref_paths
    assert ref_paths[target].exists()
    assert ref_paths[target].name == "1_pk_int8_1.csv"


def test_sample_reference_with_replacement(tmp_path: Path):
    ref_path = tmp_path / "1_pk_int8_1.int8.csv"
    write_column_seed(ref_path, [1, 2, 3])

    values = sample_reference_values(ref_path, 10)
    assert len(values) == 10
    assert all(v in {"1", "2", "3"} for v in values)


def test_sample_reference_cycles_when_smaller(tmp_path: Path):
    ref_path = tmp_path / "1_pk_int8_1.int8.csv"
    write_column_seed(ref_path, ["a", "b"])

    values = sample_reference_values(ref_path, 5)
    assert len(values) == 5
    assert set(values) <= {"a", "b"}


def test_sample_reference_missing_file(tmp_path: Path):
    with pytest.raises(SeedGenError, match="not found"):
        sample_reference_values(tmp_path / "missing.csv", 5)


def test_cross_database_reference(tmp_path: Path):
    model = _model_with_ref()
    registry = build_column_registry(model)
    refs = discover_references(model)
    ref_paths = pregenerate_reference_columns(model, tmp_path, registry, refs)

    source_path = ref_paths["iot_metadata.t_workshop.pk_int8_1"]
    values = sample_reference_values(source_path, 20)
    assert len(values) == 20
    assert all(int(v) in range(1, 101) for v in values)
