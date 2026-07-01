"""Column count allocation using floor + greedy algorithm."""

from __future__ import annotations

import math


def allocate_columns(total: int, proportions: list[float]) -> list[int]:
    """Allocate `total` columns across types according to `proportions`.

    Uses floor allocation first, then greedily distributes the remainder to
    the largest fractional parts.
    """
    if total <= 0 or not proportions:
        return []

    if any(p < 0 for p in proportions):
        raise ValueError("proportions must not be negative")

    if abs(sum(proportions) - 1.0) > 1e-6:
        raise ValueError("proportions must sum to 1.0")

    # Handle edge case where total is less than number of proportions.
    raw = [total * p for p in proportions]
    base = [math.floor(r) for r in raw]
    remainder = total - sum(base)

    if remainder > 0:
        # Greedily give one extra to the indices with the largest fractional parts.
        fractions = [(i, raw[i] - base[i]) for i in range(len(proportions))]
        fractions.sort(key=lambda x: x[1], reverse=True)
        for i, _ in fractions[:remainder]:
            base[i] += 1

    return base
