"""Batch direct INSERT strategy.

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

Emits a single ``JDBCSampler`` invocation per batch, where the VALUES
clause contains ``batch_lines`` placeholder rows. The preceding
``JSR223PreProcessor`` populates ``batch_lines * n_cols`` ``param_N``
slots in row-major order; the sampler binds them via ``${param_N}``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from direct_insert_write.errors import DirectInsertGenerationError
from direct_insert_write.preprocessor_generator import generate_preprocessor_script
from direct_insert_write.sql_generator import generate_batch_insert_sql
from write_strategies.base import WriteStrategy, WriteStrategyError
from write_strategies.models import ResolvedTable, WriteRuntime


class BatchInsertStrategy(WriteStrategy):
    """``mode="batch_insert"`` — one batch per sampler execution."""

    @property
    def mode_name(self) -> str:
        return "batch_insert"

    def requires_prepared_insert_template(self) -> bool:
        return False

    def generate_query(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
        insert_template: Optional[str] = None,
        *,
        row_count: Optional[int] = None,
    ) -> str:
        if not isinstance(batch_lines, int) or batch_lines <= 0:
            raise WriteStrategyError(
                f"generate_query requires positive 'batch_lines' (int), got {batch_lines!r}"
            )
        try:
            return generate_batch_insert_sql(
                table.fqn,
                table.columns,
                batch_lines,
                row_count=row_count,
            )
        except DirectInsertGenerationError as exc:
            raise WriteStrategyError(str(exc)) from exc

    def get_sampler_type(self) -> str:
        return "JDBCSampler"

    def get_sampler_config(self) -> Dict[str, Any]:
        return {"usePrepared": False}

    def requires_param_setup(self) -> bool:
        return True

    def get_preprocessor_code(
        self,
        table: ResolvedTable,
        batch_lines: int,
        runtime: WriteRuntime,
    ) -> Optional[str]:
        if not isinstance(batch_lines, int) or batch_lines <= 0:
            raise WriteStrategyError(
                f"batch_insert requires 'batch_lines' > 0, got {batch_lines!r}"
            )
        try:
            return generate_preprocessor_script(
                table_config=dict(table.table_config),
                device_per_thread=runtime.device_per_thread,
                ms_step=runtime.ms_step,
                batch_lines=batch_lines,
                device_start=runtime.device_start,
                batch_seq_init=runtime.batch_seq_init,
            )
        except DirectInsertGenerationError as exc:
            raise WriteStrategyError(str(exc)) from exc

    def get_sampler_script(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
    ) -> Optional[str]:
        return None
