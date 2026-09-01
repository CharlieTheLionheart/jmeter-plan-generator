# Design: write-batch-mode-semantics — 5 mode × batch_lines × dpt 统一

## Context

`feat/sparse-table` 基线 17 commits（pytest 661/661），含 `col-tag-bind-write` 17 commits（已 archive）。`ptag-runtime-derived` DCR 已合并入本 DCR（不再独立推进）。

当前实现存在 5 个已知 gap（详见 proposal.md Why 段）：

- gap #1：SetupTG 仅烤 `numThreads` 个 entry，WriteTG bind 分支固定取 index=0 → dpt>1 时部分设备找不到 SharedMemory key
- gap #2：schemaless bind 分支 InfluxDB Line `tag_set` 只填 ptag，缺 regular_tag
- gap #3：`single_insert` / `batch_insert` / `single_prepared` 三个 mode 与 `col_tag_bind_mode=true` 静默错配
- gap #4：`single_prepared + batch_lines > 1` schema 未禁（运行时未定义）
- gap #5：`_build_inline_sql_preprocessor_script` bind 分支整批共用一个 ts，与 D-24 schemaless bind 分支"batch_lines 个递增 ts" 不一致

业务期望：ptag 第一列用内联 GString `"${threadNum}_${deviceIndex}"` 拼出 + bind 分支 dpt 真生效 + 5 mode 业务含义统一。**deviceIndex 语义必须与 device_start 绑定**（`deviceIndex ∈ [device_start, device_start + device_per_thread - 1]`），多端协同时不同端的 deviceIndex 范围不重叠，ptag `{threadNum}_{deviceIndex}` 跨端唯一。

## Decisions

### Decision 1: 5 mode 命名不变，业务语义按"每 SQL 行数"重定义

**Decision**：5 mode 命名维持 `single_insert` / `batch_insert` / `single_prepared` / `batch_prepared` / `schemaless`，业务语义按"每条 INSERT SQL 写多少行"重新定义。

**Rationale**：
- `single_*` 业务语义 = 1 行；`batch_*` 业务语义 = N 行；`schemaless` = 每个 HTTP body 拼 N 个 InfluxDB Line
- 命名 vs 含义分离：mode 名表达 API 形态（直接 INSERT / PreparedStatement / InfluxDB Line），`batch_lines` 表达行数
- 兼容既有 fixture + pytest；不引入新命名（避免 fixture 重命名 churn）

**Alternatives considered**：
- 改 `single` → `strict`、`batch` → `bulk`：破坏现有 fixture 命名一致性，不推荐
- 合并 T0/T1 为单一 API（只保留 PreparedStatement）：代码量大、废掉 col-tag-bind-write 已落地的直接 INSERT 路径，不推荐

### Decision 2: `batch_lines` 字段覆盖全部 5 mode

**Decision**：`batch_lines` 字段覆盖全部 5 mode，约束如下：

| mode | batch_lines 约束 |
|---|---|
| single_insert | `= 1`（R-PAR-016 已有） |
| single_prepared | `= 1`（R-PAR-016 扩展对称约束） |
| batch_insert | `≥ 1`，无上限 |
| batch_prepared | `≥ 1`，无上限 |
| schemaless | `≥ 1`，语义为"每 HTTP body 的 Line 数量" |

**Rationale**：
- 字段单一入口：用户配置 `batch_lines` 一处生效，5 mode 全覆盖
- schemaless 模式下 N Line = 一次 POST body 内容，与 batch_insert 的"每条 SQL N 行"语义对齐
- spec §2.0 L147 当前措辞「`batch` 和 `schemaless` 模式下可提供」改为「全部 5 mode 都可提供」

**Alternatives considered**：
- 给 schemaless 另开字段（`influxdb_lines_per_body`）：与 `batch_lines` 重复表达，违反字段单一入口原则，不推荐
- `batch_lines` 仅作用于含 batch 关键字的 mode（保留现行为）：gap #4 永远存在，不推荐

### Decision 3: R-PAR-016 扩展为对称约束

