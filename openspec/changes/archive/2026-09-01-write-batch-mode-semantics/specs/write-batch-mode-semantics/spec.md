## ADDED Requirements

### Requirement: 5 mode 业务含义按"每 SQL 行数"重定义

5 mode（`single_insert` / `batch_insert` / `single_prepared` / `batch_prepared` / `schemaless`）命名 MUST 维持不变，业务语义 MUST 按"每条 INSERT SQL 写多少行"重新定义：

| mode | 业务语义 | SQL 形状 |
|---|---|---|
| single_insert | 1 行 | `insert into t values (?, ?)` |
| single_prepared | 1 行 | `PreparedStatement.setXxx(...)` × 1 |
| batch_insert | N 行 | `insert into t values (?,?),(?,?),(?,?)` |
| batch_prepared | N 行 | `addBatch() × N` + `executeBatch()` |
| schemaless | N Lines/HTTP body | N 行 InfluxDB Line + `\n` 分隔 |

#### Scenario：single 模式业务期望 = 1 行/SQL

- **WHEN** 用户配置 `mode: single_insert` 或 `mode: single_prepared` 且 `batch_lines: 1`
- **THEN** 每条 INSERT SQL 写 1 行
- **AND** 单 sampler 内 for 循环遍历 `[device_start, device_start + device_per_thread - 1]` 范围的设备，每设备各写 1 条 SQL

#### Scenario：batch 模式业务期望 = N 行/SQL

- **WHEN** 用户配置 `mode: batch_insert` 或 `mode: batch_prepared` 或 `mode: schemaless` 且 `batch_lines: N`
- **THEN** 每条 INSERT SQL（或每 HTTP body）写 N 行
- **AND** N 行的时间戳按 `ms_step` 间隔递增生成

### Requirement: batch_lines 字段覆盖全部 5 mode

`batch_lines` 字段 MUST 覆盖全部 5 mode，约束 SHALL 如下：

| mode | batch_lines 约束 |
|---|---|
| single_insert | `= 1`（R-PAR-016 已有） |
| single_prepared | `= 1`（R-PAR-016 扩展对称约束） |
| batch_insert | `≥ 1`，无上限 |
| batch_prepared | `≥ 1`，无上限 |
| schemaless | `≥ 1`，语义为"每 HTTP body 的 Line 数量" |

#### Scenario：single_prepared + batch_lines=1 OK

- **WHEN** fixture 配置 `mode: single_prepared` + `batch_lines: 1`
- **THEN** `WriteConfig` schema 校验通过，不抛 `ValueError`

#### Scenario：single_prepared + batch_lines>1 ValueError

- **WHEN** fixture 配置 `mode: single_prepared` + `batch_lines: 5`
- **THEN** `WriteConfig.check_single_modes_batch_lines_one` 抛 `ValueError`，消息含 `single_prepared mode requires batch_lines=1`
- **AND** 生成器在 fixture 解析阶段即失败，不进入 JMX 生成

#### Scenario：schemaless + batch_lines=N 语义对齐

- **WHEN** fixture 配置 `mode: schemaless` + `batch_lines: 10`
- **THEN** 每 HTTP body 内拼 10 个 InfluxDB Line（`\n` 分隔）
- **AND** 与 `mode: batch_insert + batch_lines: 10` 的"N 行/SQL"语义对齐

### Requirement: Write TG sampler 内 for 循环遍历 device_per_thread

每个 Write TG sampler / PreProcessor 内部 MUST 按以下顺序执行：

1. PreProcessor 算本 tick 的 `deviceIndex ∈ [device_start, device_start + device_per_thread - 1]`（**绝对设备号**，与 device_start 绑定，多端协同时不同端的 deviceIndex 范围不重叠）
2. 外层 `for deviceIndex in device_start..(device_start + device_per_thread - 1)`：
   - 用内联 GString `"${threadNum}_${deviceIndex}"` 派生第一 ptag
   - INSERT 1 条 SQL（**写 `batch_lines` 行 × 1 device**——把同 device 的 `batch_lines` 个时间戳拼成 1 条 SQL 入库；动机：KaiwuDB 时序底层每 device 一个文件，跨 device 单 SQL 需同时打开/关闭多个文件性能差）或生成 1 个 HTTP body（内含 `batch_lines` Line）
   - 单 SQL/单 HTTP body = 1 throughput tick
