"""Generate column names from group, type, and count."""

from __future__ import annotations

from column_namer.constants import prefix_for_group
from column_namer.normalize import normalize_type


def generate_column_names(
    group: str,
    col_type: str,
    count: int,
    *,
    start: int = 1,
) -> list[str]:
    """Generate `count` column names for `group` with type `col_type`.

    Names follow the pattern `{prefix}_{normalized_type}_{sequence}` where
    sequence starts at `start`.
    """
    if count <= 0:
        return []

    prefix = prefix_for_group(group)
    base_type = normalize_type(col_type)
    return [f"{prefix}_{base_type}_{i}" for i in range(start, start + count)]
