"""End-to-end seed generation orchestrator."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Optional

from config_parser.models import (
    DatabaseConfig,
    TableConfig,
    TestConfig,
    TestModelConfig,
)
from seed_data_generator.adapter import SeedGenError, classify_val_range
from seed_data_generator.generators import generate_column_values
from seed_data_generator.io import (
    build_row_aggregate,
    cleanup_table_seeds,
    discover_column_files,
    read_column_seed,
    write_column_seed,
    write_row_aggregate,
)
from seed_data_generator.reference import (
    build_column_registry,
    discover_references,
    is_reference_target,
    iter_table_columns,
    pregenerate_reference_columns,
    sample_reference_values,
)


logger = logging.getLogger(__name__)


def _config_hash(model: TestModelConfig) -> str:
    """Return a stable hash of the input config for traceability."""
    return hashlib.sha256(model.model_dump_json().encode("utf-8")).hexdigest()[:16]


def _generate_table_seeds(
    db: DatabaseConfig,
    table: TableConfig,
    output_dir: Path,
    refs: dict[str, list[Any]],
    ref_paths: dict[str, Path],
    *,
    skip_row_aggregate: bool = False,
) -> list[Path]:
    """Generate column seed files and the row aggregate for one table.

    col-tag-bind-write (2026-08-05): when ``skip_row_aggregate=True``, the
    row-aggregate CSV (``{db}/{table}.csv``) is NOT produced. Column seed
    files are still written regardless, because the SetupTG bind sampler
    reads them directly to initialize per-group row memory.
    """
    table_dir = output_dir / db.name / table.name
    generated: list[Path] = []

    # Track whether we have seen the first ptag yet; first ptag has no seed file
    first_ptag_seen = False
    first_ptag_info: tuple[int, str] | None = None  # (index, name)

    # Pre-compute the row-aggregate length (= max seed_num across all
    # columns) so PK columns can be auto-expanded to a unique
    # 1..N series. Without this, a PK with val_range "=1" and
    # seed_num 1 produces one value ("1"); the row aggregate then
    # cyclic-fills and every row gets PK=1 → duplicate key on insert.
    max_seed = 0
    for _, _, c, _, _ in iter_table_columns(table):
        max_seed = max(max_seed, c.seed_num)
    if max_seed <= 0:
        max_seed = 1

    for index, name, col, group, base_type in iter_table_columns(table):
        target_key = f"{db.name}.{table.name}.{name}"
        ref_path = ref_paths.get(target_key)

        # Detect first ptag column (skip seed file generation for it)
        is_first_ptag = (
            not first_ptag_seen
            and group == "primary_tags"
        )
        if is_first_ptag:
            first_ptag_seen = True
            first_ptag_info = (index, name)
            # Do NOT write a column seed file for first ptag
            # PreProcessor will inject ${device_code} at runtime
            continue

        # PK columns must be unique across the row aggregate. Override
        # any constant/short seed (e.g. val_range "=1", seed_num 1) with
        # a 1..max_seed series so cyclic-fill in build_row_aggregate
        # produces one distinct PK per row.
        if group == "primary_keys":
            values = [str(i) for i in range(1, max_seed + 1)]
            col_path = table_dir / f"{index}_{name}.csv"
            write_column_seed(col_path, values)
            generated.append(col_path)
            continue

        if col.val_range and col.val_range.startswith("ref:"):
            # Dependent column: sample from referenced primary key seed file.
            source_key = col.val_range[4:]
            source_path = ref_paths.get(source_key)
            if source_path is None:
                raise SeedGenError(
                    f"missing reference seed file for {source_key} "
                    f"(referenced by {db.name}.{table.name}.{name})"
                )
            values = sample_reference_values(source_path, col.seed_num)
            col_path = table_dir / f"{index}_{name}.csv"
        elif ref_path is not None:
            # This column is referenced by others; reuse the pre-generated values.
            values = read_column_seed(ref_path)
            col_path = table_dir / f"{index}_{name}.csv"
        else:
            domain = classify_val_range(col.col_type, col.val_range)
            values = generate_column_values(
                domain,
                col.seed_num,
                getattr(col, "nullable", False),
                getattr(col, "null_rate", 0.0),
            )
            col_path = table_dir / f"{index}_{name}.csv"

        write_column_seed(col_path, values)
        generated.append(col_path)

    # Build row aggregate, injecting first ptag as virtual column if present.
    # col-tag-bind-write (2026-08-05): skipped when ``skip_row_aggregate=True``
    # because the SetupTG bind sampler reads column seeds directly.
    if not skip_row_aggregate:
        header, rows = build_row_aggregate(table_dir, first_ptag_info=first_ptag_info)
        aggregate_path = output_dir / db.name / f"{table.name}.csv"
        write_row_aggregate(aggregate_path, header, rows)
        generated.append(aggregate_path)
    return generated


def generate_seeds(
    model: TestModelConfig,
    output_dir: str | Path,
    *,
    seed: Optional[int] = None,
    test_cfg: Optional[TestConfig] = None,
) -> dict[str, list[Path]]:
    """Generate column seed files and row aggregates for every table in ``model``.

    Args:
        model: Parsed test model configuration.
        output_dir: Directory where ``seeds/`` subtree will be written.
        seed: Optional random seed for reproducible generation.
        test_cfg: col-tag-bind-write (2026-08-05): when provided, per-table
            ``WriteConfig.col_tag_bind_mode`` is consulted and the row aggregate
            is skipped for tables that opt into column-tag binding. Backward
            compatible: passing ``None`` preserves the prior full-row behavior
            for every table.

    Returns:
        Mapping from ``db_name.table_name`` to the list of generated paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if seed is not None:
        import random

        random.seed(seed)

    registry = build_column_registry(model)
    refs = discover_references(model)
    ref_paths = pregenerate_reference_columns(model, output_dir, registry, refs)

    config_hash = _config_hash(model)
    logger.info("seed generation started: config_hash=%s output_dir=%s", config_hash, output_dir)

    results: dict[str, list[Path]] = {}
    all_files: list[Path] = []
    for db in model.rel_dbs + model.ts_dbs:
        for table in db.tables:
            wc = test_cfg.find_write_config(db.name, table.name) if test_cfg else None
            skip = bool(wc and wc.col_tag_bind_mode)
            files = _generate_table_seeds(
                db, table, output_dir, refs, ref_paths, skip_row_aggregate=skip
            )
            results[f"{db.name}.{table.name}"] = files
            all_files.extend(files)

    logger.info(
        "seed generation complete: config_hash=%s files=%d",
        config_hash,
        len(all_files),
    )
    return results


def cleanup_table(output_dir: str | Path, db_name: str, table_name: str) -> None:
    """Remove generated seed files for a single table."""
    cleanup_table_seeds(Path(output_dir), db_name, table_name)
