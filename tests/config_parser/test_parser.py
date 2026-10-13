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
            "db_url": "jdbc:kaiwudb://localhost:26257/defaultdb",
            "conn_pool_size": 10,
            "device_start": 1,
            "test_duration": 60,
        },
        "write_config": [
            {
                "tbl_name": "t_workshop",
                "throughput": 1000,
                "mode": "direct",
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
    assert cfg.conn_config.db_url == "jdbc:kaiwudb://localhost:26257/defaultdb"


# ---------------------------------------------------------------------------
# pub_sub_config 真实 fixture yaml 解析 (OpenSpec pub-sub-end-to-end §4)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "kwjdbc_svt" / "fixtures"


def test_parse_pub_sub_database_mode_fixture() -> None:
    """整库模式 fixture (test_cfg_pub_sub.yaml):
    ``pub_sub_config.tables`` 为 None, ``expected_min_rows`` 未设 (默认 None).

    Per tasks.md §4.1: ``config_parser.parse_test_cfg_yaml(...)`` 解析
    无 ``ValidationError``, ``pub_sub_config`` 字段被加载为 ``PubSubConfig`` 实例.
    """
    path = FIXTURES_DIR / "test_cfg_pub_sub.yaml"
    cfg = parse_test_cfg_yaml(path)
    assert cfg.pub_sub_config is not None
    pub_sub = cfg.pub_sub_config
    assert pub_sub.publisher_db == "iot_monitor"
    assert pub_sub.publication_name == "pub_iot"
    assert pub_sub.subscription_name == "sub_iot"
    assert pub_sub.conninfo == (
        "postgresql://root@127.0.0.1:26257/iot_monitor?sslmode=disable"
    )
    assert pub_sub.tables is None  # 整库模式
    assert pub_sub.expected_min_rows is None  # 默认 (Verify TG 内联 1)
    assert pub_sub.options == {
        "target": '{"iot_monitor.t_cnc":"iot_monitor_sub.t_cnc"}',
        "enable": "on",
    }


def test_parse_pub_sub_table_mode_fixture() -> None:
    """表级 fixture (test_cfg_pub_sub_tables.yaml):
    ``pub_sub_config.tables`` 含 1 张表 + columns 子集 + where 过滤 +
    ``expected_min_rows=0`` (恒真, WHERE 过滤场景).

    Per tasks.md §4.2: 解析无 ``ValidationError``, ``pub_sub_config`` 字段
    被加载为 ``PubSubConfig`` 实例 + tables / columns / where / expected_min_rows
    都正确解析.
    """
    path = FIXTURES_DIR / "test_cfg_pub_sub_tables.yaml"
    cfg = parse_test_cfg_yaml(path)
    assert cfg.pub_sub_config is not None
    pub_sub = cfg.pub_sub_config
    assert pub_sub.publisher_db == "iot_monitor"
    assert pub_sub.publication_name == "pub_iot_tables"
    assert pub_sub.subscription_name == "sub_iot_tables"
    assert pub_sub.tables is not None
    assert len(pub_sub.tables) == 1
    entry = pub_sub.tables[0]
    assert entry.name == "t_cnc"
    assert entry.columns == ["k_timestamp", "device_id", "col_float8_1"]
    assert entry.where == "col_float8_1 > 0"
    assert pub_sub.expected_min_rows == 0
    assert pub_sub.options == {
        "target": '{"iot_monitor.t_cnc":"iot_monitor_sub.t_cnc"}',
        "ignore_history": "true",
        "retry": "5s",
    }


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
    # ref: target uses column_namer-allocated name (pk_int8_1 for an int8 PK),
    # not col_type — multiple columns with the same type must be addressable
    # by their generated name.
    data["rel_dbs"][0]["tables"][0]["data_cols"][0]["val_range"] = (
        "ref:iot_metadata.t_workshop.pk_int8_1"
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
        {"tbl_name": "t_motor", "throughput": 1000, "mode": "direct", "batch_lines": 1, "num_threads": 5}
    )
    path = _write_yaml(tmp_path, "test_cfg.yaml", data)
    with pytest.raises(ConfigParserError, match="num_threads"):
        parse_test_cfg_yaml(path)


def test_schemaless_mode_accepted(tmp_path: Path) -> None:
    """rest-schemaless-write §A: ``schemaless`` is now a valid mode value;
    the previously-deferred reject_schemaless validator was removed in §5.
    Parser must accept mode=schemaless without raising. The HTTP path
    dispatch + rest_api_config missing check live in JMXSkeletonGenerator.
    """
    data = _valid_cfg()
    data["write_config"][0]["mode"] = "schemaless"
    path = _write_yaml(tmp_path, "test_cfg.yaml", data)
    cfg = parse_test_cfg_yaml(path)
    assert cfg.write_config[0].mode == "schemaless"


def test_query_placeholder_unbound(tmp_path: Path) -> None:
    data = _valid_cfg()
    data["query_config"] = [{"query": "SELECT * FROM t WHERE LIMIT ?", "num_threads": 1}]
    path = _write_yaml(tmp_path, "test_cfg.yaml", data)
    with pytest.raises(ConfigParserError):
        parse_test_cfg_yaml(path)


def test_query_placeholder_bound(tmp_path: Path) -> None:
    data = _valid_cfg()
    data["query_config"] = [
        {"query": "SELECT * FROM t WHERE col_int8_1 = ?", "num_threads": 1}
    ]
    path = _write_yaml(tmp_path, "test_cfg.yaml", data)
    cfg = parse_test_cfg_yaml(path)
    assert len(cfg.query_config) == 1
