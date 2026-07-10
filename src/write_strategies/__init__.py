"""Write-strategy pattern: pluggable SQL / sampler / preprocessor rendering per write mode.

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

Public surface
--------------

- :class:`WriteStrategy` — abstract base class (:mod:`write_strategies.base`).
- :class:`WriteStrategyError` — domain exception raised by strategies
  or the registry.
- :data:`STRATEGY_REGISTRY` — mode → strategy class
  (:mod:`write_strategies.registry`).
- :func:`get_strategy` — instantiate the strategy for a write mode.
- :func:`supported_modes` — list of currently registered modes.

Usage::

    from write_strategies import get_strategy
    from write_strategies.models import ResolvedTable, WriteRuntime

    strategy = get_strategy("single_insert")
    table = ResolvedTable(fqn="iot_monitor.t", columns=["ts", "c1"])
    sql = strategy.generate_query(table)

Importing this package populates :data:`STRATEGY_REGISTRY` with the
built-in modes. New modes can be added at runtime via
:func:`register_strategy`.
"""

from write_strategies.base import WriteStrategy, WriteStrategyError
from write_strategies.models import ResolvedTable, WriteRuntime
from write_strategies.registry import (
    STRATEGY_REGISTRY,
    bootstrap,
    get_strategy,
    register_strategy,
    supported_modes,
)

# Populate the registry with the built-in strategies.
bootstrap()

__all__ = [
    "WriteStrategy",
    "WriteStrategyError",
    "ResolvedTable",
    "WriteRuntime",
    "STRATEGY_REGISTRY",
    "get_strategy",
    "register_strategy",
    "supported_modes",
]
