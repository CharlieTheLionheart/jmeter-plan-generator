"""Registry-lookup performance benchmark.

Closes review.md §3 "测试覆盖" gap:
- ``get_strategy(mode)`` is the dispatch hot path used by every
  ``write_groups`` call. A 50 ms ceiling on 1 000 lookups keeps the
  registry lookup an O(1) dict access in practice.

Hand-rolled ``time.perf_counter`` (no pytest-benchmark dep) — the metric
is a ceiling, not a distribution.
"""

from __future__ import annotations

import time

from write_strategies.registry import (
    STRATEGY_REGISTRY,
    bootstrap,
    get_strategy,
    supported_modes,
)


class TestRegistryPerformance:
    def test_get_strategy_1000_lookups_under_50ms(self):
        modes = list(STRATEGY_REGISTRY.keys())
        assert modes, "registry empty — bootstrap() did not run"
        start = time.perf_counter()
        for _ in range(1000):
            get_strategy(modes[0])
        elapsed = time.perf_counter() - start
        assert elapsed < 0.050, (
            f"1000 get_strategy() lookups took {elapsed*1000:.1f} ms (cap 50 ms)"
        )

    def test_bootstrap_idempotent(self):
        bootstrap()
        size_before = len(STRATEGY_REGISTRY)
        bootstrap()
        size_after = len(STRATEGY_REGISTRY)
        assert size_before == size_after
        assert size_after == 5

    def test_supported_modes_returns_five_entries(self):
        modes = supported_modes()
        assert len(modes) == 5
        assert set(modes) >= {
            "single_insert",
            "batch_insert",
            "single_prepared",
            "batch_prepared",
            "schemaless",
        }
