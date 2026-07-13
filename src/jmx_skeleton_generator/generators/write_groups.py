"""Write ThreadGroup generators."""

from __future__ import annotations

from typing import Dict, List

from config_parser.models import WriteConfig
from throughput_control import generate_write_timer
from utils.preprocessor_helpers import all_groovy_decls
from utils.xml_helpers import (
    empty_hash_tree,
    hash_tree,
    jdbc_sampler_element,
    jsr223_preprocessor_element,
    jsr223_sampler_element,
    thread_group_element,
)
from write_strategies import get_strategy


# Groovy body for batch_prepared JSR223PreProcessor (data preparation).
# The helper declarations (calculateLocalDeviceStart + others) are
# prepended by :func:`build_batch_prepared_preprocessor_script` so
# both this script and single_prepared_strategy share one source of
# device-number arithmetic (review §"单一设备号计算 helper" 落地).
_BATCH_PREPARED_PREPROCESSOR_BODY = r"""// JSR223PreProcessor (groovy): batch_prepared 当前批次数据准备
def tableName = vars.get("table_name")
def sharedRows = props.get("__SHARED_MEM_${tableName}") as ArrayList<Object[]>

def batchLines = Integer.parseInt(vars.get("batch_lines") ?: "1")
def totalRows = sharedRows.size()
def startIdx = (int)(Math.random() * totalRows)

// 基准时间（每个线程首次执行时一次性获取）
if (vars.get("base_time") == null) {
    vars.putLong("base_time", System.currentTimeMillis())
}
def baseTime = Long.parseLong(vars.get("base_time"))
def batchSeq = Long.parseLong(vars.get("batch_seq") ?: "0")
def msStep = Long.parseLong(vars.get("ms_step") ?: "1000")

// 设备号计算（本线程负责的设备范围）
def threadNum = ctx.getThreadNum()
def deviceStart = Long.parseLong(vars.get("device_start") ?: "1")
def devicePerThread = Integer.parseInt(vars.get("device_per_thread") ?: "1")
def localDeviceStart = calculateLocalDeviceStart(deviceStart, threadNum, devicePerThread)

def batchRows = new ArrayList<Object[]>()
for (int i = 0; i < batchLines; i++) {
    def srcRow = sharedRows.get((startIdx + i) % totalRows)
    def rowCopy = srcRow.clone()
    // 替换第一个 Primary Tag 占位符为设备标识
    rowCopy[0] = "device_${localDeviceStart + (i % devicePerThread)}"
    // 装配时间戳（假设时间戳为 INSERT 的最后一个参数）
    def ts = new java.sql.Timestamp(baseTime + batchSeq * msStep + (long)(i * msStep / batchLines))
    rowCopy = Arrays.copyOf(rowCopy, rowCopy.length + 1)
    rowCopy[rowCopy.length - 1] = ts
    batchRows.add(rowCopy)
}

vars.putObject("__BATCH_ROWS_${tableName}", batchRows)
vars.put("batch_seq", String.valueOf(batchSeq + 1))
"""

# Groovy scripts for batch_prepared JSR223Sampler (JDBC batch 执行)
BATCH_PREPARED_SAMPLER_SCRIPT = r"""// JSR223Sampler (groovy): batch_prepared JDBC batch 执行
import org.apache.jmeter.protocol.jdbc.config.DataSourceElement

def tableName = vars.get("table_name")
def insertSql = vars.get("insert_sql")
def batchRows = vars.getObject("__BATCH_ROWS_${tableName}") as ArrayList<Object[]>

def rowCount = batchRows.size()
if (rowCount == 0) {
    log.warn("No batch rows prepared for table ${tableName}")
    return
}

DataSourceElement.getConnection("jdbcConfig").withCloseable { conn ->
    conn.prepareStatement(insertSql).withCloseable { pstmt ->
        for (int rowIdx = 0; rowIdx < rowCount; rowIdx++) {
            def row = batchRows.get(rowIdx)
            for (int colIdx = 0; colIdx < row.length; colIdx++) {
                def value = row[colIdx]
                if (value == null) {
                    pstmt.setNull(colIdx + 1, java.sql.Types.NULL)
                } else {
                    pstmt.setObject(colIdx + 1, value)
                }
            }
            pstmt.addBatch()
        }
        pstmt.executeBatch()
    }
}
"""


