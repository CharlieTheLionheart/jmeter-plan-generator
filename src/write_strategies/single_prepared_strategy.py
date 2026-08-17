"""Single-row PreparedStatement write strategy.

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

落地于 commit ``9fdcf0d``（2026-07，(feat) JDBC数据源配置生成器，
DirectInsert/PrepareInsert语句生成器）；主 spec §2.0 L134 mode 枚举 +
§7 历史排期跟踪。

Uses JMeter ``JDBCSampler`` with ``queryType="Prepared Update Statement"``
so the JDBC driver compiles each statement once and reuses the prepared
handle across iterations. The caller (``PreparedInsertTemplateGenerator``)
resolves the ``insert into db.table (cols) values (?, ?)`` template and
passes it through :meth:`generate_query`; the strategy itself is stateless.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from utils.preprocessor_helpers import all_groovy_decls
from write_strategies.base import WriteStrategy, WriteStrategyError
from write_strategies.models import ResolvedTable, WriteRuntime


class SinglePreparedStatementStrategy(WriteStrategy):
    """``mode="single_prepared"`` — prepared single-row insert per execution."""

    @property
    def mode_name(self) -> str:
        return "single_prepared"

    def requires_prepared_insert_template(self) -> bool:
        return True

    def generate_query(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
        insert_template: Optional[str] = None,
    ) -> str:
        """Return the prepared INSERT template supplied by the caller."""
        if insert_template is None:
            raise WriteStrategyError(
                "single_prepared mode requires an INSERT template "
                "from PreparedInsertTemplateGenerator"
            )
        return insert_template

    def get_sampler_type(self) -> str:
        return "JDBCSampler"

    def get_sampler_config(self) -> Dict[str, Any]:
        return {"usePrepared": True}

    def requires_param_setup(self) -> bool:
        return True

    def get_preprocessor_code(
        self,
        table: ResolvedTable,
        batch_lines: int,
        runtime: WriteRuntime,
    ) -> Optional[str]:
        """Emit a JSR223PreProcessor that feeds one row of params per call.

        The single-prep driver does not use shared-memory rows; the
        params come from a per-call Groovy function (timestamps + device
        ids), reusing the project-wide helper declarations in
        :mod:`utils.preprocessor_helpers`.
        """
        table_g = "'" + table.fqn.replace("'", "\\'") + "'"
        decls = all_groovy_decls()
        return (
            f"{decls}\n"
            "// -------- single_prepared: assemble one row --------\n"
            f"def preparedTable = {table_g}\n"
            f"def devicePerThread = {int(runtime.device_per_thread)} as long\n"
            f"def msStepL = {int(runtime.ms_step)} as long\n"
            "def threadNum = ctx.getThreadNum()\n"
            "if (threadNum < 0) { threadNum = (vars.get('__threadNum') as Integer) ?: 0 }\n"
            "long ts = System.currentTimeMillis()\n"
            # Use the shared single-source helper (multi-end tasks §2.4) — both
            # batch_prepared and single_prepared consume calculateLocalDeviceStart.
            "long localStart = calculateLocalDeviceStart(0L, threadNum, devicePerThread)\n"
            "long deviceNumber = localStart\n"
            "vars.put('param_0', new java.sql.Timestamp(ts).toString())\n"
            "vars.put('param_1', deviceIdentifier(deviceNumber))\n"
            "log.info('SinglePrep: table=' + preparedTable + ' ts=' + ts + ' device=' + deviceNumber)\n"
        )

    def get_sampler_script(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
    ) -> Optional[str]:
        return None
