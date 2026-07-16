"""CLI entry point for the KaiwuDB SVT test-plan generator.

Design: openspec/changes/main-entry/design.md

Three responsibilities only — CLI parsing, configuration loading, and
error-to-exit-code mapping. The actual JMX assembly is delegated to
:mod:`jmx_skeleton_generator.generators.skeleton.JMXSkeletonGenerator`.
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path
from typing import List, Optional, Tuple

from column_namer import ColumnNamer
from config_parser.models import ConfigParserError, TestConfig, TestModelConfig
from config_parser.parser import parse_test_cfg_yaml, parse_test_model_yaml
from ddl_generator.generator import DDLGenerator, DdlGenerationError
from jdbc_datasource.jdbc_data_source_generator import JmxGenerationError
from jmx_skeleton_generator.generators.skeleton import JMXSkeletonGenerator
from prepared_insert_template.generator import (
    PreparedInsertTemplateGenerator,
    requires_prepared_insert_templates,
)
from seed_data_generator.adapter import SeedGenError
from seed_data_generator.orchestrator import generate_seeds


EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_SEED = 2
EXIT_DDL = 3
EXIT_JMX = 4
EXIT_UNEXPECTED = 5
EXIT_KEYBOARD_INTERRUPT = 130


_DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

logger = logging.getLogger("kwjdbc_svt")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments via :mod:`argparse`.

    Positional: ``test_model.yaml`` ``test_cfg.yaml``.
    Optional: ``-o/--output-dir`` (default: cwd), ``-v/--verbose`` (repeatable).
    """
    parser = argparse.ArgumentParser(
        prog="python -m kwjdbc_svt.main",
        description=(
            "Generate a JMeter test plan + seed files from test_model.yaml "
            "and test_cfg.yaml."
        ),
    )
    parser.add_argument(
        "test_model",
        type=Path,
        help="Path to test_model.yaml.",
    )
    parser.add_argument(
        "test_cfg",
        type=Path,
        help="Path to test_cfg.yaml.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Output directory (default: current working directory).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity: -v → INFO, -vv → DEBUG (default: WARNING).",
    )
    return parser.parse_args(argv)


def setup_logging(verbose_level: int) -> None:
    """Configure root logger with the requested verbosity.

    Verbosity mapping: 0 → WARNING, 1 → INFO, 2 → DEBUG. Higher counts
    stay at DEBUG.
    """
    level = logging.WARNING
    if verbose_level == 1:
        level = logging.INFO
    elif verbose_level >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format=_DEFAULT_LOG_FORMAT,
        force=True,
    )


def load_configs(args: argparse.Namespace) -> Tuple[TestModelConfig, TestConfig]:
    """Parse test_model + test_cfg files.

    Raises :class:`ConfigParserError` (mapped to exit code 1). Missing
    files, empty YAML roots, and Pydantic validation failures are all
    funnelled through this exception.
    """
    model = parse_test_model_yaml(args.test_model)
    cfg = parse_test_cfg_yaml(args.test_cfg)
    return model, cfg


def map_exception_to_exit_code(exc: BaseException) -> int:
    """Map a runtime exception to a stable shell exit code."""
    if isinstance(exc, ConfigParserError):
        return EXIT_VALIDATION
    if isinstance(exc, SeedGenError):
        return EXIT_SEED
    if isinstance(exc, DdlGenerationError):
        return EXIT_DDL
    if isinstance(exc, JmxGenerationError):
        return EXIT_JMX
    return EXIT_UNEXPECTED


def _build_columns_by_table(model: TestModelConfig) -> dict[str, List[str]]:
    """Produce the ``{db.table: [col_names...]}`` mapping for the whole model.

    Iterates the relational and time-series databases; primary-tag
    columns are included in the list.

    For time-series tables, ``ts_col`` is prepended to the column list
    so the generated INSERT template contains the timestamp column —
    the batch_prepared sampler appends a per-row timestamp to each
    row, so the template's ``?`` count must match.
    """
    out: dict[str, List[str]] = {}
    for db in list(model.rel_dbs) + list(model.ts_dbs):
        for table in db.tables:
            namer = ColumnNamer(table)
            names, _idx = namer()
            ts_col_name = getattr(table, "ts_col", None)
            ts_name = ts_col_name.name if ts_col_name else None
            column_list: List[str] = []
            if ts_name:
                column_list.append(ts_name)
            column_list.extend(names)
            fqn = f"{db.name}.{table.name}".lower()
            out[fqn] = column_list
    return out


def _wants_prepared(cfg: TestConfig) -> bool:
    """True when any write_config entry uses a prepared-statement mode."""
    return requires_prepared_insert_templates(cfg.write_config)


def _run_pipeline(
    model: TestModelConfig,
    cfg: TestConfig,
    output_dir: Path,
) -> None:
    """Wire model → seeds → DDL → prepared-templates → JMXSkeletonGenerator.

    output_dir is the user-facing destination; the seed tree is rooted
    at ``output_dir/seeds/`` per spec.md §"Output seed directory
    structure"; the final JMX lives at ``output_dir/test_plan.jmx``.
    """
    columns_by_table = _build_columns_by_table(model)

    # Seeds (under seeds/ subdir; absolute path passed to generate_seeds)
    seeds_root = output_dir / "seeds"
    seed_paths_map = generate_seeds(model, seeds_root)
    # Reshape seed_paths_map (db_name.table -> list[Path]) into
    # seed_csv_paths (db_name -> {table_name -> csv_path}) for the
    # skeleton. Each entry is the row-aggregate CSV (last path is the
    # aggregate; column seed files are written but not used by the
    # skeleton — shared-memory setup reads them directly).
    seed_csv_paths: dict[str, dict[str, str]] = {}
    for fqn, paths in seed_paths_map.items():
        db_name, table_name = fqn.split(".", 1)
        if paths:
            seed_csv_paths.setdefault(db_name, {})[table_name] = str(paths[-1])

    # DDL
    ddl_statements = DDLGenerator(model).generate_statements()

    # Prepared templates (conditional)
    prepared_templates: dict[str, str] = {}
    if _wants_prepared(cfg):
        generator = PreparedInsertTemplateGenerator(
            model, cfg.write_config, columns_by_table
        )
        prepared_templates = generator.generate()

    # JMX
    JMXSkeletonGenerator(
        test_config=cfg,
        ddl_statements=ddl_statements,
        prepared_templates=prepared_templates,
        seed_csv_paths=seed_csv_paths,
        output_dir=str(output_dir),
        model=model,
    ).generate()


def main(argv: Optional[List[str]] = None) -> int:
    """Run the CLI pipeline end-to-end.

    Returns an integer exit code suitable for ``sys.exit``. Never
    raises :class:`SystemExit` directly. ``KeyboardInterrupt`` is
    mapped to exit code 130.
    """
    try:
        args = parse_args(argv)
        setup_logging(args.verbose)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("writing artifacts to %s", output_dir)

        model, cfg = load_configs(args)
        _run_pipeline(model, cfg, output_dir)
        logger.info("done")
        return EXIT_OK

    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT

    except BaseException as exc:
        exit_code = map_exception_to_exit_code(exc)
        if exit_code == EXIT_UNEXPECTED and logging.getLogger().level <= logging.DEBUG:
            traceback.print_exc()
        else:
            logger.error("%s: %s", type(exc).__name__, exc)
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
