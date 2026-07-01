"""Normalize column type names for use in column names."""

from __future__ import annotations

import re


def normalize_type(col_type: str) -> str:
    """Strip length/precision modifiers and array suffix from a column type.

    Examples:
        varchar(16)    -> varchar
        decimal(10,2)  -> decimal
        int8           -> int8
        float[]        -> float
    """
    normalized = col_type.strip().lower()
    # Remove array suffix.
    normalized = re.sub(r"\[\s*\]+$", "", normalized)
    # Remove size/precision/scale modifiers.
    normalized = re.sub(r"\s*\(.*\)$", "", normalized)
    return normalized.strip()
