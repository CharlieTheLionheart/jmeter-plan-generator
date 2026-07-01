"""Column group prefix mappings."""

from __future__ import annotations

GROUP_PREFIXES: dict[str, str] = {
    "data_cols": "col",
    "primary_tags": "ptag",
    "regular_tags": "rtag",
    "primary_keys": "pk",
}


def prefix_for_group(group: str) -> str:
    """Return the prefix for a known column group."""
    if group not in GROUP_PREFIXES:
        raise ValueError(f"unknown column group: {group}")
    return GROUP_PREFIXES[group]