3. sampler 整体仍挂 `ConstantThroughputTimer calcMode=0`；for 循环不影响 throughput 调度
4. **`throughput` 业务语义 = 每个设备的 SQL 触发频率**（per-device-per-minute），sampler 内部 for 循环 dpt 个设备自动覆盖：`sampler/min/thread = per-device SQL/min`（因 1 sampler = dpt 个 SQL）。**`throughput × batch_lines` = 单设备每分钟入库行数**

#### Scenario：throughput=1/min + batch_lines=60 + ms_step=1s = 每设备 1 行/秒

- **WHEN** 配置 `throughput: 1/min`, `num_threads: 2`, `device_per_thread: 2`, `batch_lines: 60`, `ms_step: 1000`, `mode: batch_insert`, `device_start: 1`
- **THEN** 单 SQL 覆盖 60 秒时间窗口（60 行 × ms_step=1s = 60s）
- **AND** 每设备每分钟 1 条 SQL → 每设备每分钟 60 行入库 = **1 行/秒/设备**（= 业务意图）
- **AND** 每 tick 落库行数 = `60 × 2 = 120 行`（batch_lines × dpt），但 for 循环 dpt 次 SQL 共享 1 throughput tick
- **AND** 每线程 effective 落库速率 = `1 × 60 × 2 / 60 = 2 行/秒/线程 = 120 行/分钟/线程`
- **AND** 单表 TG 总落库速率 = `1 × 2 × 2 × 60 / 60 = 4 行/秒 = 240 行/分钟`
- **AND** for 循环范围 `deviceIndex ∈ [1, 2]`（端 A）；端 B 配 `device_start: 3` 则 `deviceIndex ∈ [3, 4]`，不重叠

#### Scenario：1 sampler = 1 throughput tick（per-device throughput 视角）

- **WHEN** `ConstantThroughputTimer calcMode=0`（This thread only）配 `throughput: 60/min`
- **THEN** 每线程每分钟触发 60 次 sampler（60 次/分钟/线程）
- **AND** 1 sampler 内部 for 循环 dpt 个设备 → 1 sampler = dpt 个 SQL → 每设备 SQL 触发频率 = `throughput = 60/min`
- **AND** dpt 个 SQL 不重复计入 throughput 调度（因 1 tick = 1 sampler = dpt 个 SQL 整体）

### Requirement: 落库行数公式

落库行数 MUST 按以下公式计算：
```
rows_per_tick              = batch_lines × device_per_thread       # 1 sampler 内 dpt 个 SQL 共享 1 tick
rows_per_sec_per_thread    = throughput × batch_lines × device_per_thread / 60
rows_per_sec_per_table     = throughput × num_threads × batch_lines × device_per_thread / 60
rows_per_sec_cluster       = throughput × num_threads × batch_lines × device_per_thread × 端数 / 60
rows_per_sec_per_device    = throughput × batch_lines / 60          # 业务意图：每设备入库速率
```

**吞吐单位语义**：配置字段 `throughput` = **每个设备的 SQL 触发频率**（per-device-per-minute）；`ConstantThroughputTimer calcMode=0` 实际触发频率 = `throughput`（per minute per thread），与 per-device 一致因 1 sampler = dpt SQL。

#### Scenario：集群总落库速率公式（同上例 throughput=1/min）

- **WHEN** 配置 `throughput: 1/min`, `num_threads: 2`, `device_per_thread: 2`, `batch_lines: 60`, 端数 = 1
- **THEN** `rows_per_sec_per_device = 1 × 60 / 60 = 1 行/秒/设备`
- **AND** `rows_per_sec_cluster = 1 × 2 × 2 × 60 × 1 / 60 = 4 行/秒 = 240 行/分钟`
- **AND** `test_duration: 300s` 期望落库 `4 × 300 = 1200 行`（实测 ±10%）

#### Scenario：ms_step 与 batch_lines 配合决定单 SQL 覆盖时间窗口

- **WHEN** `ms_step: 1000ms`, `batch_lines: 60`
- **THEN** 单 SQL 覆盖时间窗口 = `60 × 1000ms = 60s`（1 分钟）
- **AND** 与 `throughput: 1/min` 配对 → 1 条 SQL 入库覆盖 1 分钟数据 → 1 行/秒/设备（业务对齐）
- **WHEN** `ms_step: 1000ms`, `batch_lines: 10`
- **THEN** 单 SQL 覆盖时间窗口 = `10 × 1000ms = 10s`
- **AND** 与 `throughput: 6/min` 配对 → 1 条 SQL 入库覆盖 10s 数据 → 1 行/秒/设备（业务对齐）