**Decision**：`single_insert ∪ single_prepared` 都要求 `batch_lines == 1`。校验函数从 `check_single_insert_batch_lines`（`models.py:381-389`）改名为 `check_single_modes_batch_lines_one`，覆盖两个 mode。

**Rationale**：
- "single" 业务含义 = 1 行是定义层硬约束，不是配置选项
- 运行时未定义行为不可接受：fail-fast 在 schema 校验阶段
- 单测覆盖：`single_prepared + batch_lines == 1` OK、`single_prepared + batch_lines > 1` ValueError

**Alternatives considered**：
- 仅 schema warn 不抛错：用户可能忽略，运行时仍崩，不推荐
- 允许 `single_* + batch_lines > 1` 但 runtime 强制 batch_lines=1：掩盖用户意图，不推荐

### Decision 4: SetupTG bind sampler 烤齐 `numThreads × devicePerThread` 个 entry

**Decision**：`shared_memory_setup.py::_build_bind_sampler_groovy`（`line 106-297`）的单层 `for (int t = 0; t < numThreads; t++)`（`line 232`）改双层 `for (int t = 0; t < numThreads; t++) { for (int b = 0; b < devicePerThread; b++) { ... } }`。每 cycle 内 `deviceIndex = deviceStart + b`，`deviceCode = "${t}_${deviceIndex}"`（内联 GString 拼接），烤到 `__SHARED_MEM_{db}_{table}_bind[deviceCode]`。

**Rationale**：
- 双层 for 烤齐 `numThreads × devicePerThread` 个 key
- gap #1 修复：现有 `test_model_col_bind.yaml`（dpt=2）暴露 "no row for deviceCode device_2/device_4"，commit 2 自动修复
- `batchLines` 仍每 device 烤 N 行（与 D-25 一致）
- `deviceIndex ∈ [deviceStart, deviceStart + devicePerThread - 1]` 是与 device_start 绑定的**绝对设备号**：多端协同时不同端的 deviceIndex 范围不重叠（如端 A deviceStart=1 → 1..2；端 B deviceStart=3 → 3..4；端 A、B 不会重复生成 deviceCode）
- ptag 第 1 列值用内联 GString `"${t}_${deviceIndex}"` 直接拼接，不另抽 `ptagRuntimeValue` helper（已合并入本 DCR 的核心规则，无需独立 helper）

**Alternatives considered**：
- SetupTG 仅烤 `numThreads` 个 key，runtime devicePerThread 索引按旁路算：与 D-21 key=deviceCode 决策冲突，不推荐
- SetupTG 烤 Lazy key：JMeter WriteTG 并发访问 SetupTG lazy 写会触发 JMeterUtils 竞态，禁用
- `deviceIndex ∈ [1, devicePerThread]`（1-indexed per-thread 局部编号）：丢失 device_start 维度，多端协同 ptag 重复，**用户已否决**，2026-08-31

### Decision 5: Write TG sampler 内 `for d in deviceStart..(deviceStart + devicePerThread - 1)` 展开 dpt

**Decision**：每个 Write TG sampler / PreProcessor 内部套 `for (int d = deviceStart; d < deviceStart + devicePerThread; d++)` 外层循环（即 `deviceIndex ∈ [deviceStart, deviceStart + devicePerThread - 1]`），每 cycle 用内联 GString `"${threadNum}_${d}"` 拼第一 ptag 值；INSERT 1 条 SQL（写 `batch_lines` 行 × 1 device）或生成 1 个 HTTP body（内含 `batch_lines` Line）。**单 SQL/单 HTTP body = 1 throughput tick**。

