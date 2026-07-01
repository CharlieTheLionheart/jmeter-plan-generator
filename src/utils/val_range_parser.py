"""Parse val_range expressions used by config-parser and seed-data-generator."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Optional


class ValRangeType(enum.Enum):
    UNBOUNDED = "unbounded"
    LOWER_BOUND = "lower_bound"       # ">N" (strict)
    LOWER_EQUAL_BOUND = "lower_equal_bound"  # ">=N"
    UPPER_BOUND = "upper_bound"       # "<N" (strict)
    UPPER_EQUAL_BOUND = "upper_equal_bound"  # "<=N"
    EQUAL = "equal"                   # "=N"
    INTERVAL = "interval"
    REGEX = "regex"
    ENUM = "enum"
    FOREIGN_KEY = "foreign_key"


@dataclass
class Interval:
    low: float
    high: float
    low_open: bool
    high_open: bool


@dataclass
class ValRange:
    range_type: ValRangeType
    raw: str
    interval: Optional[Interval] = None
    regex_pattern: Optional[str] = None
    enum_values: Optional[list[str]] = None
    foreign_key: Optional[str] = None


def _parse_interval(value: str) -> Interval:
    """Parse interval notation such as [1,100], (1,100), [1,100), (1,100]."""
    match = re.fullmatch(r"(\[|\()\s*([^,]+)\s*,\s*([^,]+)\s*(\]|\))", value)
    if not match:
        raise ValueError(f"invalid interval notation: {value}")
    left_bracket, low_str, high_str, right_bracket = match.groups()
    try:
        low = float(low_str.strip())
        high = float(high_str.strip())
    except ValueError as exc:
        raise ValueError(f"interval bounds must be numeric: {value}") from exc
    return Interval(
        low=low,
        high=high,
        low_open=(left_bracket == "("),
        high_open=(right_bracket == ")"),
    )


def _parse_enum(value: str) -> list[str]:
    """Parse enum:M1,M2,M3 into a list of values."""
    values = [v.strip() for v in value[5:].split(",")]
    if not values or all(v == "" for v in values):
        raise ValueError("enum must contain at least one value")
    allowed = re.compile(r"^[一-鿿a-zA-Z0-9-_]+$")
    for v in values:
        if not allowed.match(v):
            raise ValueError(f"enum value contains invalid characters: {v}")
    return values


def _validate_regex(pattern: str) -> str:
    """Validate regex pattern must be anchored with ^ at start and $ at end."""
    if not pattern.startswith("^") or not pattern.endswith("$"):
        raise ValueError(
            f"regex pattern must be anchored with ^ at start and $ at end, got: {pattern}"
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc
    return pattern


def _validate_foreign_key(origin_foreign_key_ref_str: str) -> str:
    """Validate ref:db.table.column format; preserves 'ref:' prefix for caller to split db_name.table_name."""
    ref = origin_foreign_key_ref_str[4:]
    to_check_parts = ref.split(".")
    if len(to_check_parts) != 3 or any(not p.strip() for p in to_check_parts):
        raise ValueError(f"foreign key must be ref:db.table.column, got {origin_foreign_key_ref_str}")
    return origin_foreign_key_ref_str  # return full value with "ref:" prefix preserved


def parse_val_range(raw: str) -> ValRange:
    """Parse a val_range string into a structured ValRange object."""
    value = raw.strip()
    if not value:
        raise ValueError("val_range must not be empty")

    if value.startswith("ref:"):
        return ValRange(
            range_type=ValRangeType.FOREIGN_KEY,
            raw=raw,
            foreign_key=_validate_foreign_key(value),
        )

    if value.startswith("enum:"):
        return ValRange(
            range_type=ValRangeType.ENUM,
            raw=raw,
            enum_values=_parse_enum(value),
        )

    if value.startswith(">="):
        try:
            bound = float(value[2:].strip())
        except ValueError as exc:
            raise ValueError(f"invalid lower bound: {value}") from exc
        return ValRange(
            range_type=ValRangeType.LOWER_EQUAL_BOUND,
            raw=raw,
            interval=Interval(low=bound, high=float("inf"), low_open=False, high_open=True),
        )

    if value.startswith("<="):
        try:
            bound = float(value[2:].strip())
        except ValueError as exc:
            raise ValueError(f"invalid upper bound: {value}") from exc
        return ValRange(
            range_type=ValRangeType.UPPER_EQUAL_BOUND,
            raw=raw,
            interval=Interval(low=float("-inf"), high=bound, low_open=True, high_open=False),
        )

    if value.startswith(">") and not value.startswith(">="):
        try:
            bound = float(value[1:].strip())
        except ValueError as exc:
            raise ValueError(f"invalid lower bound: {value}") from exc
        return ValRange(
            range_type=ValRangeType.LOWER_BOUND,
            raw=raw,
            interval=Interval(low=bound, high=float("inf"), low_open=True, high_open=True),
        )

    if value.startswith("<") and not value.startswith("<="):
        try:
            bound = float(value[1:].strip())
        except ValueError as exc:
            raise ValueError(f"invalid upper bound: {value}") from exc
        return ValRange(
            range_type=ValRangeType.UPPER_BOUND,
            raw=raw,
            interval=Interval(low=float("-inf"), high=bound, low_open=True, high_open=True),
        )

    if value.startswith("="):
        try:
            bound = float(value[1:].strip())
        except ValueError as exc:
            raise ValueError(f"invalid equal bound: {value}") from exc
        return ValRange(
            range_type=ValRangeType.EQUAL,
            raw=raw,
            interval=Interval(low=bound, high=bound, low_open=False, high_open=False),
        )

    if value.startswith("[") or value.startswith("("):
        interval = _parse_interval(value)
        return ValRange(
            range_type=ValRangeType.INTERVAL,
            raw=raw,
            interval=interval,
        )

    # Treat remaining values as regex patterns (common for string types).
    return ValRange(
        range_type=ValRangeType.REGEX,
        raw=raw,
        regex_pattern=_validate_regex(value),
    )


__all__ = [
    "ValRangeType",
    "Interval",
    "ValRange",
    "parse_val_range",
]
