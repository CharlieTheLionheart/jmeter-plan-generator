"""Strategy registry mapping write modes to concrete :class:`WriteStrategy` classes.

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

Public surface
--------------

- :data:`STRATEGY_REGISTRY` — mode string → strategy class. Built-in
  entries are populated on import. New strategies can be added via
  :func:`register_strategy`.
- :func:`get_strategy` — instantiate the strategy for a given mode.
  Raises :class:`WriteStrategyError` (a ``ValueError`` subclass) when
  the mode is unknown — see ``review.md`` Boundary §1 “策略注册表未知
  mode 防御行为” and the agreed defence policy.
"""

from __future__ import annotations

from typing import Dict, List, Type

from write_strategies.base import WriteStrategy, WriteStrategyError


# Built-in strategies. Importing them here would create a circular
# dependency between ``single_insert_strategy`` and this module, so we
# populate the registry inside ``bootstrap`` (called from
# :mod:`write_strategies.__init__`).
STRATEGY_REGISTRY: Dict[str, Type[WriteStrategy]] = {}


class UnknownWriteModeError(WriteStrategyError, ValueError):
    """Raised when :func:`get_strategy` receives a mode not in the registry."""

    def __init__(self, mode: str, supported: List[str]) -> None:
        self.mode = mode
        self.supported = supported
        super().__init__(
            f"unknown write mode {mode!r}; supported modes: {supported}"
        )


def register_strategy(mode: str, strategy_cls: Type[WriteStrategy]) -> None:
    """Add (or replace) a strategy class for ``mode`` in :data:`STRATEGY_REGISTRY`.

    Strategies normally register themselves by importing this module and
    calling :func:`bootstrap` from :mod:`write_strategies.__init__`.
    Tests and third-party plugins may register custom strategies at
    runtime — the same dictionary backs production lookups.
    """
    if not isinstance(mode, str) or not mode:
        raise WriteStrategyError("mode must be a non-empty string")
    if not isinstance(strategy_cls, type) or not issubclass(strategy_cls, WriteStrategy):
        raise WriteStrategyError(
            f"strategy_cls must subclass WriteStrategy, got {strategy_cls!r}"
        )
    STRATEGY_REGISTRY[mode] = strategy_cls


def bootstrap() -> None:
    """Populate :data:`STRATEGY_REGISTRY` with the built-in strategies.

    Called once from :mod:`write_strategies.__init__`. Idempotent — each
    built-in ``register`` call overwrites any existing entry under the
    same mode.
    """
    # Local imports to break the package-cycle.
    from write_strategies.batch_insert_strategy import BatchInsertStrategy
    from write_strategies.batch_prepared_strategy import BatchPreparedStatementStrategy
    from write_strategies.schemaless_strategy import SchemalessWriteStrategy
    from write_strategies.single_insert_strategy import SingleInsertStrategy
    from write_strategies.single_prepared_strategy import SinglePreparedStatementStrategy

    register_strategy("single_insert", SingleInsertStrategy)
    register_strategy("batch_insert", BatchInsertStrategy)
    register_strategy("single_prepared", SinglePreparedStatementStrategy)
    register_strategy("batch_prepared", BatchPreparedStatementStrategy)
    # NOTE: `schemaless` 是 dead-code 注册（d461e40 后实际生成器走 skeleton.py REST
    # 分支，不再调用此 strategy）。保留仅为防御未来回退 strategy 架构时 KeyError。
    # 详见 schemaless_strategy.py module docstring + docs/specs §7。
    register_strategy("schemaless", SchemalessWriteStrategy)


def get_strategy(mode: str) -> WriteStrategy:
    """Return a fresh strategy instance for ``mode``.

    Raises
    ------
    UnknownWriteModeError
        When ``mode`` is not in :data:`STRATEGY_REGISTRY`. The error
        message lists every supported mode to aid config debugging.
    """
    if not isinstance(mode, str):
        raise UnknownWriteModeError(str(mode), sorted(STRATEGY_REGISTRY.keys()))
    strategy_cls = STRATEGY_REGISTRY.get(mode)
    if strategy_cls is None:
        raise UnknownWriteModeError(mode, sorted(STRATEGY_REGISTRY.keys()))
    return strategy_cls()


def supported_modes() -> List[str]:
    """Return the sorted list of currently registered write modes."""
    return sorted(STRATEGY_REGISTRY.keys())
