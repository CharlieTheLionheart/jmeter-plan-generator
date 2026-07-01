"""YAML parsing entry points for configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from config_parser.models import (
    ConfigParserError,
    TestConfig,
    TestModelConfig,
    validate_foreign_key_refs,
    validate_val_ranges,
)


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return its Python representation.

    Raises ConfigParserError on missing files or invalid YAML syntax.
    """
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as fh:
            content = fh.read()
    except FileNotFoundError as exc:
        raise ConfigParserError(f"file not found: {path}") from exc
    except OSError as exc:
        raise ConfigParserError(f"cannot read file {path}: {exc}") from exc

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ConfigParserError(f"invalid YAML in {path}: {exc}") from exc

    if data is None:
        raise ConfigParserError(f"YAML file is empty or has null root: {path}")
    if not isinstance(data, dict):
        raise ConfigParserError(f"YAML root must be a mapping: {path}")
    return data


def validate_consistency(model: TestModelConfig, cfg: TestConfig) -> list[str]:
    """Validate consistency between TestModelConfig and TestConfig.

    Returns a list of error messages (empty if validation passes).
    """
    errors: list[str] = []

    # Collect all table names from the model
    model_table_names: set[str] = set()
    for db in model.rel_dbs + model.ts_dbs:
        for table in db.tables:
            model_table_names.add(table.name)

    # Check that write_config targets exist in the model
    for wc in cfg.write_config:
        if wc.tbl_name != "all" and wc.tbl_name not in model_table_names:
            errors.append(
                f"write_config tbl_name='{wc.tbl_name}' not found in test_model"
            )

    return errors


def parse_test_model_yaml(path: str | Path) -> TestModelConfig:
    """Parse a test_model.yaml file into TestModelConfig."""
    data = load_yaml(path)
    try:
        model = TestModelConfig.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - wrap all validation errors uniformly
        raise ConfigParserError(f"test_model validation failed: {exc}") from exc

    validate_foreign_key_refs(model)
    validate_val_ranges(model)
    return model


def parse_test_cfg_yaml(path: str | Path) -> TestConfig:
    """Parse a test_cfg.yaml file into TestConfig."""
    data = load_yaml(path)
    try:
        return TestConfig.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - wrap all validation errors uniformly
        raise ConfigParserError(f"test_cfg validation failed: {exc}") from exc


__all__ = [
    "load_yaml",
    "validate_consistency",
    "parse_test_model_yaml",
    "parse_test_cfg_yaml",
]