**Rationale**：
- sampler 内 for 循环是单一入口：spec §2.2 显式声明
- 与 ConstantThroughputTimer `calcMode=0` 对齐：每线程 sampler 触发 1 次 = 1 tick，for 循环内 dpt 次 SQL 不重复计入 throughput 调度
- 实际落库行数 = `throughput × num_threads × batch_lines × device_per_thread × test_duration / 60`
- `deviceIndex = deviceStart + b`（b ∈ [0, devicePerThread)）即与 device_start 绑定的绝对设备号范围 `[deviceStart, deviceStart + devicePerThread - 1]`；多端协同时不同端不重叠
- **业务意图**：`batch_lines` 把同 device 的多个时间戳拼成 1 条 SQL 入库。动机：KaiwuDB 时序底层每 device 一个文件，跨 device 单 SQL 需同时打开/关闭多个文件性能差；同 device 多时间戳拼 1 SQL 大幅减少文件 open/close 次数

**Alternatives considered**：
- JMeter `LoopController.loops = numThreads × devicePerThread`（外部 DCR 旧提案）：与 ConstantThroughputTimer 交互产生 throughput 浮动（per-thread 均摊循环次数与 throughput 配置冲突），不推荐。本 DCR 显式否定该方案；dpt 展开统一在 sampler 内 for 循环
- 拆多个 Write TG（每个 device 一个 TG）：装配复杂度高，Schedule 单 TG 足够，不推荐
- `for d in 1..devicePerThread`（1-indexed per-thread 局部编号）：丢失 device_start 维度，多端协同 ptag 重复，**用户已否决**，2026-08-31

### Decision 6: throughput = per-device SQL/min；rows_per_tick = `batch_lines × device_per_thread`

**Decision**：`throughput` 配置字段 MUST 表达 **per-device 每分钟 SQL 触发频率**（per-device-per-minute）；spec §2.0 L131 措辞从"每个写入线程的目标吞吐量"更新为"**每个设备的目标吞吐量**"。`ConstantThroughputTimer calcMode=0` 实际配置值 = `throughput`（每线程每分钟 sampler 触发数 = 每设备每分钟 SQL 数，因 1 sampler = dpt 个 SQL 自动覆盖 dpt 个设备）。

每个 throughput tick 落库行数 = `batch_lines × device_per_thread`；**每设备入库速率**（业务意图）= `throughput × batch_lines / 60` 行/秒/设备。

**Rationale**：
- 业务意图对齐：每分钟每设备 SQL 数 + 每 SQL 写 batch_lines 行 = 每设备入库行数
- `ConstantThroughputTimer calcMode=0` 不需要修改（实现层 throughput = sampler/min/thread = per-device SQL/min，巧合一致）
- 落库行数公式唯一入口：spec §2.2 显式公式 `rows_per_sec_cluster = throughput × num_threads × batch_lines × device_per_thread × 端数 / 60`
- 现网 throughput 配置按旧 per-thread 措辞（`rows_per_sec_per_table = throughput × num_threads`）调优 → 新公式 `× batch_lines × device_per_thread`，落库行数翻 `batch_lines × device_per_thread` 倍；migration note：throughput 含义从 per-thread 升级为 per-device

**Alternatives considered**：
- 1 cycle = batchLines × dpt SQL = 1 tick：user rejected，2026-08-31（commit 3 选项 B）
- for 循环内每个设备算 1 tick：user rejected，2026-08-31（commit 3 选项 C）
- `throughput` 保持"per-thread sampler/min"语义：与新业务意图脱钩，用户需心算 dpt 因子，不推荐

### Decision 7: ts 列按 **整步语义** 递增生成 `batch_lines` 个（业务意图：单 SQL 覆盖时间窗口 = `batch_lines × ms_step`）

**Decision**：`batch_lines > 1` 时，ts 列按 `ms_step` 间隔（**整步语义**）递增生成 N 个时间戳，覆盖所有 5 mode + bind 分支。**单 SQL 覆盖时间窗口 = `batch_lines × ms_step`**；与 `throughput` 配对实现"每设备每秒钟入库 N 行"业务意图。

