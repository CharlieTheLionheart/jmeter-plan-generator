"""Schemaless write strategy (deferred — T2).

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

The schemaless mode is intentionally a placeholder. Callers that
configure ``schemaless`` in ``test_cfg.yaml`` should be rejected at
validation time; the strategy itself refuses to render an actual
sampler script via :class:`NotImplementedError` so any misconfigured
chain fails loudly rather than silently producing bogus JMX.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from write_strategies.base import WriteStrategy
from write_strategies.models import ResolvedTable, WriteRuntime


class SchemalessWriteStrategy(WriteStrategy):
    """``mode="schemaless"`` — placeholder pending T2 design change."""

    @property
    def mode_name(self) -> str:
        return "schemaless"

    def requires_prepared_insert_template(self) -> bool:
        return False

    def generate_query(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
        insert_template: Optional[str] = None,
    ) -> str:
        return ""

    def get_sampler_type(self) -> str:
        return "JSR223Sampler"

    def get_sampler_config(self) -> Dict[str, Any]:
        return {"scriptLanguage": "groovy"}

    def requires_param_setup(self) -> bool:
        return False

    def get_preprocessor_code(
        self,
        table: ResolvedTable,
        batch_lines: int,
        runtime: WriteRuntime,
    ) -> Optional[str]:
        return None

    def get_sampler_script(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
    ) -> Optional[str]:
        raise NotImplementedError(
            "Schemaless write strategy is not yet implemented (T2)"
        )