def build_batch_prepared_preprocessor_script() -> str:
    """Compose the Groovy body for the batch_prepared JSR223PreProcessor.

    Prepends :func:`utils.preprocessor_helpers.all_groovy_decls` so
    that ``calculateLocalDeviceStart`` and the rest of the shared
    helpers are visible at runtime. Single source of truth for
    device-number arithmetic — see tasks §2.3.
    """
    return f"{all_groovy_decls()}\n{_BATCH_PREPARED_PREPROCESSOR_BODY}"


def generate_write_thread_groups(
    write_config: List[WriteConfig],
    prepared_templates: Dict[str, str],
) -> List:
    """Generate write ThreadGroups for all prepared-mode table entries.

    Parameters
    ----------
    write_config:
        All write configuration entries from ``TestConfig``.
    prepared_templates:
        Dictionary mapping ``db.table`` to INSERT template strings.

    Returns
    -------
    A flat list of elements forming all write ThreadGroups.
    - ``batch_prepared``: [ThreadGroup, hashTree, ConstantThroughputTimer,
      hashTree, JSR223PreProcessor, hashTree, JSR223Sampler, hashTree]
    - ``single_prepared`` / other modes: [ThreadGroup, hashTree,
      ConstantThroughputTimer, hashTree, JDBCSampler, hashTree]
    Skips entries that do not use ``single_prepared`` / ``batch_prepared``
    modes (those are relational-table batch inserts handled in Setup).
    Returns an empty list when no prepared modes are configured.
    """
    results: List = []

    for wc in write_config:
        if wc.mode not in ("single_prepared", "batch_prepared"):
            # 关系表 batch insert 由 SetupThreadGroup 路径处理；这里仅管 prepared modes。
            continue

        fqn = wc.tbl_name.lower()
        template = prepared_templates.get(fqn, f"-- placeholder for {wc.tbl_name}")

        # 通过策略注册表决定 sampler 类型与 scriptLanguage；
        # 单插入/批插入/无模式继续交给 SetupThreadGroup 路径，write_groups 不消费。
        strategy = get_strategy(wc.mode)
        sampler_type = strategy.get_sampler_type()
        script_language = strategy.get_config("scriptLanguage", "groovy")
        use_prepared = bool(strategy.get_config("usePrepared", False))

        tg, tg_hash = thread_group_element(
            name=f"Write-{wc.tbl_name}",
            testname=f"[Write] {wc.tbl_name}",
            num_threads=wc.num_threads,
            ramp_time=1,
            duration="${test_duration}",
            loops="-1",
            scheduler=True,
        )

        timer, timer_hash = generate_write_timer()

        if sampler_type == "JSR223Sampler":
            # batch_prepared 使用 JSR223Sampler + 预置 Groovy 体（设计文档 §3.6）；
            # 预置体由 strategy 注册表之外的 jmx_skeleton_generator 维护，
            # 体现 write_groups 与 strategy 的协作边界。
            preprocessor, preproc_hash = jsr223_preprocessor_element(
                name=f"batch_prepared-{wc.tbl_name}-pre",
                script=build_batch_prepared_preprocessor_script(),
                script_language=script_language,
                testname=f"[Write] {wc.tbl_name} - batch_prepared preprocessor",
            )
            sampler, samp_hash = jsr223_sampler_element(
                name=f"Write-{wc.tbl_name}",
                script=BATCH_PREPARED_SAMPLER_SCRIPT,
                script_language=script_language,
                testname=f"[Write] {wc.tbl_name}",
            )
            results.extend([
                tg, tg_hash, timer, timer_hash,
                preprocessor, preproc_hash, sampler, samp_hash,
            ])
        else:
            # single_prepared 走 JDBCSampler；usePrepared 由 strategy 提供。
            sampler, samp_hash = jdbc_sampler_element(
                name=f"Write-{wc.tbl_name}",
                query=template,
                data_source="${db_url}",
                query_type="Prepared Update Statement",
                use_prepared=use_prepared,
                testname=f"[Write] {wc.tbl_name}",
            )
            results.extend([tg, tg_hash, timer, timer_hash, sampler, samp_hash])

    return results
