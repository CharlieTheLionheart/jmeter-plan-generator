"""Table-level column name generator used by the DDL generator."""

from __future__ import annotations

from column_namer import generate_column_names
from column_namer.normalize import normalize_type
from config_parser.models import TableConfig


class ColumnNameGenerator:
    """Generate column names for a table using ``{prefix}_{type}_{sequence}``."""

    def __init__(self, table_config: TableConfig):
        self.table_config = table_config
        self._counters: dict[tuple[str, str], int] = {}

    def generate(self, group: str, col_type: str, count: int) -> list[str]:
        """Generate ``count`` column names for ``group`` and ``col_type``.

        Sequence numbers are tracked independently per ``(group, normalized type)``
        so repeated calls for the same group and type continue numbering.
        """
        if count <= 0:
            return []

        key = (group, normalize_type(col_type))
        start = self._counters.get(key, 1)
        names = generate_column_names(group, col_type, count, start=start)
        self._counters[key] = start + count
        return names

    def generate_primary_keys(self, col_type: str, count: int) -> list[str]:
        return self.generate("primary_keys", col_type, count)

    def generate_data_cols(self, col_type: str, count: int) -> list[str]:
        return self.generate("data_cols", col_type, count)

    def generate_primary_tags(self, col_type: str, count: int) -> list[str]:
        return self.generate("primary_tags", col_type, count)

    def generate_regular_tags(self, col_type: str, count: int) -> list[str]:
        return self.generate("regular_tags", col_type, count)