### Requirement: SetupTG bind sampler 烤齐 numThreads × devicePerThread 个 entry

`shared_memory_setup.py::_build_bind_sampler_groovy` MUST 改双层 for（t + b），每 cycle MUST 用 `deviceIndex = device_start + b`，`deviceCode = "${t}_${deviceIndex}"`（内联 GString 拼接）派生 deviceCode，烤到 `__SHARED_MEM_{db}_{table}_bind[deviceCode]`。

#### Scenario：dpt=2 + device_start=1 fixture SetupTG 烤 4 个 key

- **WHEN** `num_threads: 2`, `device_per_thread: 2`, `device_start: 1`
- **THEN** SetupTG bind sampler 烤 4 个 SharedMemory key：`0_1`, `0_2`, `1_1`, `1_2`
- **AND** deviceIndex 范围 `[1, 2]`（端 A）；端 B 配 `device_start: 3` → deviceIndex 范围 `[3, 4]`，跨端 ptag 不重叠
- **AND** 每 key 对应一组列子集（`col_names` + `row_values[batchLines]`），与 D-21/D-25 一致

#### Scenario：dpt=1 退化为单层

- **WHEN** `num_threads: 2`, `device_per_thread: 1`, `device_start: 1`
- **THEN** SetupTG bind sampler 烤 2 个 SharedMemory key：`0_1`, `1_1`
- **AND** deviceIndex 范围 `[1, 1]`（退化）；行为与 dpt=1 旧实现一致（向后兼容）

#### Scenario：多端协同 deviceIndex 范围不重叠

- **WHEN** 端 A 配 `device_start: 1, device_per_thread: 2`；端 B 配 `device_start: 3, device_per_thread: 2`
- **THEN** 端 A 烤 4 个 key（deviceIndex [1,2]）；端 B 烤 4 个 key（deviceIndex [3,4]）
- **AND** 端 A、端 B 不会重复生成同一 deviceCode（ptag `{threadNum}_{deviceIndex}` 跨端唯一）

### Requirement: bind 分支 InfluxDB Line tag_set = 所有 ptag + regular_tag

schemaless bind 分支（`rest_write_groups.py:244-248`）InfluxDB Line `tag_set` MUST 包含所有 ptag + regular_tag 列值。

#### Scenario：multi-tag fixture bind 分支不丢 rtag

- **WHEN** fixture 含 1 ptag + 1 rtag + `col_tag_bind_mode: true`
- **THEN** schemaless bind 分支 tag_set 包含 ptag 列值 + rtag 列值
- **AND** KaiwuDB `select distinct (tag_set) from iot_monitor.t_full` 含 ptag + rtag 真实值

#### Scenario：fixture 无 regular_tag 时行为兼容

- **WHEN** fixture 仅含 ptag，无 rtag
- **THEN** tag_set 构建跳过空 rtag list；输出 tag_set 仅含 ptag（与改前行为一致）

### Requirement: ts 列按 ms_step 间隔递增生成 batch_lines 个（**整步语义** = `+ i × msStep`）

所有 5 mode + bind 分支的 ts 列 MUST 按 **`ms_step` 间隔（整步语义）**递增生成 `batch_lines` 个时间戳（即 `+ i × msStep`，**非** `+ i × (msStep / batchLines)` **分摊语义**）。**单 SQL 覆盖时间窗口 MUST = `batch_lines × ms_step`**。

#### Scenario：整步 vs 分摊语义对比

- **WHEN** 配置 `batch_lines: 10`, `ms_step: 1000`
- **THEN** 整步语义（采用）：10 行时间戳间隔 = `1000ms`，10 行覆盖 `9 秒`（= `9 × 1000ms`）
- **AND** 分摊语义（旧 D-24）：10 行时间戳间隔 = `100ms`，10 行覆盖 `0.9 秒`（= `9 × 100ms`）—— 与业务意图"单 SQL 覆盖 `batch_lines × ms_step` 时间窗口"不符
- **AND** 本 DCR MUST 采用整步语义（修复 gap #6）

#### Scenario：batch_lines=10 绑 path 生成 10 个递增 ts

- **WHEN** `batch_lines: 10`, `ms_step: 1000`
- **THEN** bind 分支 10 行时间戳依次为 `baseTime, baseTime+1000, baseTime+2000, ..., baseTime+9000`（毫秒）
- **AND** KaiwuDB `select min(ts), max(ts) from iot_monitor.meters` 差值 ≈ `9000ms`（9 秒）

