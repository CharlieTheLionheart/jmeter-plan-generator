"""Tests for col_tag_bind_mode row-aggregate skip in Orchestrator.

Per OpenSpec change ``col-tag-bind-write`` (2026-08-05) Decision 3 + tasks.md §2:
- When ``col_tag_bind_mode=True``, Orchestrator skips ``write_row_aggregate``
  for that table (no ``{db}/{table}.csv`` aggregate file).
- Column seed files (``{db}/{table}/{idx}_{name}.csv``) are still generated.
- Other tables in mixed scenarios keep their aggregate.
"""

from __future__ import annotations

from pathlib import Path

from config_parser.models import (
    ColTypeConfig,
    ConnConfig,
    PrimaryTagColTypeConfig,
    RelDbConfig,
    RelTableConfig,
    TestConfig,
    TestModelConfig,
    TsDbConfig,
    TsTableConfig,
    WriteConfig,
)
from seed_data_generator import generate_seeds


def _make_ts_table(name: str = "t_cnc") -> TsTableConfig:
    return TsTableConfig(
        name=name,
        data_col_count=1,
        primary_tag_count=1,
        regular_tag_count=0,
        data_cols=[
            ColTypeConfig(
                col_type="int8", type_proportion=1.0, val_range="[1,10]", seed_num=5
            )
        ],
        primary_tags=[
            PrimaryTagColTypeConfig(
                col_type="varchar(32)", type_proportion=1.0, val_range="enum:X,Y", seed_num=5
            )
        ],
    )


def _make_rel_table(name: str = "t_workshop") -> RelTableConfig:
    return RelTableConfig(
        name=name,
        primary_key_count=1,
        data_col_count=1,
        primary_keys=[
            ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="[1,100]", seed_num=5)
        ],
        data_cols=[
            ColTypeConfig(col_type="varchar(16)", type_proportion=1.0, val_range="enum:A,B,C", seed_num=5)
        ],
    )


def _make_model() -> TestModelConfig:
    """Model with two ts tables + one rel table to exercise mixed scenarios."""
    return TestModelConfig(
        rel_dbs=[RelDbConfig(name="iot_metadata", tables=[_make_rel_table()])],
        ts_dbs=[
            TsDbConfig(name="iot_monitor", tables=[_make_ts_table("t_cnc")]),
            TsDbConfig(name="iot_monitor", tables=[_make_ts_table("t_alt")]),
        ],
    )


def _make_conn_config() -> ConnConfig:
    return ConnConfig(db_url="jdbc:kaiwudb://127.0.0.1:26257/defaultdb")


def _make_test_config(
    *, col_tag_bind_tables: set[str] | None = None
) -> TestConfig:
    """Build a TestConfig with one WriteConfig per (db, table).

    ``col_tag_bind_tables`` is a set of ``{db}.{table}`` keys for which
    ``col_tag_bind_mode=True`` is set; defaults to empty set.
    """
    col_tag_bind_tables = col_tag_bind_tables or set()
    write_configs: list[WriteConfig] = []
    model = _make_model()
    for db in model.rel_dbs + model.ts_dbs:
        for table in db.tables:
            key = f"{db.name}.{table.name}"
            bind = key in col_tag_bind_tables
            write_configs.append(
                WriteConfig(
                    tbl_name=key,
                    mode="prepare",
                    col_tag_bind_mode=bind,
                    col_num_per_tag=2 if bind else 0,
                )
            )
    return TestConfig(conn_config=_make_conn_config(), write_config=write_configs)


def test_skip_row_aggregate_skips_aggregate_csv(tmp_path: Path) -> None:
    """col_tag_bind_mode=True → no ``{db}/{table}.csv`` aggregate."""
    model = _make_model()
    cfg = _make_test_config(col_tag_bind_tables={"iot_monitor.t_cnc"})
    generate_seeds(model, tmp_path, seed=42, test_cfg=cfg)

    aggregate = tmp_path / "iot_monitor" / "t_cnc.csv"
    assert not aggregate.exists(), (
        f"col_tag_bind_mode=True table must NOT produce aggregate CSV; "
        f"found {aggregate}"
    )


def test_skip_row_aggregate_keeps_column_seeds(tmp_path: Path) -> None:
    """col_tag_bind_mode=True → column seed files still generated."""
    model = _make_model()
    cfg = _make_test_config(col_tag_bind_tables={"iot_monitor.t_cnc"})
    generate_seeds(model, tmp_path, seed=42, test_cfg=cfg)

    # Column seeds under iot_monitor/t_cnc/ (excluding the aggregate csv)
    table_dir = tmp_path / "iot_monitor" / "t_cnc"
    column_files = sorted(p.name for p in table_dir.iterdir() if p.is_file())
    # Per _make_ts_table: 1 data_col → 1 column seed file
    assert any(name.endswith("col_int8_1.csv") for name in column_files), (
        f"column seed files must still be generated; found: {column_files}"
    )


def test_default_skip_false_keeps_aggregate(tmp_path: Path) -> None:
    """col_tag_bind_mode=False (or unset) → aggregate CSV generated as before."""
    model = _make_model()
    cfg = _make_test_config()  # no bind tables
    generate_seeds(model, tmp_path, seed=42, test_cfg=cfg)

    # All three tables must have aggregate
    assert (tmp_path / "iot_metadata" / "t_workshop.csv").exists()
    assert (tmp_path / "iot_monitor" / "t_cnc.csv").exists()
    assert (tmp_path / "iot_monitor" / "t_alt.csv").exists()


def test_mixed_table_skip_only_for_bind(tmp_path: Path) -> None:
    """Mixed scenario: bind table has no aggregate; full-row tables do."""
    model = _make_model()
    cfg = _make_test_config(col_tag_bind_tables={"iot_monitor.t_cnc"})
    generate_seeds(model, tmp_path, seed=42, test_cfg=cfg)

    # Bind table: no aggregate
    assert not (tmp_path / "iot_monitor" / "t_cnc.csv").exists()
    # Other tables still have aggregate
    assert (tmp_path / "iot_metadata" / "t_workshop.csv").exists()
    assert (tmp_path / "iot_monitor" / "t_alt.csv").exists()
