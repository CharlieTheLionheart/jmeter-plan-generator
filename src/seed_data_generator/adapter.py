"""Adapt ``utils.val_range_parser`` output into a generator-friendly domain."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from utils.val_range_parser import ValRangeType, parse_val_range


class DomainKind(Enum):
    """Kind of value domain described by a ``val_range`` string."""

    NUMERIC = auto()
    ENUM = auto()
    REGEX = auto()
    FOREIGN_KEY = auto()


@dataclass(frozen=True)
class ValueDomain:
    """Normalized description of the values a column may take."""

    kind: DomainKind
    is_integer: Optional[bool] = None
    low: Optional[float] = None
    high: Optional[float] = None
    low_inclusive: Optional[bool] = None
    high_inclusive: Optional[bool] = None
    precision: Optional[int] = None
    enum_values: Optional[list[str]] = None
    regex_pattern: Optional[str] = None
    foreign_key: Optional[str] = None


_INTEGER_TYPES = frozenset(
    {"int8", "int4", "int2", "int", "bigint", "smallint", "tinyint"}
)
_FLOAT_TYPES = frozenset(
    {"float", "float4", "float8", "double", "decimal", "numeric"}
)


class SeedGenError(Exception):
    """Raised when seed generation cannot proceed."""


def _base_type(col_type: str) -> str:
    return col_type.strip().lower().split("(")[0].split("[")[0].strip()


def _is_numeric_type(col_type: str) -> bool:
    base = _base_type(col_type)
    return base in _INTEGER_TYPES or base in _FLOAT_TYPES


def _adjust_integer_bounds(
    low: float,
    high: float,
    low_inclusive: bool,
    high_inclusive: bool,
) -> tuple[float, float]:
    """Convert interval bounds to inclusive integer bounds (keeps infinity)."""
    if math.isinf(low):
        effective_low = low
    elif low_inclusive:
        effective_low = math.ceil(low)
    else:
        effective_low = math.floor(low) + 1

    if math.isinf(high):
        effective_high = high
    elif high_inclusive:
        effective_high = math.floor(high)
    else:
        effective_high = math.ceil(high) - 1

    return effective_low, effective_high


def classify_val_range(col_type: str, val_range: Optional[str]) -> ValueDomain:
    """Classify a column's ``val_range`` into a ``ValueDomain``.

    Raises:
        SeedGenError: When the ``val_range`` is unsupported for the column type
            or cannot be parsed.
    """
    if not val_range:
        raise SeedGenError(f"val_range is required for column type {col_type}")

    parsed = parse_val_range(val_range)

    if parsed.range_type is ValRangeType.FOREIGN_KEY:
        return ValueDomain(
            kind=DomainKind.FOREIGN_KEY,
            foreign_key=parsed.foreign_key,
        )

    if parsed.range_type is ValRangeType.ENUM:
        return ValueDomain(
            kind=DomainKind.ENUM,
            enum_values=list(parsed.enum_values) if parsed.enum_values else [],
        )

    if parsed.range_type is ValRangeType.REGEX:
        if _is_numeric_type(col_type):
            raise SeedGenError(
                f"regex val_range is not supported for numeric type {col_type}"
            )
        return ValueDomain(
            kind=DomainKind.REGEX,
            regex_pattern=parsed.regex_pattern,
        )

    # Numeric interval / bound.
    if not _is_numeric_type(col_type):
        raise SeedGenError(
            f"numeric val_range is not supported for non-numeric type {col_type}"
        )

    interval = parsed.interval
    if interval is None:
        raise SeedGenError(f"numeric val_range {val_range!r} has no interval")

    base = _base_type(col_type)
    is_integer = base in _INTEGER_TYPES
    precision = None if is_integer else 2

    low_inc = not interval.low_open
    high_inc = not interval.high_open
    low, high = interval.low, interval.high

    if is_integer:
        low, high = _adjust_integer_bounds(low, high, low_inc, high_inc)
        low_inc = True
        high_inc = True

    return ValueDomain(
        kind=DomainKind.NUMERIC,
        is_integer=is_integer,
        low=low,
        high=high,
        low_inclusive=low_inc,
        high_inclusive=high_inc,
        precision=precision,
    )