#### Scenario：batch_lines=10 绑 path 生成 10 个递增 ts

- **WHEN** `batch_lines: 10`, `ms_step: 1000`
- **THEN** bind 分支 10 行时间戳依次为 `baseTime, baseTime+1000, baseTime+2000, ..., baseTime+9000`（毫秒）
- **AND** KaiwuDB `select min(ts), max(ts) from iot_monitor.meters` 差值 ≈ `9000ms`（9 秒）

### Requirement: single_insert / batch_insert / single_prepared bind 分支生效

`generate_write_thread_groups`（`write_groups.py:957-1201`）MUST 在 3 mode (`single_insert` / `batch_insert` / `single_prepared`) 且 `col_tag_bind_mode=True` 时走 bind 分支：

- `single_insert` / `batch_insert`：MUST 调用 `_build_inline_sql_preprocessor_script(col_tag_bind_mode=True)`
- `single_prepared`：MUST 调用 `_build_batch_prepared_bind_preprocessor_body`
- `single_prepared` + `bind_mode=True` + `batch_lines>1` MUST 抛 ValueError（schema R-PAR-016 对称约束兜底）

#### Scenario：single_insert + bind=true 不再静默错配

- **WHEN** fixture 配置 `mode: single_insert` + `col_tag_bind_mode: true`
- **THEN** 生成 JMX 含 `_build_inline_sql_preprocessor_script(col_tag_bind_mode=True)` 路径
- **AND** SetupTG bind sampler 烤齐 `__SHARED_MEM_*_bind` SharedMemory key
- **AND** WriteTG PreProcessor 从 bind map 取 row 字典，按内联 GString `"${threadNum}_${deviceIndex}"` 派生第一 ptag

#### Scenario：single_prepared + bind=true + batch_lines=1 OK

- **WHEN** fixture 配置 `mode: single_prepared` + `col_tag_bind_mode: true` + `batch_lines: 1`
- **THEN** 生成 JMX 含 `_build_batch_prepared_bind_preprocessor_body` 调用
- **AND** PreparedStatement bind path 生效，每 tick 写 `device_per_thread × 1` 行

#### Scenario：single_prepared + bind=true + batch_lines>1 ValueError

- **WHEN** fixture 配置 `mode: single_prepared` + `col_tag_bind_mode: true` + `batch_lines: 5`
- **THEN** `WriteConfig.check_single_modes_batch_lines_one` 抛 `ValueError`
- **AND** 生成器在 fixture 解析阶段即失败

## MODIFIED Requirements

### Modification: 主 spec §2.0 字段表（line ~130-149）

调整以下行：

- `mode`：删去 T0/T1/T2 括号分类；新增「业务语义：single = 1 行/SQL，batch = N 行/SQL，schemaless = N Line/HTTP body」
- `batch_lines`：删去「`batch` 和 `schemaless` 模式下可提供」措辞；改为「全部 5 mode 都可提供；`single_*` 模式强制 = 1（R-PAR-016 对称约束）」
- `device_per_thread`：删去「仅 batch 类生效」隐含措辞；明确「全部 5 mode 都参与 sampler 内 for 循环」
- `ms_step`：保留位置 `ts_col.ms_step`；新增「batch_lines > 1 时按 ms_step 间隔递增生成 N 个时间戳」
- `col_tag_bind_mode`：明确「适用全部 5 mode」（删去当前仅 batch_prepared 路径生效的隐含措辞）

### Modification: 主 spec §2.2 吞吐量与 TG 编排（line ~320-340）

- 新增「落库行数公式」段落
- 写入线程组段落新增「sampler 内 for 循环遍历 `device_per_thread` 个设备」描述
- 删去原「`device_per_thread` 仅 batch 类生效」隐含措辞

### Modification: 主 spec §2.0 col_tag_bind_mode 段（line ~138 区域）

- 在「tag_set 部分仍按所有 ptag + regular_tag 填」段下新增引用本 delta spec §"bind 分支 InfluxDB Line tag_set = 所有 ptag + regular_tag"
- 在「hash 分组」段同步删去 D-21 后已失效的 `hash(ptag_tuple) mod num_threads` 措辞

### Modification: 主 spec §7 已落地排期表（line ~392）

新增行：`write-batch-mode-semantics`（与 col-tag-bind-write 同列；原 `ptag-runtime-derived` 已合并入本 DCR）。