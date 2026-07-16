"""Batch PreparedStatement write strategy.

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

JMeter ``JDBCSampler`` can only bind one parameter set per call, so
batch_prepared bypasses it and uses ``JSR223Sampler`` to invoke JDBC
``addBatch`` / ``executeBatch`` directly. The batch size is
explicitly capped — see the section “batch size 上限 / 连接超时 / 异常
回滚” below.

Batch size ceiling
------------------
``batch_size_max`` caps how many rows a single
``executeBatch`` invocation may enqueue. The default is 1000 (well below
JMeter's typical default JDBC fetch size, but configurable through
``get_sampler_config`` extras; see ``review.md`` Boundary §1 “batch
size 上限 / 连接超时 / 异常回滚”).

Connection timeout
------------------
``connection_timeout_ms`` sets the ``Connection.setNetworkTimeout``
value used at batch open. Default 30 000 ms.

Exception rollback
------------------
On any ``SQLException`` the script rolls back the active transaction
(via the optional ``tx_conn`` path) and propagates the exception so
JMeter records a sample failure.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from utils.preprocessor_helpers import all_groovy_decls
from write_strategies.base import WriteStrategy, WriteStrategyError
from write_strategies.models import ResolvedTable, WriteRuntime

# Conservative defaults; bump via the sampler config extras.
DEFAULT_BATCH_SIZE_MAX = 1000
DEFAULT_CONNECTION_TIMEOUT_MS = 30_000


class BatchPreparedStatementStrategy(WriteStrategy):
    """``mode="batch_prepared"`` — JDBC batch via JSR223Sampler."""

    def __init__(
        self,
        batch_size_max: int = DEFAULT_BATCH_SIZE_MAX,
        connection_timeout_ms: int = DEFAULT_CONNECTION_TIMEOUT_MS,
    ) -> None:
        if not isinstance(batch_size_max, int) or batch_size_max <= 0:
            raise WriteStrategyError(
                f"batch_size_max must be > 0, got {batch_size_max!r}"
            )
        if not isinstance(connection_timeout_ms, int) or connection_timeout_ms < 0:
            raise WriteStrategyError(
                f"connection_timeout_ms must be >= 0, got {connection_timeout_ms!r}"
            )
        self._batch_size_max = batch_size_max
        self._connection_timeout_ms = connection_timeout_ms

    @property
    def mode_name(self) -> str:
        return "batch_prepared"

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
                "batch_prepared mode requires an INSERT template "
                "from PreparedInsertTemplateGenerator"
            )
        return insert_template

    def get_sampler_type(self) -> str:
        return "JSR223Sampler"

    def get_sampler_config(self) -> Dict[str, Any]:
        return {
            "scriptLanguage": "groovy",
            "batchSizeMax": self._batch_size_max,
            "connectionTimeoutMs": self._connection_timeout_ms,
        }

    def requires_param_setup(self) -> bool:
        return True

    def get_preprocessor_code(
        self,
        table: ResolvedTable,
        batch_lines: int,
        runtime: WriteRuntime,
    ) -> Optional[str]:
        """Batch_prepared stages rows inside the JSR223Sampler body itself.

        Kept for symmetry so the JMX builder can attach a sampler
        preamble when desired. Returns ``None`` by default.
        """
        return None

    def get_sampler_script(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
    ) -> Optional[str]:
        """Return the Groovy body the JSR223Sampler executes per iteration."""
        table_name = table.fqn
        if not table_name:
            raise WriteStrategyError(
                "batch_prepared.get_sampler_script requires a table fqn"
            )
        batch_max = self._batch_size_max
        timeout_ms = self._connection_timeout_ms
        decls = all_groovy_decls()
        # The full Groovy body — uses addBatch / executeBatch, bounded
        # by batchSizeMax, rolls back on SQLException.
        return (
            f"{decls}\n"
            "// -------- batch_prepared: JSR223Sampler body --------\n"
            f"def tableKey = '{table_name}'\n"
            f"def batchSizeMax = {int(batch_max)}\n"
            f"def connectionTimeoutMs = {int(timeout_ms)}\n"
            "def dataSource = 'jdbcConfig'\n"
            "def conn = null\n"
            "def stmt = null\n"
            "try {\n"
            "    def ctxEnv = ctx.getThreadContext().getVariables()\n"
            "    def prev = ctxEnv.getObject('java.sql.Connection')\n"
            "    conn = (prev != null) ? prev : "
            "org.apache.jmeter.protocol.jdbc.util.DataSourceElement\n"
            "        .getConnection(dataSource)\n"
            "    conn.setAutoCommit(false)\n"
            "    conn.setNetworkTimeout(Runnable::run, connectionTimeoutMs)\n"
            "    stmt = conn.prepareStatement(org.apache.jmeter.util.JMeterUtils\n"
            "            .getJMeterProperties().get('prep_' + tableKey) "
            "as String)\n"
            "    int batched = 0\n"
            "    int totalRows = (vars.get('batch_lines_total') as Integer) ?: batchSizeMax\n"
            "    for (int r = 0; r < totalRows && batched < batchSizeMax; r++) {\n"
            "        int paramIdx = 0\n"
            "        // timestamp + device id parameter wiring consumed "
            "by the prepared statement.\n"
            "        long ts = System.currentTimeMillis()\n"
            "        long deviceNumber = calculateDeviceNumber(0L, 0L, 1L, r)\n"
            "        stmt.setTimestamp(paramIdx++, new java.sql.Timestamp(ts))\n"
            "        stmt.setString(paramIdx++, deviceIdentifier(deviceNumber))\n"
            "        stmt.addBatch()\n"
            "        batched++\n"
            "    }\n"
            "    int[] counts = stmt.executeBatch()\n"
            "    conn.commit()\n"
            "    SampleResult.setResponseMessage('batch_prepared ok rows=' + batched)\n"
            "    SampleResult.setSuccessful(true)\n"
            "} catch (java.sql.SQLException sqlEx) {\n"
            "    if (conn != null) {\n"
            "        try { conn.rollback() } catch (java.sql.SQLException ignored) {}\n"
            "    }\n"
            "    SampleResult.setSuccessful(false)\n"
            "    SampleResult.setResponseMessage('batch_prepared failed: ' + sqlEx.getMessage())\n"
            "    log.error('batch_prepared failed: ' + sqlEx)\n"
            "    throw sqlEx\n"
            "} finally {\n"
            "    if (stmt != null) { try { stmt.close() } "
            "catch (java.sql.SQLException ignored) {} }\n"
            "    if (conn != null) { try { conn.setAutoCommit(true) } "
            "catch (java.sql.SQLException ignored) {} }\n"
            "}\n"
        )
