"""Integration tests for col_tag_bind_mode seed_csv_paths wiring.

Per OpenSpec change ``col-tag-bind-write`` (2026-08-05) tasks.md §2:
- Bind-mode tables have NO row aggregate (``Orchestrator`` skipped
  ``write_row_aggregate``).
- ``main._run_pipeline`` must exclude bind-mode tables from
  ``seed_csv_paths`` so the SetupTG row-seed sampler does not receive a
  column-seed CSV path (which lacks a header row and is not a valid
  row aggregate).

Regression: commit 2 review (agent ``a420e9ce72f013d2f``) flagged that
unfiltered ``paths[-1]`` for bind tables produced invalid ``csvPath=``
entries in SetupTG JMX. These tests pin the bind-aware filter in place.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kwjdbc_svt import main as cli_module

cli_main = cli_module.main


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    import yaml

    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _two_table_model() -> dict:
    """Two ts tables: ``t_cnc`` (will be bind) + ``t_alt`` (full-row)."""
    base_table = {
        "data_col_count": 1,
        "primary_tag_count": 1,
        "regular_tag_count": 0,
        "data_cols": [
            {"col_type": "int8", "type_proportion": 1.0, "val_range": "[0,100]"}
        ],
        "primary_tags": [{"col_type": "int8", "type_proportion": 1.0}],
        "ts_col": {"name": "ts", "type": "timestamp", "ms_step": 1000},
    }
    return {
        "ts_dbs": [
            {
                "name": "iot_monitor",
                "tables": [
                    {**base_table, "name": "t_cnc"},
                    {**base_table, "name": "t_alt"},
                ],
            }
        ]
    }


def _mixed_cfg(bind_table: str = "iot_monitor.t_cnc") -> dict:
    """One bind table + one full-row table; both have primary tags >= 1."""
    return {
        "conn_config": {
            "db_url": "jdbc:kaiwudb://localhost:26257/iot",
            "conn_pool_size": 10,
            "device_start": 1,
            "test_duration": 60,
        },
        "write_config": [
            {
                "tbl_name": bind_table,
                "throughput": 1000.0,
                "mode": "prepare",
                "batch_lines": 1,
                "device_per_thread": 1,
                "num_threads": 1,
                "col_tag_bind_mode": True,
                "col_num_per_tag": 1,
            },
            {
                "tbl_name": "iot_monitor.t_alt",
                "throughput": 1000.0,
                "mode": "prepare",
                "batch_lines": 1,
                "device_per_thread": 1,
                "num_threads": 1,
            },
        ],
    }


def test_run_pipeline_excludes_bind_table_from_csv_paths(tmp_path: Path) -> None:
    """Bind-mode tables must NOT appear in ``seed_csv_paths`` for SetupTG.

    Without the fix, ``paths[-1]`` for a bind table is a column-seed CSV
    (e.g. ``.../t_cnc/1_col_int8_1.csv``) which the row-seed loader cannot
    parse as a row aggregate.
    """
    model = _write_yaml(tmp_path, "model.yaml", _two_table_model())
    cfg = _write_yaml(tmp_path, "cfg.yaml", _mixed_cfg())
    out = tmp_path / "out"

    with patch("kwjdbc_svt.main.JMXSkeletonGenerator") as mock_skel:
        rc = cli_main([str(model), str(cfg), "-o", str(out)])

    assert rc == 0
    assert mock_skel.called, "JMXSkeletonGenerator must be invoked"
    seed_csv_paths = mock_skel.call_args.kwargs["seed_csv_paths"]

    # Bind table excluded
    assert "iot_monitor" in seed_csv_paths, seed_csv_paths
    assert "t_cnc" not in seed_csv_paths["iot_monitor"], (
        f"bind-mode table t_cnc must be excluded from seed_csv_paths; "
        f"got {seed_csv_paths['iot_monitor']}"
    )
    # Full-row table kept
    assert "t_alt" in seed_csv_paths["iot_monitor"], (
        f"full-row table t_alt must remain in seed_csv_paths; "
        f"got {seed_csv_paths['iot_monitor']}"
    )


def test_run_pipeline_keeps_all_full_row_tables(tmp_path: Path) -> None:
    """Without any bind-mode tables, all aggregates flow through unchanged."""
    cfg_dict = _mixed_cfg()
    # Disable bind on both
    cfg_dict["write_config"][0]["col_tag_bind_mode"] = False
    cfg_dict["write_config"][0]["col_num_per_tag"] = 0
    cfg_dict["write_config"][1]["col_tag_bind_mode"] = False
    cfg_dict["write_config"][1]["col_num_per_tag"] = 0

    model = _write_yaml(tmp_path, "model.yaml", _two_table_model())
    cfg = _write_yaml(tmp_path, "cfg.yaml", cfg_dict)
    out = tmp_path / "out"

    with patch("kwjdbc_svt.main.JMXSkeletonGenerator") as mock_skel:
        rc = cli_main([str(model), str(cfg), "-o", str(out)])

    assert rc == 0
    seed_csv_paths = mock_skel.call_args.kwargs["seed_csv_paths"]
    assert "t_cnc" in seed_csv_paths["iot_monitor"]
    assert "t_alt" in seed_csv_paths["iot_monitor"]


# ---------------------------------------------------------------------------
# commit 6 (2026-08-10): main entry validation + skeleton.py wiring
# ---------------------------------------------------------------------------


def test_main_validates_col_num_per_tag_exceeds_data_col_count(tmp_path: Path) -> None:
    """col_tag_bind_mode=true with col_num_per_tag > data_col_count → ValueError.

    Per OpenSpec tasks.md §7.1: the upper-bound validation cannot live on
    WriteConfig alone because it requires cross-reference to TestModelConfig.
    Main entry raises ValueError naming the offending ``{db}.{table}``.
    """
    model_dict = _two_table_model()
    cfg_dict = _mixed_cfg()
    # Force col_num_per_tag > data_col_count (data_col_count=1 here, set 5)
    cfg_dict["write_config"][0]["col_num_per_tag"] = 5

    model = _write_yaml(tmp_path, "model.yaml", model_dict)
    cfg = _write_yaml(tmp_path, "cfg.yaml", cfg_dict)
    out = tmp_path / "out"

    rc = cli_main([str(model), str(cfg), "-o", str(out)])
    assert rc == EXIT_VALIDATION, (
        f"col_num_per_tag > data_col_count must exit 1, got {rc}"
    )


def test_main_validates_zero_primary_tag(tmp_path: Path) -> None:
    """col_tag_bind_mode=true on a table with primary_tag_count=0 → ValueError.

    Per OpenSpec tasks.md §7.1: bind mode requires at least one primary tag
    (the hash-bucket key). Zero ptag is meaningless — every write would land
    on the same group.
    """
    model_dict = _two_table_model()
    # Strip primary_tag_count to 0 on t_cnc
    for db in model_dict["ts_dbs"]:
        for tbl in db["tables"]:
            if tbl["name"] == "t_cnc":
                tbl["primary_tag_count"] = 0
                tbl["primary_tags"] = []

    cfg_dict = _mixed_cfg()  # bind on iot_monitor.t_cnc

    model = _write_yaml(tmp_path, "model.yaml", model_dict)
    cfg = _write_yaml(tmp_path, "cfg.yaml", cfg_dict)
    out = tmp_path / "out"

    rc = cli_main([str(model), str(cfg), "-o", str(out)])
    assert rc == EXIT_VALIDATION, (
        f"primary_tag_count=0 + bind mode must exit 1, got {rc}"
    )


def test_end_to_end_col_bind_emits_subset_jmx(tmp_path: Path) -> None:
    """Full pipeline run with bind mode produces a JMX whose Write TG
    PreProcessor reads ``__SHARED_MEM_*_bind`` (subset path), not
    ``__SHARED_MEM_*_columns`` (legacy full-row path).

    Exercises the skeleton.py schemaless wiring (commit 6 §7.2): the
    schemaless branch must pass ``write_configs`` into
    ``generate_rest_write_thread_group`` so the per-table bind-mode flag
    actually reaches the PreProcessor template.

    Implementation note: this test patches ``generate_rest_write_thread_group``
    at the *module* imported by skeleton, then asserts the call kwargs.
    A simpler variant (call ``JMXSkeletonGenerator(...).generate()`` with
    a real model + cfg) would also work but requires YAML parsing in the
    test body — the kwargs-assertion is more focused.
    """
    from jmx_skeleton_generator.generators import skeleton as skel_mod
    from jmx_skeleton_generator.generators.skeleton import JMXSkeletonGenerator
    from config_parser.models import (
        ConnConfig, RestApiConfig, TestConfig, TestModelConfig,
        TsDbConfig, TsTableConfig, WriteConfig,
    )

    cfg = TestConfig(
        conn_config=ConnConfig(db_url="jdbc:kaiwudb://localhost:26257/defaultdb"),
        write_config=[WriteConfig(
            tbl_name="iot_monitor.meters", mode="schemaless",
            throughput=60.0, num_threads=4, device_per_thread=2,
            col_tag_bind_mode=True, col_num_per_tag=3,
        )],
        rest_api_config=RestApiConfig(
            https_mode="tls", login_user="root",
            ca_cert_path="/tmp/ca.crt", login_password="root123",
        ),
    )
    model = TestModelConfig(ts_dbs=[TsDbConfig(
        name="iot_monitor",
        tables=[TsTableConfig(
            name="meters", data_col_count=10, primary_tag_count=1,
            primary_tags=[{"col_type": "varchar(64)", "type_proportion": 1.0}],
            regular_tags=[], data_cols=[],
        )],
    )])

    captured: dict = {}
    real = skel_mod.generate_rest_write_thread_group

    def spy(model_arg, rest_arg, **kwargs):
        captured["write_configs"] = kwargs.get("write_configs")
        return real(model_arg, rest_arg, **kwargs)

    with patch.object(skel_mod, "generate_rest_write_thread_group", side_effect=spy):
        JMXSkeletonGenerator(cfg, output_dir=str(tmp_path), model=model).generate()

    assert captured.get("write_configs") is not None, (
        "skeleton schemaless branch must pass write_configs into "
        "generate_rest_write_thread_group (commit 6 §7.2 wiring)"
    )
    assert len(captured["write_configs"]) == 1
    assert captured["write_configs"][0].tbl_name == "iot_monitor.meters"
    assert captured["write_configs"][0].col_tag_bind_mode is True


def test_mixed_table_end_to_end(tmp_path: Path) -> None:
    """Mixed-table (bind + full-row) wiring: bind table passes bind_mode,
    full-row table passes ``col_tag_bind_mode=False`` (no rebroadcast).

    Exercises the write_cfg_by_table lookup inside
    ``generate_rest_write_thread_group`` (commit 5 fix ``76cb16a``):
    a missing fqn in ``write_cfg_by_table`` falls back to the legacy
    full-row path with ``col_tag_bind_mode=False``, ``col_num_per_tag=0``,
    ``device_per_thread=1``.

    Implementation: two write_configs, one bind + one full-row, run
    skeleton.generate(), assert both PreProcessors emit the expected
    row-source marker (``_bind`` for the bind table, ``_columns`` for
    the full-row table).
    """
    from jmx_skeleton_generator.generators.skeleton import JMXSkeletonGenerator
    from config_parser.models import (
        ConnConfig, RestApiConfig, TestConfig, TestModelConfig,
        TsDbConfig, TsTableConfig, WriteConfig,
    )

    cfg = TestConfig(
        conn_config=ConnConfig(db_url="jdbc:kaiwudb://localhost:26257/defaultdb"),
        write_config=[
            WriteConfig(tbl_name="iot_monitor.t_bind", mode="schemaless",
                        throughput=60.0, num_threads=2, device_per_thread=2,
                        col_tag_bind_mode=True, col_num_per_tag=3),
            WriteConfig(tbl_name="iot_monitor.t_full", mode="schemaless",
                        throughput=60.0, num_threads=2, device_per_thread=2),
        ],
        rest_api_config=RestApiConfig(
            https_mode="tls", login_user="root",
            ca_cert_path="/tmp/ca.crt", login_password="root123",
        ),
    )
    model = TestModelConfig(ts_dbs=[TsDbConfig(
        name="iot_monitor",
        tables=[
            TsTableConfig(name="t_bind", data_col_count=10, primary_tag_count=1,
                          primary_tags=[{"col_type": "varchar(64)", "type_proportion": 1.0}],
                          regular_tags=[], data_cols=[]),
            TsTableConfig(name="t_full", data_col_count=10, primary_tag_count=1,
                          primary_tags=[{"col_type": "varchar(64)", "type_proportion": 1.0}],
                          regular_tags=[], data_cols=[]),
        ],
    )])

    out_path = JMXSkeletonGenerator(cfg, output_dir=str(tmp_path), model=model).generate()
    xml = out_path.read_text(encoding="utf-8")

    # bind table: PreProcessor reads __SHARED_MEM_*_bind
    assert "__SHARED_MEM_iot_monitor_t_bind_bind" in xml, (
        "bind table must reference its __SHARED_MEM_*_bind SharedMemory key"
    )
    # full-row table: PreProcessor reads __SHARED_MEM_*_columns (legacy)
    assert "__SHARED_MEM_iot_monitor_t_full_columns" in xml, (
        "full-row table must reference __SHARED_MEM_*_columns (legacy path)"
    )


# ---------------------------------------------------------------------------
# commit 6 (2026-08-10) end-to-end tests use inline imports so the wiring
# spy in ``test_end_to_end_col_bind_emits_subset_jmx`` stays local to that
# test body — module-top-level imports would force the spy / WriteConfig
# / JMXSkeletonGenerator coupling across all tests in this module.
# ---------------------------------------------------------------------------

from kwjdbc_svt.main import EXIT_VALIDATION  # noqa: E402  (used by validation tests)
