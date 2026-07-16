# 2026-07-16 fixture 扩展示例 — 遗留问题清单

`tests/kwjdbc_svt/fixtures/{test_model,test_cfg}.yaml` 扩展到 query_config + batch_prepared 后，端到端
smoke 串联暴露一批 pre-existing 缺陷。本轮逐一修复后已稳定于 KSQL 层，但仍剩三条未触动，
留给独立 DCR 推进。本文件留作后续接手时的入口。

## 状态回顾

| 阶段 | 结果 |
|---|---|
| JMX 生成 | pass（exit 0，~30KB test_plan.jmx） |
| Setup / DDL | pass（`retentions 3d` bare 形式可被 KaiwuDB 接受） |
| Setup / SharedMemory | pass（loader 写入 global `JMeterUtils.getJMeterProperties()`） |
| Sampler / 写 | 触达 KSQL（DB 真实连接）但 INSERT 失败 |
| Sampler / 查 | na（本轮未跑通到 query sampler，Query thread group 配置未受污染） |
| 真 bug 数（已修） | 11（见 commit 4b385a2 之外本轮 +1 commit） |
| 真 bug 数（未修） | 3（见下） |

## 遗留问题

### F-1. seed CSV 字符串带引号 → JDBC 无法推断 INT8/FLOAT 类型

**位置**：`src/seed_data_generator/`（生成器）+ `src/shared_memory_initializer/`（loader）

**症状**：
```
KSQLException: ERROR: could not resolve "25" as INT8 type (column col_int8_1)
KSQLException: ERROR: could not resolve "73.64" as FLOAT4 type (column col_float4_1)
```

**根因**：
- seed-data-generator 写 CSV 时给所有字段加双引号（`"25"`、`"73.64"`）
- SharedMemoryLoader 用 `line.split(',')` 拆分，**未剥离字段两端引号**
- 落到 `props` 的 row cell 是 String `"25"`，batch_prepared sampler 调
  `pstmt.setObject(colIdx, value)` 时 KaiwuDB JDBC driver 拿到 String、无法推断 INT8
- 直接_insert 路径（single_insert / batch_insert）走的是 inline SQL 字符串拼接，绕开 setObject，
  所以单条写入能跑通；只有 PreparedStatement 路径暴露

**建议修法**（任选其一）：
1. loader `line.split(',')` 后对每字段执行 `field.replaceAll('^"|"$', '')` 剥引号
2. seed-data-generator 改用无引号 CSV writer（下游 loader 已实现无引号解析）
3. sampler 按 `columnTypes[i]` 调 `pstmt.setInt` / `setDouble` / `setString` 显式定型

**影响范围**：所有 `*_prepared` 模式 + 所有数值列。

**Failing 测试**：无现成单测，需新增 `tests/shared_memory_initializer/test_quote_stripping.py`
（loader 解析 `"25"` → `25`） + `tests/write_strategies/test_int_type_binding.py`（sampler 显式定型）。

### F-2. 占位符 `${device_code}` 未被 loader 替换

**位置**：`src/seed_data_generator/`

**症状**：seed CSV 内容形如
```
"29","73.64","${device_code}","M1"
```
loader 直接把字面 `${device_code}` 塞进 `props["__SHARED_MEM_..."]`。batch_prepared 预处理器
只在 `ptagIdx` 位置覆盖 `device_<n>`，未扫其他列；sampler 端收到的就是字面 `${device_code}`。
DDL 不接受该值：
```
KSQLException: ERROR: ... invalid input syntax for type ...
```

**根因**：seed generator 模板里直接写占位符，无替换机制。

**建议修法**：
- seed-data-generator 在生成 CSV 时**不写占位符**，直接为每个 (device, row) 组合
  生成具体值；或者生成两份 CSV — 一份有占位符（供 query sampler `?` 采样用），
  一份写完 device 标识（供 write sampler 用）
- 替代方案：loader 检测到 `${...}` 占位符时按 (tableName, colName) 维度从 device_code
  映射表替换

**影响范围**：所有 `*_prepared` 模式的写阶段。`single_insert` / `batch_insert` 也受影响但
inline 路径下未走完。

**Failing 测试**：无。

### F-3. `first_ptag` UDV 兜底靠硬编码

**位置**：`src/jmx_skeleton_generator/generators/write_groups.py:_resolve_first_ptag`

**症状**：当 caller 不传 `model`（轻量级单测场景），预处理器从
`vars.get("first_ptag") ?: "ptag_varchar_1"` 兜底，硬编码 `ptag_varchar_1`。
如果表的第一个 Primary Tag 不是 varchar（比如 spec §8.1 允许的 INT8 形态），兜底错。

**根因**：`first_ptag` UDV 走 `ColumnNamer` 命名约定 + 实际类型做后缀；
UDV 兜底路径没有走 ColumnNamer。

**建议修法**：
- 把 `first_ptag` 计算从 `write_groups._resolve_first_ptag` 抽到 `column_namer` 模块顶层
- 单测路径（无 model）走相同 ColumnNamer 路径，给一个最小 TsTableConfig 即可推

**影响范围**：所有 *_prepared 写预处理器；目前 fixture 只测了 varchar primary tag，未触发。

**Failing 测试**：无现成 — 需新增 `tests/jmx_skeleton_generator/test_first_ptag_resolution.py`
覆盖 int primary tag 场景。

## 推进建议

按依赖关系：
1. **F-1** 是阻塞（不修无法验证 F-2 是否真有 bug — 当前 INSERT 失败可能掩盖 F-2）
2. **F-2** 在 F-1 修完后才能稳定复现 / 修
3. **F-3** 是边角，独立可推进

F-1 单独提个 DCR（CSV 引号剥离是生成器层契约变更），F-2 跟 DDL/loader 都相关但应独立 issue，
F-3 是 DCR 编号留给后续的 column_namer 抽取 PR。

## 触发场景留档

**复现命令**（截至 2026-07-16 末态）：
```bash
source venv/bin/activate
rm -rf /tmp/jmeter-smoke/out && mkdir -p /tmp/jmeter-smoke
python -m kwjdbc_svt.main tests/kwjdbc_svt/fixtures/test_model.yaml \
    tests/kwjdbc_svt/fixtures/test_cfg.yaml -o /tmp/jmeter-smoke/out
timeout 15 jmeter -n -t /tmp/jmeter-smoke/out/test_plan.jmx \
    -Jtest_duration=3 -Jnum_threads=1 -Jdevice_start=1 -Jdevice_per_thread=1 \
    -Jwrite_throughput=60 -j /tmp/jmeter-smoke/jmeter.log
grep -m1 "KSQLException" /tmp/jmeter-smoke/jmeter.log
```

**DB 先决条件**：KaiwuDB 容器运行在 `localhost:26257`，`iot_monitor.t_cnc` 表已 DROP
（`mcp__kwdb__write-query DROP TABLE iot_monitor.t_cnc`）。SetupThreadGroup DDL-2
会按 fixture 自动重建。

## 不在本轮范围

- query sampler 真跑（fixture 三个 query 还未在 smoke 中实际命中 DB）
- 多端协同 `device_start` 路径验证
- schemaless 模式（T2，spec 显式 defer）
- `nullable=true` 数据列的真 null 投递（loader 仍把 null 当字面字符串 "null" 处理）