**整步 vs 分摊语义对比**：
- **整步语义**（本 DCR 采用）：每行 ts 间隔 = `ms_step`，单 SQL 覆盖时间窗口 = `batch_lines × ms_step`。`throughput=1/min + batch_lines=60 + ms_step=1000ms` → 每设备 1 行/秒（60 × 1s = 60s 窗口）
- **分摊语义**（D-24 落地实现，**gap #6 修复**）：每行 ts 间隔 = `ms_step / batch_lines`，单 SQL 覆盖时间窗口 = `ms_step`。同样配置下只覆盖 1 秒（60 × 1/60s = 1s 窗口），与"每设备 1 行/秒"业务意图不符

**Rationale**：
- **业务意图**：每 device 1 文件 + 同 device 多时间戳拼 1 SQL 减少 open/close = `batch_lines` 把时间窗口 `batch_lines × ms_step` 内数据拼 1 SQL 入库
- **典型配对**：`throughput=1/min + batch_lines=60 + ms_step=1000ms` = 单 SQL 覆盖 60s 时间窗口，每分钟每设备 1 条 SQL → 1 行/秒/设备（用户确认，2026-08-31）
- **gap #5 修复**：`_build_inline_sql_preprocessor_script` bind 分支（`write_groups.py:181`）当前整批共用一个 ts，改为递增 N 个
- **gap #6 修复**：源码 5 处 `+ i × (msStep / batchLines)` 改为 `+ i × msStep`：
  - `write_groups.py:260`（inline 主路径）— `r * (msStep / Math.max(1, batchLines))` → `r * msStep`
  - `write_groups.py:667`（batch_prepared bind）— `i * msStep / max(1, batchLines)` → `i * msStep`
  - `write_groups.py:811`（batch_prepared legacy）— `i * msStep / batchLines` → `i * msStep`
  - `rest_write_groups.py:253`（schemaless bind 分支）— `+ b * msStep / max(1, batchLines)` → `+ b * msStep`
  - `rest_write_groups.py:330-339`（schemaless 主路径）— `+ b * msStep / max(1, batchLines)` → `+ b * msStep`
- **migration 影响**：现网 fixture 若按"分摊语义"调优 ms_step 配置，需重新校准（ms_step = 用户期望单行间隔，非"窗口 ÷ batch_lines"）。建议 commit 7 smoke 实测两 fixture 旧新配置对比落库时间窗口确认

**Alternatives considered**：
- 用 `long ms_step_纳秒` + 纳秒精度：与 KaiwuDB `timestamp` 精度一致，秒级已足够，不推荐
- 给每行独立采样 ts（而非按 ms_step 固定间隔）：时间戳发散、违反 D-24 决策，不推荐

### Decision 8: bind 分支 tag_set = 所有 ptag + regular_tag

**Decision**：schemaless bind 分支（`rest_write_groups.py:244-248`）InfluxDB Line `tag_set` 当前只填 ptag，改为填所有 ptag + regular_tag。

**Rationale**：
- spec §2.0 L145 已声明"tag_set 部分仍按所有 ptag + regular_tag 填"
- design Decision 8（col-tag-bind-write 2026-08-05）原意图一致，但 bind 分支实装时漏掉
- 非 bind 分支（`rest_write_groups.py:330-337`）已实现全填，bind 分支对齐

**Alternatives considered**：
- 维持 bind 分支只填 ptag：违反 spec 措辞、multi-tag fixture 静默丢 rtag，不推荐
- 用 `tagMap.putAll(...)` 批量填：与现 ptag-only 实现等价差异不大，无额外收益

### Decision 9: `single_insert` / `batch_insert` / `single_prepared` bind 分支生效

**Decision**：`generate_write_thread_groups`（`write_groups.py:957-1201`）中 `single_insert` / `batch_insert` / `single_prepared` 三个 mode 在 `col_tag_bind_mode=True` 时走 bind 分支：

- `single_insert` / `batch_insert`：调用 `_build_inline_sql_preprocessor_script(col_tag_bind_mode=True)`（`gap #3` 修复）
- `single_prepared`：调用 `_build_batch_prepared_bind_preprocessor_body`（`gap #3` 修复；首次生成 prep body）；若 `batch_lines > 1` 同时 `bind_mode=True` → ValueError（schema R-PAR-016 对称约束兜底）

