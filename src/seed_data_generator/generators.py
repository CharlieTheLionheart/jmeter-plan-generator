"""Value generators for numeric, string, enum, and NULL values."""

from __future__ import annotations

import itertools
import math
import random
from typing import Any, Optional

from seed_data_generator.adapter import DomainKind, SeedGenError, ValueDomain


def _null_count(seed_num: int, nullable: bool, null_rate: float) -> int:
    """Return the number of NULLs to inject."""
    if not nullable or null_rate <= 0.0:
        return 0
    return min(seed_num, math.floor(null_rate * seed_num))


def _bound_numeric_domain(domain: ValueDomain, count: int) -> tuple[float, float]:
    """Replace infinite bounds with a finite window sized from ``count``."""
    low = domain.low if domain.low is not None else 0.0
    high = domain.high if domain.high is not None else 0.0

    if math.isinf(low) and math.isinf(high):
        return 0.0, float(count * 2)
    if math.isinf(low):
        assert not math.isinf(high)
        return high - float(count * 2), high
    if math.isinf(high):
        return low, low + float(count * 2)
    return low, high


def _generate_integers(domain: ValueDomain, count: int) -> list[int]:
    low, high = _bound_numeric_domain(domain, count)
    low_i, high_i = int(math.ceil(low)), int(math.floor(high))
    if low_i > high_i:
        raise SeedGenError(
            f"integer domain [{low}, {high}] contains no valid integer"
        )
    return [random.randint(low_i, high_i) for _ in range(count)]


def _generate_floats(domain: ValueDomain, count: int) -> list[float]:
    low, high = _bound_numeric_domain(domain, count)
    precision = domain.precision if domain.precision is not None else 2
    if low > high:
        raise SeedGenError(
            f"float domain [{low}, {high}] contains no valid value"
        )
    values: list[float] = []
    for _ in range(count):
        value = round(random.uniform(low, high), precision)
        # Keep open bounds from rounding errors.
        if domain.low is not None and not domain.low_inclusive and value <= domain.low:
            value = round(domain.low + 10 ** (-precision), precision)
        if domain.high is not None and not domain.high_inclusive and value >= domain.high:
            value = round(domain.high - 10 ** (-precision), precision)
        values.append(value)
    return values


def _generate_enum(domain: ValueDomain, count: int) -> list[str]:
    values = domain.enum_values or []
    if not values:
        raise SeedGenError("enum domain has no values")
    cycle = itertools.cycle(values)
    return [next(cycle) for _ in range(count)]


def _generate_regex(domain: ValueDomain, count: int) -> list[str]:
    import rstr

    pattern = domain.regex_pattern or ""
    try:
        return [rstr.xeger(pattern) for _ in range(count)]
    except Exception as exc:
        raise SeedGenError(f"regex generation failed for {pattern!r}: {exc}") from exc


def _generate_non_null_values(domain: ValueDomain, count: int) -> list[Any]:
    """Generate ``count`` non-NULL values matching ``domain``."""
    if count <= 0:
        return []

    if domain.kind is DomainKind.ENUM:
        return _generate_enum(domain, count)
    if domain.kind is DomainKind.REGEX:
        return _generate_regex(domain, count)
    if domain.kind is DomainKind.NUMERIC:
        if domain.is_integer:
            return _generate_integers(domain, count)
        return _generate_floats(domain, count)

    raise SeedGenError(f"cannot generate values for domain kind {domain.kind}")


def generate_column_values(
    domain: ValueDomain,
    seed_num: int,
    nullable: bool,
    null_rate: float,
) -> list[Any]:
    """Generate ``seed_num`` values, injecting NULLs when configured."""
    if seed_num <= 0:
        raise SeedGenError(f"seed_num must be positive, got {seed_num}")
    if null_rate < 0.0 or null_rate > 1.0:
        raise SeedGenError(f"null_rate must be in [0, 1], got {null_rate}")

    null_count = _null_count(seed_num, nullable, null_rate)
    non_null_count = seed_num - null_count

    values = _generate_non_null_values(domain, non_null_count)
    if null_count:
        values.extend([None] * null_count)
        random.shuffle(values)
    return values
