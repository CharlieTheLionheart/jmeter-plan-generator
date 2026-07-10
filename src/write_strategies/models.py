"""Shared value objects for write strategies.

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

Two frozen dataclasses split the inputs every strategy consumes:

- :class:`ResolvedTable` — the *structural* view of one table (qualified
  name, ordered columns, raw build-order metadata). Stable across a run.
- :class:`WriteRuntime` — the *runtime* knobs a write workload needs
  (device numbering + timestamp stepping). Varies per write_config entry.

Keeping the two apart mirrors design §3.7: ``generate_query`` only needs
the structural view, while the PreProcessor hooks additionally take the
runtime knobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ResolvedTable:
    """Structural view of one table passed to a write strategy.

    Parameters
    ----------
    fqn:
        Fully qualified ``db.table`` name, lowercased.
    columns:
        Ordered column names, in build (DDL) order.
    table_config:
        Raw table metadata (timestamp column, ptag columns, …) forwarded
        to ``direct_insert_write.preprocessor_generator``. Optional for
        strategies that only need ``fqn`` / ``columns``.
    """

    fqn: str
    columns: Sequence[str]
    table_config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WriteRuntime:
    """Runtime numbering / timestamp knobs for a write workload."""

    device_per_thread: int = 1
    ms_step: int = 1000
    device_start: int = 0
    batch_seq_init: int = 0