**Rationale**：
- 消除 3 mode 静默错配
- 与 `batch_prepared` 路径已有的 bind 分支实现对齐
- `single_prepared` 新增 prep body 引入 JSR223PreProcessor overhead（每 tick 多 1 次 prep 调度）— spec §2.2 接受

**Alternatives considered**：
- 维持 3 mode 不读 `col_tag_bind_mode`：gap #3 永存，不推荐
- 在 `_build_direct_insert_components` 加 bind 分支 + `single_prepared` 单独实现 prep body：散在多处，集中装配逻辑上提到 `generate_write_thread_groups` 更可控

## Open Questions

### 待 review ⏳

1. **`single_prepared` 新增 prep body 性能影响**：每 tick 多 1 次 JSR223PreProcessor 调度，JMeter 5.6.3 实测未跑；smoke 阶段观察 throughput 偏差
2. **D-17 JDBC bind path 真集群 smoke**：本 DCR commit 7 必跑；若发现落库行数不符合 `rows_per_sec_cluster × test_duration` 公式则升 severity

## Risks

| 风险 | 缓解 |
|---|---|
| 5 mode 笛卡尔积爆炸（40 组合）pytest 无法全覆盖 | pytest 选代表性边界 case；其他靠 fixture smoke 跑全量；commit 切分每 commit 独立验 |
| 现有 `test_model_col_bind.yaml` dpt=2 暴露 gap #1，commit 2 修复后 JMX 变化 | `test_main_col_bind.py` 集成 case 期望值同步改（`__SHARED_MEM_*_bind` size 2→4） |
| throughput 定义变更（`× batch_lines × dpt`）影响现网配置 | spec §2.0 L131 + §2.2 显式公式；migration note：throughput 应除以 `batch_lines × dpt` |
| `single_prepared` 新增 prep body 性能影响 | commit 7 smoke 跑 batch_insert + dpt=2 + bind=true + bind=false 对照，throughput 偏差 ±10% 接受 |
| ptag-runtime-derived DCR 已合并入本 DCR → 无此风险 | 不适用 |
| D-17 真集群落库行数不符公式 | commit 7 smoke 必跑；server 端 `count(*)` 二次断言；落库失败则升 blocker 不 archive |
| **gap #6 ts 整步 vs 分摊语义**：现分摊语义与业务意图不符 | 源码 5 处改 `+ i × msStep`（commit 3/4/5 合并落地）；fixture ms_step 配置需重新校准（user 已确认整步语义优先，分摊语义回归视为 regression） |

## Migration Plan

| commit | 任务 | 验证 |
|---|---|---|
| 1 | spec delta + WriteConfig `check_single_modes_batch_lines_one` + DCR 5 件套 | pytest 不 regress |
| 2 | SetupTG bind sampler 双层 for | 4 单测 case + 现有 `test_model_col_bind.py` 期望值同步 |
| 3 | `_build_inline_sql_preprocessor_script` dpt for + bind ts 递增 + **gap #6 整步语义**（line 260 改 `r * msStep`） | 4 单测 case |
| 4 | `_build_batch_prepared_*_preprocessor_body` dpt for + **gap #6 整步语义**（line 667/811 改 `i * msStep`） | 3 单测 case |
| 5 | `_build_rest_write_preprocessor_script` dpt for + bind tag_set 补 regular_tag + **gap #6 整步语义**（line 253/330-339 改 `+ b * msStep`） | 4 单测 case |
| 6 | `generate_write_thread_groups` 三 mode 走 bind 分支 | 6 单测 case |
| 7 | fixture + pytest + smoke 真集群 5min | pytest 691/691 + smoke 落库行数 `count(*) ≈ rows_per_sec_cluster × test_duration` |
| 8 | openspec-archive-change + todolist.md 同步 | openspec-verify-change 通过 |

commit 顺序敏感：commit 1 必须先于 commit 2-7；commit 2-7 之间可乱序（每 commit 独立验证）。