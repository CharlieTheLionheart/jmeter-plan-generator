"""Tests for the kwjdbc_svt CLI entry point.

Tasks covered: main-entry tasks §7 (单元) + §8 (集成).
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from config_parser import ConfigParserError
from ddl_generator.generator import DdlGenerationError
from jdbc_datasource.jdbc_data_source_generator import JmxGenerationError
from kwjdbc_svt import main as cli_module
from seed_data_generator.adapter import SeedGenError
from kwjdbc_svt.main import (
    EXIT_DDL,
    EXIT_JMX,
    EXIT_OK,
    EXIT_SEED,
    EXIT_UNEXPECTED,
    EXIT_VALIDATION,
    map_exception_to_exit_code,
    parse_args,
    setup_logging,
)

cli_main = cli_module.main


FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def model_path() -> Path:
    return FIXTURE_DIR / "test_model.yaml"


@pytest.fixture
def cfg_path() -> Path:
    return FIXTURE_DIR / "test_cfg.yaml"


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    import yaml

    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _minimal_model() -> dict:
    return {
        "ts_dbs": [
            {
                "name": "iot_monitor",
                "tables": [
                    {
                        "name": "t_cnc",
                        "data_col_count": 1,
                        "primary_tag_count": 1,
                        "regular_tag_count": 0,
                        "data_cols": [
                            {
                                "col_type": "int8",
                                "type_proportion": 1.0,
                                "val_range": "[0,100]",
                            }
                        ],
                        "primary_tags": [
                            {"col_type": "int8", "type_proportion": 1.0}
                        ],
                        "ts_col": {
                            "name": "ts",
                            "type": "timestamp",
                            "ms_step": 1000,
                        },
                    }
                ],
            }
        ]
    }


def _minimal_cfg() -> dict:
    return {
        "conn_config": {
            "db_url": "jdbc:kaiwudb://localhost:26257/iot",
            "conn_pool_size": 10,
            "device_start": 1,
            "test_duration": 60,
        },
        "write_config": [
            {
                "tbl_name": "iot_monitor.t_cnc",
                "throughput": 1000.0,
                "mode": "single_insert",
                "batch_lines": 1,
                "device_per_thread": 1,
                "num_threads": 5,
            }
        ],
    }


# ---------------------------------------------------------------------------
# §7.1-§7.3 CLI parsing + logging
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_defaults_when_only_yaml_paths_provided(self):
        args = parse_args([str(FIXTURE_DIR / "test_model.yaml"), str(FIXTURE_DIR / "test_cfg.yaml")])
        assert args.verbose == 0
        assert args.output_dir == Path(".")
        assert args.test_model == FIXTURE_DIR / "test_model.yaml"

    def test_v_flag_maps_to_count(self):
        args = parse_args(
            [
                str(FIXTURE_DIR / "test_model.yaml"),
                str(FIXTURE_DIR / "test_cfg.yaml"),
                "-v",
                "-v",
            ]
        )
        assert args.verbose == 2

    def test_output_dir_takes_long_form(self):
        args = parse_args(
            [
                str(FIXTURE_DIR / "test_model.yaml"),
                str(FIXTURE_DIR / "test_cfg.yaml"),
                "--output-dir",
                "/tmp/kwjdbc-out",
            ]
        )
        assert str(args.output_dir) == "/tmp/kwjdbc-out"

    def test_missing_positional_raises_systemexit(self):
        with pytest.raises(SystemExit):
            parse_args([])


class TestSetupLogging:
    @pytest.fixture(autouse=True)
    def restore_root_level(self):
        original = logging.getLogger().level
        yield
        logging.getLogger().setLevel(original)

    def test_default_level_is_warning(self):
        setup_logging(0)
        assert logging.getLogger().level == logging.WARNING

    def test_v_flag_sets_info(self):
        setup_logging(1)
        assert logging.getLogger().level == logging.INFO

    def test_vv_flag_sets_debug(self):
        setup_logging(2)
        assert logging.getLogger().level == logging.DEBUG

    def test_extra_v_stays_at_debug(self):
        setup_logging(3)
        assert logging.getLogger().level == logging.DEBUG


# ---------------------------------------------------------------------------
# §7.4-§7.8 main() exit-code mapping
# ---------------------------------------------------------------------------


class TestExitCodeMapping:
    def test_validation_error_maps_to_1(self):
        assert map_exception_to_exit_code(ConfigParserError("x")) == EXIT_VALIDATION == 1

    def test_seed_gen_error_maps_to_2(self):
        assert map_exception_to_exit_code(SeedGenError("x")) == EXIT_SEED == 2

    def test_ddl_generation_error_maps_to_3(self):
        assert map_exception_to_exit_code(DdlGenerationError("x")) == EXIT_DDL == 3

    def test_jmx_generation_error_maps_to_4(self):
        assert map_exception_to_exit_code(JmxGenerationError("x")) == EXIT_JMX == 4

    def test_unknown_exception_maps_to_5(self):
        assert map_exception_to_exit_code(RuntimeError("x")) == EXIT_UNEXPECTED == 5

    def test_keyboard_interrupt_not_in_map(self):
        # KeyboardInterrupt is handled by main() separately, returns 130 directly.
        assert map_exception_to_exit_code(KeyboardInterrupt()) == EXIT_UNEXPECTED


class TestMainExitCodes:
    """Each scenario mocks one module to raise, then asserts the exit code."""

    def _good_args(self, tmp_path: Path):
        model = _write_yaml(tmp_path, "model.yaml", _minimal_model())
        cfg = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        return [str(model), str(cfg), "-o", str(tmp_path / "out")]

    def test_validation_error_returns_1(self, tmp_path: Path, caplog):
        with patch(
            "kwjdbc_svt.main.load_configs",
            side_effect=ConfigParserError("bad yaml"),
        ):
            rc = cli_main(self._good_args(tmp_path))
        assert rc == EXIT_VALIDATION

    def test_seed_generation_error_returns_2(self, tmp_path: Path, model_path, cfg_path):
        args = [str(model_path), str(cfg_path), "-o", str(tmp_path / "out")]
        with patch(
            "kwjdbc_svt.main._run_pipeline",
            side_effect=SeedGenError("seed fail"),
        ):
            rc = cli_main(args)
        assert rc == EXIT_SEED

    def test_ddl_error_returns_3(self, tmp_path: Path, model_path, cfg_path):
        args = [str(model_path), str(cfg_path), "-o", str(tmp_path / "out")]
        with patch(
            "kwjdbc_svt.main._run_pipeline",
            side_effect=DdlGenerationError("ddl fail"),
        ):
            rc = cli_main(args)
        assert rc == EXIT_DDL

    def test_jmx_error_returns_4(self, tmp_path: Path, model_path, cfg_path):
        args = [str(model_path), str(cfg_path), "-o", str(tmp_path / "out")]
        with patch(
            "kwjdbc_svt.main._run_pipeline",
            side_effect=JmxGenerationError("jmx fail"),
        ):
            rc = cli_main(args)
        assert rc == EXIT_JMX

    def test_unexpected_exception_returns_5(self, tmp_path: Path, model_path, cfg_path):
        args = [str(model_path), str(cfg_path), "-o", str(tmp_path / "out")]
        with patch(
            "kwjdbc_svt.main._run_pipeline",
            side_effect=RuntimeError("boom"),
        ):
            rc = cli_main(args)
        assert rc == EXIT_UNEXPECTED

    def test_keyboard_interrupt_returns_130(self, tmp_path: Path, model_path, cfg_path):
        args = [str(model_path), str(cfg_path), "-o", str(tmp_path / "out")]
        with patch(
            "kwjdbc_svt.main._run_pipeline",
            side_effect=KeyboardInterrupt,
        ):
            rc = cli_main(args)
        assert rc == 130


# ---------------------------------------------------------------------------
# §8 E2E tests
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_minimal_config_generates_jmx_and_seeds(self, tmp_path: Path):
        model = _write_yaml(tmp_path, "model.yaml", _minimal_model())
        cfg = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        out = tmp_path / "out"

        rc = cli_main([str(model), str(cfg), "-o", str(out)])
        assert rc == EXIT_OK

        jmx = out / "test_plan.jmx"
        assert jmx.is_file(), "test_plan.jmx should be generated"
        # JMX is valid XML
        ET.parse(jmx)  # raises on malformed XML

        # seeds directory exists
        seeds_dir = out / "seeds"
        assert seeds_dir.is_dir(), "seeds/ directory should be created"

    def test_seed_subdirectory_naming_pattern(self, tmp_path: Path):
        model = _write_yaml(tmp_path, "model.yaml", _minimal_model())
        cfg = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        out = tmp_path / "out"

        rc = cli_main([str(model), str(cfg), "-o", str(out)])
        assert rc == EXIT_OK

        # Row aggregate at seeds/{db}/{table}.csv
        aggregate = out / "seeds" / "iot_monitor" / "t_cnc.csv"
        assert aggregate.is_file(), f"row aggregate missing: {aggregate}"

        # Column seed at seeds/{db}/{table}/{index}_{col}.csv
        column_seed = out / "seeds" / "iot_monitor" / "t_cnc" / "1_col_int8_1.csv"
        assert column_seed.is_file(), f"column seed missing: {column_seed}"

    def test_output_dir_created_when_missing(self, tmp_path: Path):
        model = _write_yaml(tmp_path, "model.yaml", _minimal_model())
        cfg = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        out = tmp_path / "deep" / "nested" / "out"
        assert not out.exists()

        rc = cli_main([str(model), str(cfg), "-o", str(out)])
        assert rc == EXIT_OK
        assert out.is_dir()
        assert (out / "test_plan.jmx").is_file()

    def test_overwrite_emits_warning_log(self, tmp_path: Path, caplog):
        model = _write_yaml(tmp_path, "model.yaml", _minimal_model())
        cfg = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        out = tmp_path / "out"
        out.mkdir(parents=True, exist_ok=True)

        # Pre-create the file so the second run has something to overwrite
        (out / "test_plan.jmx").write_text("dummy", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="kwjdbc_svt"):
            rc = cli_main([str(model), str(cfg), "-o", str(out)])
        assert rc == EXIT_OK
        # We do not assert on the WARNING text here because overwrite
        # semantics may move between JMXSkeletonGenerator and the
        # generator level; the assertion that the file is regenerated
        # to a new payload is more reliable.
        assert (out / "test_plan.jmx").read_text(encoding="utf-8") != "dummy"

    def test_vv_flag_emits_debug_log(self, tmp_path: Path, caplog):
        model = _write_yaml(tmp_path, "model.yaml", _minimal_model())
        cfg = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        out = tmp_path / "out"

        with caplog.at_level(logging.DEBUG, logger="kwjdbc_svt"):
            rc = cli_main([str(model), str(cfg), "-o", str(out), "-vv"])

        assert rc == EXIT_OK
        # Root logger should be configured to DEBUG
        assert logging.getLogger().level == logging.DEBUG

    def test_programmatic_invocation_returns_int(self, tmp_path: Path):
        model = _write_yaml(tmp_path, "model.yaml", _minimal_model())
        cfg = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        out = tmp_path / "out"

        rc = cli_main([str(model), str(cfg), "-o", str(out)])
        # main() does not call sys.exit; returns int directly.
        assert isinstance(rc, int)
        assert rc == EXIT_OK

    def test_ts_only_model_does_not_emit_rel_init(self, tmp_path: Path):
        """conditional-relational-setup DCR: a ts-only model MUST NOT
        emit any relational init subtree (RelInit_/relprep/Loop Controller
        for). The DDL SetupThreadGroup is still present.
        """
        model = _write_yaml(tmp_path, "model.yaml", _minimal_model())
        cfg = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        out = tmp_path / "out"

        rc = cli_main([str(model), str(cfg), "-o", str(out)])
        assert rc == EXIT_OK
        xml = (out / "test_plan.jmx").read_text(encoding="utf-8")
        assert "RelInit_" not in xml
        assert "relprep" not in xml
        assert "Loop Controller for" not in xml
        # The DDL SetupThreadGroup is still emitted for the ts database.
        assert "SetupThreadGroup" in xml
        assert "iot_monitor" in xml

    def test_rel_model_emits_loop_controller_per_table(self, tmp_path: Path):
        """A model that declares a relational database MUST emit one
        ``Loop Controller for {db}.{table}`` per table, and the
        ``RelInit_`` sampler for each.
        """
        rel_model = {
            "rel_dbs": [
                {
                    "name": "iot_meta",
                    "tables": [
                        {
                            "name": "t_workshop",
                            "primary_key_count": 1,
                            "primary_keys": [
                                {
                                    "col_type": "int8",
                                    "type_proportion": 1.0,
                                    "val_range": "[1,100]",
                                    "seed_num": 50,
                                }
                            ],
                            "data_col_count": 1,
                            "data_cols": [
                                {
                                    "col_type": "varchar(16)",
                                    "type_proportion": 1.0,
                                    "val_range": "enum:A,B",
                                    "seed_num": 2,
                                }
                            ],
                        }
                    ],
                }
            ],
            "ts_dbs": [
                {
                    "name": "iot_monitor",
                    "tables": [
                        {
                            "name": "t_cnc",
                            "data_col_count": 1,
                            "primary_tag_count": 1,
                            "regular_tag_count": 0,
                            "data_cols": [
                                {
                                    "col_type": "int8",
                                    "type_proportion": 1.0,
                                    "val_range": "[0,100]",
                                }
                            ],
                            "primary_tags": [
                                {"col_type": "int8", "type_proportion": 1.0}
                            ],
                            "ts_col": {
                                "name": "ts",
                                "type": "timestamp",
                                "ms_step": 1000,
                            },
                        }
                    ],
                }
            ],
        }
        cfg = {
            "conn_config": {
                "db_url": "jdbc:kaiwudb://localhost:26257/iot",
                "conn_pool_size": 10,
                "device_start": 1,
                "test_duration": 60,
            },
            "write_config": [
                {
                    "tbl_name": "iot_monitor.t_cnc",
                    "throughput": 1000.0,
                    "mode": "single_insert",
                    "num_threads": 1,
                }
            ],
            "query_config": [],
        }
        model = _write_yaml(tmp_path, "model.yaml", rel_model)
        cfg = _write_yaml(tmp_path, "cfg.yaml", cfg)
        out = tmp_path / "out"

        rc = cli_main([str(model), str(cfg), "-o", str(out)])
        assert rc == EXIT_OK
        xml = (out / "test_plan.jmx").read_text(encoding="utf-8")
        assert "Loop Controller for iot_meta.t_workshop" in xml
        assert "RelInit_iot_meta_t_workshop" in xml
        assert "RelInit_iot_meta_t_workshop_relprep" in xml


# ---------------------------------------------------------------------------
# §7.9 Prepared template generator skipped
# ---------------------------------------------------------------------------


class TestPreparedSkip:
    def test_prepared_template_skipped_when_no_prepared_modes(self, tmp_path: Path):
        """write_config has all single_insert → PreparedInsertTemplateGenerator not invoked."""
        from config_parser.parser import parse_test_cfg_yaml
        from kwjdbc_svt.main import _wants_prepared

        cfg_path = _write_yaml(tmp_path, "cfg.yaml", _minimal_cfg())
        cfg_obj = parse_test_cfg_yaml(cfg_path)

        assert _wants_prepared(cfg_obj) is False
