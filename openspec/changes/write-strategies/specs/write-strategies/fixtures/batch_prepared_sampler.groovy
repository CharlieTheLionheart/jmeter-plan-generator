def calculateTimestamps(long base_time_ms, long batch_seq, long ms_step, long batch_lines, int row_count) {
    if (batch_lines <= 0L) { throw new RuntimeException('batch_lines must be > 0: ' + batch_lines) }
    if (row_count < 0) { throw new RuntimeException('row_count must be >= 0: ' + row_count) }
    long intra = ms_step / batch_lines
    long base = base_time_ms + batch_seq * ms_step
    def out = []
    for (int i = 0; i < row_count; i++) { out.add(base + i * intra) }
    return out
}

long calculateDeviceNumber(long thread_num, long device_start, long device_per_thread, int row_index) {
    if (device_per_thread <= 0L) { throw new RuntimeException('device_per_thread must be > 0: ' + device_per_thread) }
    if (row_index < 0) { throw new RuntimeException('row_index must be >= 0: ' + row_index) }
    return device_start + thread_num * device_per_thread + ((long) row_index % device_per_thread)
}

def deviceIdentifier(long device_number) {
    return 'device_' + device_number
}

def cloneRows(def rows) {
    def out = []
    rows.each { row -> out.add(new ArrayList(row)) }
    return out
}

long calculateLocalDeviceStart(long deviceStart, int threadNum, long devicePerThread) {
    if (devicePerThread <= 0L) { throw new RuntimeException('devicePerThread must be > 0: ' + devicePerThread) }
    return deviceStart + (long) threadNum * devicePerThread
}

// -------- batch_prepared: JSR223Sampler body --------
def tableKey = 'iot_monitor.sensor_readings'
def batchSizeMax = 1000
def connectionTimeoutMs = 30000
def dataSource = 'jdbcConfig'
def conn = null
def stmt = null
try {
    def ctxEnv = ctx.getThreadContext().getVariables()
    def prev = ctxEnv.getObject('java.sql.Connection')
    conn = (prev != null) ? prev : org.apache.jmeter.protocol.jdbc.util.DataSourceElement
        .getConnection(dataSource)
    conn.setAutoCommit(false)
    conn.setNetworkTimeout(Runnable::run, connectionTimeoutMs)
    stmt = conn.prepareStatement(org.apache.jmeter.util.JMeterUtils
            .getJMeterProperties().get('prep_' + tableKey) as String)
    int batched = 0
    int totalRows = (vars.get('batch_lines_total') as Integer) ?: batchSizeMax
    for (int r = 0; r < totalRows && batched < batchSizeMax; r++) {
        int paramIdx = 0
        // timestamp + device id parameter wiring consumed by the prepared statement.
        long ts = System.currentTimeMillis()
        long deviceNumber = calculateDeviceNumber(0L, 0L, 1L, r)
        stmt.setTimestamp(paramIdx++, new java.sql.Timestamp(ts))
        stmt.setString(paramIdx++, deviceIdentifier(deviceNumber))
        stmt.addBatch()
        batched++
    }
    int[] counts = stmt.executeBatch()
    conn.commit()
    SampleResult.setResponseMessage('batch_prepared ok rows=' + batched)
    SampleResult.setSuccessful(true)
} catch (java.sql.SQLException sqlEx) {
    if (conn != null) {
        try { conn.rollback() } catch (java.sql.SQLException ignored) {}
    }
    SampleResult.setSuccessful(false)
    SampleResult.setResponseMessage('batch_prepared failed: ' + sqlEx.getMessage())
    log.error('batch_prepared failed: ' + sqlEx)
    throw sqlEx
} finally {
    if (stmt != null) { try { stmt.close() } catch (java.sql.SQLException ignored) {} }
    if (conn != null) { try { conn.setAutoCommit(true) } catch (java.sql.SQLException ignored) {} }
}
