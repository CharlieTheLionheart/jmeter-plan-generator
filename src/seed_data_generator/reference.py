"""Foreign-key reference discovery, pre-generation, and sampling."""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from column_namer import allocate_columns, generate_column_names, normalize_type
from config_parser.models import (
    ColTypeConfig,
    DatabaseConfig,
    PrimaryTagColTypeConfig,
    TableConfig,
    TestModelConfig,
)
from seed_data_generator.adapter import SeedGenError
from seed_data_generator.generators import generate_column_values
from seed_data_generator.io import read_column_seed, write_column_seed


# Order must match ``column_namer.namer.ColumnNamer.GROUP_ORDER``.
_GROUP_ORDER = ["primary_keys", "data_cols", "primary_tags", "regular_tags"]
_COUNT_FIELDS = {
    "primary_keys": "primary_key_count",
    "data_cols": "data_col_count",
    "primary_tags": "primary_tag_count",
    "regular_tags": "regular_tag_count",
}


def _all_columns(
    table: TableConfig,
) -> Iterable[tuple[str, Any]]:
    """Yield (group_name, column_config) for every column in a table."""
    for group in _GROUP_ORDER:
        cols = getattr(table, group, [])
        for col in cols:
            yield group, col


def iter_table_columns(
    table: TableConfig,
) -> Iterable[tuple[int, str, Any, str, str]]:
    """Yield (index, name, col_config, group, base_type) in emission order.

    The emission order matches ``column_namer.ColumnNamer`` so the
    downstream seed-file naming and the rel-table initialisation sampler
    SQL are aligned. Per-type name counters are shared across model
    entries with the same group+type, mirroring ColumnNamer's
    ``type_counters`` so two entries of the same ``(group, col_type)``
    yield ``col_varchar_1`` and ``col_varchar_2`` instead of two
    duplicate names (regression on 2026-07-17).
    """
    from column_namer.generate import generate_column_names as _g
    from column_namer.normalize import normalize_type as _norm

    index = 1
    type_counters: dict[tuple[str, str], int] = {}
    for group in _GROUP_ORDER:
        cols = getattr(table, group, [])
        if not cols:
            continue
        total = getattr(table, _COUNT_FIELDS[group])
        if total <= 0:
            continue
        proportions = [c.type_proportion for c in cols]
        counts = allocate_columns(total, proportions)
        for col, count in zip(cols, counts):
            if count <= 0:
                continue
            base_type = _norm(col.col_type)
            key = (group, base_type)
            start = type_counters.get(key, 1)
            for name in _g(group, col.col_type, count, start=start):
                yield index, name, col, group, base_type
                index += 1
            type_counters[key] = start + count


def build_column_registry(
    model: TestModelConfig,
) -> dict[str, tuple[DatabaseConfig, TableConfig, Any, int, str, str]]:
    """Map ``db.table.column_name`` to (db, table, col, index, group, base_type)."""
    registry: dict[str, tuple[DatabaseConfig, TableConfig, Any, int, str, str]] = {}
    for db in model.rel_dbs + model.ts_dbs:
        for table in db.tables:
            for index, name, col, group, base_type in iter_table_columns(table):
                key = f"{db.name}.{table.name}.{name}"
                registry[key] = (db, table, col, index, group, base_type)
    return registry


def discover_references(
    model: TestModelConfig,
) -> dict[str, list[tuple[DatabaseConfig, TableConfig, Any, int, str]]]:
    """Return mapping ``ref_target`` -> list of referencing columns."""
    refs: dict[str, list[tuple[DatabaseConfig, TableConfig, Any, int, str]]] = defaultdict(list)
    for db in model.rel_dbs + model.ts_dbs:
        for table in db.tables:
            for index, name, col, group, base_type in iter_table_columns(table):
                if col.val_range and col.val_range.startswith("ref:"):
                    target = col.val_range[4:]
                    refs[target].append((db, table, col, index, base_type))
    return dict(refs)


def _column_seed_path(
    table_dir: Path,
    index: int,
    name: str,
) -> Path:
    return table_dir / f"{index}_{name}.csv"


def _generate_target_values(
    db: DatabaseConfig,
    table: TableConfig,
    col: Any,
    base_type: str,
) -> list[Any]:
    """Generate seed values for a referenced target column."""
    if col.val_range and col.val_range.startswith("ref:"):
        raise SeedGenError(
            f"reference target {db.name}.{table.name}.{col.col_type} "
            "cannot itself have a ref val_range"
        )

    from seed_data_generator.adapter import classify_val_range

    domain = classify_val_range(col.col_type, col.val_range)
    return generate_column_values(
        domain,
        col.seed_num if isinstance(col, ColTypeConfig) else table.primary_key_count,
        getattr(col, "nullable", False),
        getattr(col, "null_rate", 0.0),
    )


def pregenerate_reference_columns(
    model: TestModelConfig,
    output_dir: Path,
    registry: dict[str, tuple[DatabaseConfig, TableConfig, Any, int, str, str]],
    refs: dict[str, list[tuple[DatabaseConfig, TableConfig, Any, int, str]]],
) -> dict[str, Path]:
    """Write ``.csv`` seed files for every referenced column and return target->path.

    外键关系生成（T1）落地于 commit ``8614b90``（R-3 续 FK 约束 +
    workshop 100 行）；主 spec §7 历史排期跟踪。shig fixture 3 层 FK，
    FK 23503 验证 / 0 orphans。
    """
    ref_paths: dict[str, Path] = {}
    for target in refs:
        entry = registry.get(target)
        if entry is None:
            raise SeedGenError(f"reference target not found: {target}")
        db, table, col, index, group, base_type = entry
        table_dir = output_dir / db.name / table.name
        ref_path = _column_seed_path(table_dir, index, target.split(".")[-1])
        values = _generate_target_values(db, table, col, base_type)
        write_column_seed(ref_path, values)
        ref_paths[target] = ref_path
    return ref_paths


def sample_reference_values(ref_path: Path, seed_num: int) -> list[str]:
    """Sample ``seed_num`` values from a ``.csv`` seed file uniformly with replacement."""
    if not ref_path.exists():
        raise SeedGenError(f"reference seed file not found: {ref_path}")

    values = read_column_seed(ref_path)
    if not values:
        raise SeedGenError(f"reference seed file is empty: {ref_path}")

    return [random.choice(values) for _ in range(seed_num)]


def is_reference_target(
    name: str,
    refs: dict[str, list[Any]],
) -> bool:
    """Return True if ``name`` is referenced by another column."""
    return name in refs
