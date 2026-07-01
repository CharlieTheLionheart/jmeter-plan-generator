"""Tests for config_parser YAML loading and parsing."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config_parser import ConfigParserError, parse_test_cfg_yaml, parse_test_model_yaml


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _valid_model() -> dict:
    return {
        "rel_dbs": [
            {
                "name": "iot_metadata",
                "tables": [
                    {
                        "name": "t_workshop",
                        "primary_key_count": 1,
                        "data_col_count": 1,
                        "primary_keys": [
                            {"col_type": "int8", "type_proportion": 1.0}
                        ],
                        "data_cols": [
                            {"col_type": "varchar(64)", "type_proportion": 1.0}
                        ],
                    }
                ],
            }
        ]
    }


def _valid_cfg() -> dict:
    return {
        "conn_config": {
            "db_url": "jdbc:kaiwudb://localhost:26257/iot",
            "conn_pool_size": 10,
            "device_start": 1,
            "test_duration": 60,
        },
        "write_config": [
            {
                "tbl_name": "t_workshop",
                "throughput": 1000,
                "mode": "single_insert",
                "num_threads": 10,
            }
        ],
    }


def test_parse_valid_test_model(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, "test_model.yaml", _valid_model())
    model = parse_test_model_yaml(path)
    assert len(model.rel_dbs) == 1
    assert model.rel_dbs[0].name == "iot_metadata"


def test_parse_valid_test_cfg(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, "test_cfg.yaml", _valid_cfg())
    cfg = parse_test_cfg_yaml(path)
    assert cfg.conn_config.db_url == "jdbc:kaiwudb://localhost:26257/iot"


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigParserError, match="file not found"):
        parse_test_model_yaml(tmp_path / "missing.yaml")


def test_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("not: valid: yaml: [", encoding="utf-8")
    with pytest.raises(ConfigParserError, match="invalid YAML"):
        parse_test_model_yaml(path)


def test_empty_yaml(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigParserError, match="empty or has null root"):
        parse_test_model_yaml(path)


def test_missing_mandatory_field(tmp_path: Path) -> None:
    data = _valid_model()
    del data["rel_dbs"][0]["tables"][0]["name"]
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError):
        parse_test_model_yaml(path)


def test_type_proportion_valid(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["data_cols"] = [
        {"col_type": "int8", "type_proportion": 0.1},
        {"col_type": "int4", "type_proportion": 0.2},
        {"col_type": "varchar(32)", "type_proportion": 0.7},
    ]
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    model = parse_test_model_yaml(path)
    assert len(model.rel_dbs[0].tables[0].data_cols) == 3


def test_type_proportion_invalid(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["data_cols"] = [
        {"col_type": "int8", "type_proportion": 0.5},
        {"col_type": "int4", "type_proportion": 0.4},
    ]
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="type_proportion"):
        parse_test_model_yaml(path)


def test_type_proportion_float_epsilon(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["data_cols"] = [
        {"col_type": "int8", "type_proportion": 0.1},
        {"col_type": "int4", "type_proportion": 0.2},
        {"col_type": "varchar(32)", "type_proportion": 0.7},
    ]
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    # 0.1 + 0.2 + 0.7 may not be exactly 1.0 due to floating point
    model = parse_test_model_yaml(path)
    assert model is not None


def test_nullable_false_with_null_rate(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["data_cols"][0]["nullable"] = False
    data["rel_dbs"][0]["tables"][0]["data_cols"][0]["null_rate"] = 0.1
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="nullable"):
        parse_test_model_yaml(path)


def test_null_rate_out_of_range(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["data_cols"][0]["null_rate"] = 1.5
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError):
        parse_test_model_yaml(path)


def test_primary_tag_count_range(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["primary_tag_count"] = 5
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="primary_tag_count"):
        parse_test_model_yaml(path)


def test_primary_tag_rejects_nullable_field(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["primary_tags"] = [
        {"col_type": "varchar(32)", "type_proportion": 1.0, "nullable": False}
    ]
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError):
        parse_test_model_yaml(path)


def test_primary_tag_rejects_float(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["primary_tags"] = [
        {"col_type": "float4", "type_proportion": 1.0}
    ]
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="float4"):
        parse_test_model_yaml(path)


def test_primary_tag_rejects_long_varchar(tmp_path: Path) -> None:
    data = _valid_model()
    data["ts_dbs"] = [
        {
            "name": "iot_data",
            "tables": [
                {
                    "name": "t_cnc",
                    "data_col_count": 1,
                    "ts_col": {"name": "ts", "type": "timestamp", "ms_step": 1000},
                    "primary_tag_count": 1,
                    "regular_tag_count": 0,
                    "primary_tags": [
                        {"col_type": "varchar(256)", "type_proportion": 1.0}
                    ],
                    "data_cols": [
                        {"col_type": "int8", "type_proportion": 1.0}
                    ],
                }
            ],
        }
    ]
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="exceeds 128"):
        parse_test_model_yaml(path)


def test_tag_rejects_timestamp(tmp_path: Path) -> None:
    data = _valid_model()
    data["ts_dbs"] = [
        {
            "name": "iot_data",
            "tables": [
                {
                    "name": "t_cnc",
                    "data_col_count": 1,
                    "ts_col": {"name": "ts", "type": "timestamp", "ms_step": 1000},
                    "primary_tag_count": 1,
                    "regular_tag_count": 1,
                    "primary_tags": [
                        {"col_type": "varchar(64)", "type_proportion": 1.0}
                    ],
                    "regular_tags": [
                        {"col_type": "timestamp", "type_proportion": 1.0}
                    ],
                    "data_cols": [
                        {"col_type": "int8", "type_proportion": 1.0}
                    ],
                }
            ],
        }
    ]
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="timestamp"):
        parse_test_model_yaml(path)


def test_with_hash_range(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["with_hash"] = 60000
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="with_hash"):
        parse_test_model_yaml(path)


def test_foreign_key_target_missing(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["data_cols"][0]["val_range"] = (
        "ref:iot_metadata.t_missing.col"
    )
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="foreign key target"):
        parse_test_model_yaml(path)


def test_foreign_key_target_exists(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["data_cols"][0]["val_range"] = (
        "ref:iot_metadata.t_workshop.int8"
    )
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    model = parse_test_model_yaml(path)
    assert model is not None


def test_empty_integer_interval(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["primary_keys"][0]["col_type"] = "int8"
    data["rel_dbs"][0]["tables"][0]["primary_keys"][0]["val_range"] = "(1,2)"
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="no valid integer"):
        parse_test_model_yaml(path)


def test_interval_reverse_order(tmp_path: Path) -> None:
    data = _valid_model()
    data["rel_dbs"][0]["tables"][0]["primary_keys"][0]["val_range"] = "[10,1]"
    path = _write_yaml(tmp_path, "test_model.yaml", data)
    with pytest.raises(ConfigParserError, match="lower bound"):
        parse_test_model_yaml(path)


def test_write_num_threads_inconsistent(tmp_path: Path) -> None:
    data = _valid_cfg()
    data["write_config"].append(
        {"tbl_name": "t_motor", "throughput": 1000, "mode": "single_insert", "batch_lines": 1, "num_threads": 5}
    )
    path = _write_yaml(tmp_path, "test_cfg.yaml", data)
    with pytest.raises(ConfigParserError, match="num_threads"):
        parse_test_cfg_yaml(path)


def test_query_placeholder_unbound(tmp_path: Path) -> None:
    data = _valid_cfg()
    data["query_config"] = [{"query": "SELECT * FROM t WHERE LIMIT ?", "num_threads": 1}]
    path = _write_yaml(tmp_path, "test_cfg.yaml", data)
    with pytest.raises(ConfigParserError):
        parse_test_cfg_yaml(path)


def test_query_placeholder_bound(tmp_path: Path) -> None:
    data = _valid_cfg()
    data["query_config"] = [
        {"query": "SELECT * FROM t WHERE col_int8_1 = ?", "mode": "statement", "num_threads": 1}
    ]
    path = _write_yaml(tmp_path, "test_cfg.yaml", data)
    cfg = parse_test_cfg_yaml(path)
    assert len(cfg.query_config) == 1
