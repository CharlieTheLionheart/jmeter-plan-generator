"""Table-level column naming entry point."""

from __future__ import annotations

from config_parser.models import TableConfig
from column_namer.allocate import allocate_columns
from column_namer.generate import generate_column_names
from column_namer.normalize import normalize_type


class ColumnNamer:
    """Generate column names and index mapping for a table."""

    # Order in which column groups are emitted.
    GROUP_ORDER = ["primary_keys", "data_cols", "primary_tags", "regular_tags"]

    _COUNT_FIELDS: dict[str, str] = {
        "primary_keys": "primary_key_count",
        "data_cols": "data_col_count",
        "primary_tags": "primary_tag_count",
        "regular_tags": "regular_tag_count",
    }

    def __init__(self, table_config: TableConfig):
        self.table_config = table_config
        self._names: list[str] = []
        self._types: list[str] = []
        self._index_map: dict[str, int] = {}
        self._build()

    def _build(self) -> None:
        """Build names, per-name types, and index mapping."""
        index = 1
        type_counters: dict[tuple[str, str], int] = {}

        for group in self.GROUP_ORDER:
            cols = getattr(self.table_config, group, [])
            if not cols:
                continue

            count_field = self._COUNT_FIELDS[group]
            total = getattr(self.table_config, count_field)
            proportions = [c.type_proportion for c in cols]
            counts = allocate_columns(total, proportions)

            for col, count in zip(cols, counts):
                if count <= 0:
                    continue
                base_type = normalize_type(col.col_type)
                key = (group, base_type)
                start = type_counters.get(key, 1)
                names = generate_column_names(group, col.col_type, count, start=start)
                type_counters[key] = start + count

                for name in names:
                    self._names.append(name)
                    # Per-name type shares the entry's col_type (already
                    # normalised). When allocating N columns from a single
                    # entry, every produced name inherits the same JDBC
                    # type — fix for the N-aligned column_types bug
                    # surfaced by shig smoke on 2026-07-17.
                    self._types.append(base_type)
                    self._index_map[name] = index
                    index += 1

    @property
    def names(self) -> list[str]:
        """Return the ordered list of generated column names."""
        return list(self._names)

    @property
    def types_per_name(self) -> list[str]:
        """Return per-name JDBC type list (parallel to :attr:`names`).

        Length always equals ``len(names)``; element ``i`` is the JDBC type
        (lowercased, normalised) for column ``names[i]``. Useful when
        downstream code needs per-column type metadata — e.g. building a
        N-element ``column_types`` UDV to feed into the batch_prepared
        sampler parameter binder.
        """
        return list(self._types)

    @property
    def index_map(self) -> dict[str, int]:
        """Return mapping from column name to 1-based global index."""
        return dict(self._index_map)

    def __call__(self) -> tuple[list[str], list[str], dict[str, int]]:
        """Return (names, types_per_name, index_map)."""
        return self.names, self.types_per_name, self.index_map
