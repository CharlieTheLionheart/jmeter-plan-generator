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
    # col-tag-bind-write (2026-08-05): main entry cross-reference
    # validation raises ``ValueError`` (per-table constraint violations);
    # treat as validation failure, not unexpected.
    if isinstance(exc, ValueError):
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
            # ColumnNamer.__call__ now returns (names, types_per_name, index_map)
            # — only ``names`` is needed here; types/index_map ignored.
            names, _types, _idx = namer()
            ts_col_name = getattr(table, "ts_col", None)
            ts_name = ts_col_name.name if ts_col_name else None
            column_list: List[str] = []
            if ts_name:
                column_list.append(ts_name)
            column_list.extend(names)
            fqn = f"{db.name}.{table.name}".lower()
            out[fqn] = column_list
    return out


def _validate_col_tag_bind_constraints(
    model: TestModelConfig,
    cfg: TestConfig,
) -> None:
    """col-tag-bind-write (2026-08-05): main entry validation.

    Cross-references each ``col_tag_bind_mode=True`` ``WriteConfig``
    against its ``TestModelConfig`` table. Per-table upper-bound
    (``col_num_per_tag <= data_col_count``) and ptag-count check
    (``primary_tag_count >= 1``) cannot live on ``WriteConfig`` alone
    because they require cross-reference to ``TestModelConfig``.

    Raises :class:`ValueError` naming the offending ``{db}.{table}``.
    Rel tables are skipped: bind mode is a ts-table feature (rel tables
    have no primary tags, so the hash-bucket key is undefined).
    """
    for db in model.ts_dbs:
        for table in db.tables:
            wc = cfg.find_write_config(db.name, table.name)
            if wc is None or not wc.col_tag_bind_mode:
                continue
            fqn = f"{db.name}.{table.name}"
            if wc.col_num_per_tag > table.data_col_count:
                raise ValueError(
                    f"col_tag_bind_mode=true requires col_num_per_tag "
                    f"({wc.col_num_per_tag}) <= data_col_count "
                    f"({table.data_col_count}) for {fqn}"
                )
            if table.primary_tag_count < 1:
                raise ValueError(
                    f"col_tag_bind_mode=true requires primary_tag_count "
                    f">= 1 for {fqn}, got primary_tag_count="
                    f"{table.primary_tag_count}"
                )


def _wants_prepared(cfg: TestConfig) -> bool:
    """True when any write_config entry uses a prepared-statement mode."""
    return requires_prepared_insert_templates(cfg.write_config)


def _build_relational_init_specs(
    model: TestModelConfig,
) -> List:
    """Build relational-table init sampler specs.

    For each rel table this returns one spec dict consumable by
    :func:`jmx_skeleton_generator.generators.ddl_setup
    .generate_ddl_setup_thread_group`'s ``rel_init_specs`` parameter.

    Each spec derives:

    - ``total_rows`` = ``max(seed_num across columns)`` so the row
      aggregate never has gaps (rel-table init assembly uses modulo
      wrap to repeat shorter-seed columns).
    - ``batch_lines`` = largest divisor of ``total_rows`` up to 100 so
      the no-tail-batch invariant (``total_rows % batch_lines == 0``)
      holds by construction.
    - ``columns`` = ColumnNamer-generated name list, in DDL order
      (matches the seed writer's ``{index}_{name}.csv`` numbering).
    - ``rel_col_seed_files`` = ``{index}_{name}.csv`` filenames
      aligned positionally with ``columns``.
    - ``column_types`` = JDBC type names (e.g. ``"BIGINT"``,
      ``"VARCHAR"``) aligned with ``columns``. KaiwuDB's column types
      (``INT8``/``VARCHAR``/``FLOAT4``/...) are translated via
      :data:`_JDBC_TYPE_MAP` because the JDBC driver rejects the
      short form (regression on 2026-07-17).

    Returns ``[]`` when the model declares no relational databases.
    """
    from seed_data_generator.reference import iter_table_columns

    specs: List = []
    for db in model.rel_dbs:
        for table in db.tables:
            columns: List[str] = []
            column_types: List[str] = []
            seed_nums: List[int] = []
            col_index: dict[str, int] = {}
            # ``iter_table_columns`` yields each generated column with
            # its model entry; each entry's ``seed_num`` applies to all
            # columns it fans out into. One ``seed_num`` per yielded
            # column keeps ``max`` semantically correct.
            for idx, name, col, _group, base_type in iter_table_columns(table):
                columns.append(name)
                column_types.append(_to_jdbc_type(base_type))
                col_index[name] = idx
                seed_nums.append(col.seed_num)

            if not columns:
                continue

            total_rows = max(seed_nums) if seed_nums else 0
            if total_rows <= 0:
                continue
            batch_lines = _largest_divisor_le(total_rows, upper=100)
            rel_col_seed_files = [
                f"{col_index[name]}_{name}.csv" for name in columns
            ]
            specs.append({
                "table_name": f"{db.name}.{table.name}".lower(),
                "columns": columns,
                "total_rows": total_rows,
                "batch_lines": batch_lines,
                "rel_col_seed_files": rel_col_seed_files,
                "column_types": column_types,
            })
    return specs


