"""Single-row direct INSERT strategy.

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

Picks one row per execution through JMeter's ``JDBCSampler``. The
``JSR223PreProcessor`` populates a single ``param_N`` slot (one per
column) and the sampler binds the prepared parameters one execution at
a time (``usePrepared=False`` means JMeter performs inline substitution
on the ``?`` placeholders).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from direct_insert_write.errors import DirectInsertGenerationError
from direct_insert_write.preprocessor_generator import generate_preprocessor_script
from direct_insert_write.sql_generator import generate_single_insert_sql
from write_strategies.base import WriteStrategy, WriteStrategyError
from write_strategies.models import ResolvedTable, WriteRuntime


class SingleInsertStrategy(WriteStrategy):
    """``mode="single_insert"`` — one row per sampler execution."""

    @property
    def mode_name(self) -> str:
        return "single_insert"

    def requires_prepared_insert_template(self) -> bool:
        return False

    def generate_query(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
        insert_template: Optional[str] = None,
    ) -> str:
        try:
            return generate_single_insert_sql(table.fqn, table.columns)
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
        try:
            return generate_preprocessor_script(
                table_config=dict(table.table_config),
                device_per_thread=runtime.device_per_thread,
                ms_step=runtime.ms_step,
                batch_lines=1,  # single insert forces one row per execution
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
