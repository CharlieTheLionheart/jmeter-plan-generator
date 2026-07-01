"""Benchmark and concurrency tests for seed generation."""

from __future__ import annotations

import concurrent.futures
import time
from pathlib import Path

import pytest

from config_parser.models import ColTypeConfig, DatabaseConfig, TableConfig, TestModelConfig
from seed_data_generator import generate_seeds


def _simple_table(name: str, seed_num: int = 1_000_000) -> TableConfig:
    return TableConfig(
        name=name,
        primary_key_count=1,
        data_col_count=1,
        primary_tag_count=0,
        regular_tag_count=0,
        primary_keys=[
            ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="[1,1000000]", seed_num=seed_num)
        ],
        data_cols=[
            ColTypeConfig(col_type="varchar(16)", type_proportion=1.0, val_range="^[a-z]{5,10}$", seed_num=seed_num)
        ],
    )


@pytest.mark.slow
def test_million_row_generation(tmp_path: Path):
    model = TestModelConfig(
        rel_dbs=[DatabaseConfig(name="perf_db", tables=[_simple_table("t_big")])]
    )
    start = time.perf_counter()
    results = generate_seeds(model, tmp_path, seed=1)
    elapsed = time.perf_counter() - start

    aggregate = tmp_path / "perf_db.t_big.csv"
    assert aggregate.exists()
    # header + 1_000_000 rows
    line_count = sum(1 for _ in aggregate.open("r", encoding="utf-8"))
    assert line_count == 1_000_001
    assert elapsed < 60.0


@pytest.mark.slow
def test_concurrent_table_generation(tmp_path: Path):
    model = TestModelConfig(
        rel_dbs=[
            DatabaseConfig(
                name="concurrent_db",
                tables=[
                    _simple_table("t_a", seed_num=10_000),
                    _simple_table("t_b", seed_num=10_000),
                ],
            )
        ]
    )

    def run(table_name: str) -> bool:
        # Generate a single table by building a minimal model containing only it.
        single_model = TestModelConfig(
            rel_dbs=[
                DatabaseConfig(
                    name="concurrent_db",
                    tables=[_simple_table(table_name)],
                )
            ]
        )
        results = generate_seeds(single_model, tmp_path / table_name, seed=1)
        return bool(results)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, name) for name in ("t_a", "t_b")]
        outcomes = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(outcomes)
    assert (tmp_path / "t_a" / "concurrent_db.t_a.csv").exists()
    assert (tmp_path / "t_b" / "concurrent_db.t_b.csv").exists()