# Map KaiwuDB / spec-normalised type names to JDBC ``Types`` strings
# that the KaiwuDB JDBC driver accepts as
# ``PreparedStatement.setNull(idx, typeCode-as-string)`` companion
# values. Without this translation the driver raises
# ``java.sql.SQLException: Invalid data type: int8`` (and analogous
# errors for other KaiwuDB short names). New types added to
# :func:`column_namer.normalize.normalize_type` should extend this map
# when they ever surface in a relational-table initialisation path.
_JDBC_TYPE_MAP = {
    "int8": "BIGINT",
    "int4": "INTEGER",
    "int2": "SMALLINT",
    "int1": "TINYINT",
    "float4": "REAL",
    "float8": "DOUBLE",
    "decimal": "DECIMAL",
    "numeric": "NUMERIC",
    "varchar": "VARCHAR",
    "char": "CHAR",
    "text": "LONGVARCHAR",
    "timestamp": "TIMESTAMP",
    "timestamptz": "TIMESTAMP_WITH_TIMEZONE",
    "bool": "BOOLEAN",
    "date": "DATE",
    "time": "TIME",
}


def _to_jdbc_type(normalised_name: str) -> str:
    """Translate KaiwuDB type name → JDBC ``Types`` string."""
    key = normalised_name.strip().lower()
    return _JDBC_TYPE_MAP.get(key, "VARCHAR")


def _largest_divisor_le(n: int, *, upper: int) -> int:
    """Largest integer 1 ≤ d ≤ ``upper`` that divides ``n`` evenly.

    Helper for relational-init batch sizing: spec §3.6 mandates
    ``total_rows % batch_lines == 0`` (no residual tail batch), and the
    cluster-side throughput is more honest when ``batch_lines`` is the
    largest viable divisor — fewer iterations, larger value tuples.
    Falls back to ``1`` when ``n`` is 1 (always divides).
    """
    if n <= 1:
        return 1
    cap = min(upper, n)
    for d in range(cap, 0, -1):
        if n % d == 0:
            return d
    return 1


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
    # col-tag-bind-write (2026-08-05): pass cfg so Orchestrator can honor
    # per-table ``col_tag_bind_mode`` and skip row-aggregate generation
    # for opt-in tables.
    seed_paths_map = generate_seeds(model, seeds_root, test_cfg=cfg)
    # Reshape seed_paths_map (db_name.table -> list[Path]) into
    # seed_csv_paths (db_name -> {table_name -> csv_path}) for the
    # skeleton. Each entry is the row-aggregate CSV (last path is the
    # aggregate; column seed files are written but not used by the
    # skeleton — shared-memory setup reads them directly).
    # col-tag-bind-write (2026-08-05): bind-mode tables have NO row
    # aggregate (Orchestrator skipped write_row_aggregate); the last
    # path in that list is a column seed file, not a row-aggregate.
    # Wiring ``paths[-1]`` to the row-aggregate loader would emit an
    # invalid ``csvPath=`` in SetupTG. Exclude bind-mode tables from
    # ``seed_csv_paths``; commit 3 wires them up via SetupTG bind sampler.
    seed_csv_paths: dict[str, dict[str, str]] = {}
    for fqn, paths in seed_paths_map.items():
        db_name, table_name = fqn.split(".", 1)
        if not paths:
            continue
        wc = cfg.find_write_config(db_name, table_name)
        if wc is not None and wc.col_tag_bind_mode:
            continue
        seed_csv_paths.setdefault(db_name, {})[table_name] = str(paths[-1])

    # DDL
    ddl_statements = DDLGenerator(model).generate_statements()

    # Relational-table initialisation specs (spec §3.6 关系表初始化采样器).
    # Each relational table needs a one-shot sampler that batch-inserts
    # rows from the per-column seed files. Previously the generator
    # skipped this stage, leaving sub_company / factory / workshop empty
    # after the test run (smoke regression on 2026-07-17).
    rel_init_specs = _build_relational_init_specs(model)

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
        rel_init_specs=rel_init_specs,
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
        # col-tag-bind-write (2026-08-05): per-table cross-reference
        # validation runs before _run_pipeline so failures short-circuit
        # seed generation (which would otherwise produce orphan column-seed
        # files for the rejected bind-mode table).
        _validate_col_tag_bind_constraints(model, cfg)
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
