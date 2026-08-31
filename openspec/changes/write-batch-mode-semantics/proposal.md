# write-batch-mode-semantics: 5 mode 业务含义 + batch_lines + device_per_thread 统一

## Why

主 spec `docs/specs/kwdb-svt-test-plan-generator-spec.md` §2.0 L132-137 把 5 mode 按 T0/T1/T2 JDBC 形态分类（single_insert/batch_insert/single_prepared/batch_prepared/schemaless），与实际业务期望脱钩：

1. **single/batch 命名 vs 含义冲突**：业务期望 "single = 1 行/SQL"、"batch = N 行/SQL"，但当前 `single_insert` 与 `batch_insert`（`batch_lines=1` 时）实际都写 1 行。命名无法直接表达业务含义
2. **`batch_lines` 字段作用域窄**：当前 `batch_lines` 仅 batch 类模式生效（[spec L147](docs/specs/kwdb-svt-test-plan-generator-spec.md#L147)），`single_insert` 已有 R-PAR-016 限制（`models.py:382-389`），但 `single_prepared + batch_lines > 1` schema 未禁（运行时未定义行为，**gap #4**）
3. **`device_per_thread` 对 single_insert/single_prepared 失效**（**gap #3**）：spec §2.0 L148 措辞「每线程负责写入的设备数」对 `single_*` 模式不生效；`col-tag-bind-write` DCR 已识别 bind 路径下 dpt 应真生效，但非 bind 路径仍硬编码一个设备
4. **SetupTG bind sampler 仅烤 `numThreads` 个 entry**（**gap #1**）：`shared_memory_setup.py:232` 的 `for (int t = 0; t < numThreads; t++)`（共 numThreads 次），而 WriteTG bind 分支按 `(threadNum, devicePerThread, 0)` 固定取 index=0 → 当 `device_per_thread > 1` 时 SetupTG 不烤 numThreads×dpt 个 deviceCode，部分设备找不到 SharedMemory key（bind 分支静默错配）。现有 `tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml`（dpt=2）已暴露此 bug
5. **bind 分支 InfluxDB Line tag_set 缺 regular_tag**（**gap #2**）：`rest_write_groups.py:244-248` bind 分支只填 ptag，违反 spec §2.0 L145 "tag_set 部分仍按所有 ptag + regular_tag 填"约定（design Decision 8）
6. **inline bind 分支 ts 单值**（**gap #5**）：`_build_inline_sql_preprocessor_script` bind 路径（`write_groups.py:181`）仅 `baseTime + batchSeq * msStep`，整批共用一个 ts，与 D-24 schemaless bind 分支"batch_lines 个递增 ts"不一致
7. **ts 递增分摊语义错配业务意图**（**gap #6**）：现源码 4 处用 `+ i × (msStep / batchLines)`（**分摊语义**——每行 ts 间隔 = `ms_step / batch_lines`，10 行覆盖 0.9 秒而非 9 秒）；业务意图是**整步语义**——每行 ts 间隔 = `ms_step`，`batch_lines × ms_step` = 单 SQL 覆盖时间窗口。`throughput=1/min + batch_lines=60 + ms_step=1000ms` 应每设备 1 行/秒（60 行覆盖 60s），现分摊语义只覆盖 1 秒。`write_groups.py:260/667/811` + `rest_write_groups.py:253/330-339` 5 处待改

## What Changes

重新定义 single/batch 业务含义为「每 SQL 行数」，统一 5 mode × batch_lines × device_per_thread 三维语义：

| 维度 | 现行为 | 新行为 |
|---|---|---|
| single/batch 业务含义 | 命名按 JDBC 形态（T0/T1/T2）分类；行数另由 `batch_lines` 字段表达 | 命名按"每 SQL 行数"重定义：single = 1 行、batch = N 行 |
| `batch_lines` 字段作用域 | 仅 batch 类模式生效；`single_insert` 由 R-PAR-016 强制=1；`single_prepared` schema 未禁 | 覆盖全部 5 mode；`single_*` 由 R-PAR-016 对称约束强制=1 |
| 单 sampler 写多少行 | `batch_lines` 行 × 1 个 device（每 SQL 跨设备，文件 open/close 多次） | `batch_lines × device_per_thread` 行；**每 device `batch_lines` 个时间戳拼 1 条 SQL 入库**（KaiwuDB 时序底层每 device 一个文件，跨设备单 SQL 文件 open/close 性能差） |
| 落库行数公式 | `rows_per_sec_per_table = throughput × num_threads` | `rows_per_sec_per_table = throughput × num_threads × batch_lines × device_per_thread / 60`；**每设备入库速率** = `throughput × batch_lines / 60` 行/秒 |
| throughput 业务语义 | 每个写入线程的目标吞吐量（sampler/min/thread） | **每个设备的目标吞吐量**（per-device SQL/min）；`ConstantThroughputTimer calcMode=0` 配 `throughput` = 每线程每分钟 sampler 触发 = 每设备每分钟 SQL 数（因 1 sampler = dpt SQL） |
| throughput tick 定义 | 1 sampler = 1 throughput tick（不变） | 同左；但每个 tick 落库行数 = `batch_lines × device_per_thread`；**单 SQL 覆盖时间窗口** = `batch_lines × ms_step`（如 throughput=1/min + batch_lines=60 + ms_step=1s = 单 SQL 覆盖 60s = 1 行/秒/设备） |
| SetupTG bind sampler dpt 展开 | 单层 `for (int t = 0; t < numThreads; t++)` | 双层 `for (int t = 0; t < numThreads; t++) { for (int b = 0; b < devicePerThread; b++) { ... } }`，每 cycle `deviceIndex = deviceStart + b`，烤齐 `numThreads × devicePerThread` 个 SharedMemory key（**gap #1 修复**） |
| bind 分支 InfluxDB Line tag_set | 只填 ptag | 所有 ptag + regular_tag（**gap #2 修复**） |
| bind 分支 ts 生成（inline script） | 整批共用一个 ts | 按 ms_step 间隔递增生成 `batch_lines` 个 ts（**gap #5 修复**） |
| ts 递增语义 | **分摊语义**：每行 ts 间隔 = `ms_step / batch_lines`（10 行覆盖 0.9s） | **整步语义**：每行 ts 间隔 = `ms_step`（10 行覆盖 9s）；单 SQL 覆盖时间窗口 = `batch_lines × ms_step`（**gap #6 修复**，改 5 处源码） |
| `single_*` + `col_tag_bind_mode=true` | 静默错配（`_build_direct_insert_components` 与 `single_prepared` 路径不读 `wc.col_tag_bind_mode`） | 走 bind 分支 prep body（**gap #3 修复**） |

## Capabilities

### New Capabilities

- `write-batch-mode-semantics`：5 mode × batch_lines × device_per_thread × col_tag_bind_mode 统一语义

### Modified Capabilities

- `col-tag-bind-write`：SetupTG bind sampler 烤齐 `numThreads × devicePerThread` 个 key（**gap #1**）；schemaless bind 分支 tag_set 补 regular_tag（**gap #2**）；bind 分支被 `single_*` 模式消费（**gap #3**）
- ~~`ptag-runtime-derived`~~：**已合并入本 DCR**（不再独立推进；ptag 第 1 列 runtime 派生 + SetupTG 双层 for + deviceIndex 与 device_start 绑定等核心规则全部归入本 DCR）

## Impact

**Affected code**：

- `src/config_parser/models.py::WriteConfig.check_single_insert_batch_lines` → 改名为 `check_single_modes_batch_lines_one`，覆盖 `single_insert ∪ single_prepared`
- `src/jmx_skeleton_generator/generators/shared_memory_setup.py::_build_bind_sampler_groovy`：`for (int t = 0; t < numThreads; t++)` 改 `for (int t = 0; t < numThreads; t++) { for (int b = 0; b < devicePerThread; b++) { ... } }` 双层 for
- `src/jmx_skeleton_generator/generators/write_groups.py`：
  - `_build_inline_sql_preprocessor_script`（`line 50-310`，single_insert/batch_insert）外层套 `for d in device_start..(device_start + dpt - 1)` + bind 分支 ts 按 ms_step 间隔递增
  - `_build_batch_prepared_*_preprocessor_body`（`line 556-820`）外层套同 for 循环
  - `generate_write_thread_groups`（`line 957-1201`）：让 `single_insert` / `batch_insert` / `single_prepared` 在 `col_tag_bind_mode=True` 时走 bind 分支
- `src/jmx_skeleton_generator/generators/rest_write_groups.py::_build_rest_write_preprocessor_script`：`schemaless` 模式外层套同 for 循环 + bind 分支 tag_set 补 regular_tag
- `src/utils/preprocessor_helpers.py`：不变（ptag 第 1 列值用内联 GString `"${threadNum}_${deviceIndex}"` 拼接，不抽 helper）

**Affected docs**：

- 主 spec `docs/specs/kwdb-svt-test-plan-generator-spec.md` §2.0 L130-149（字段表）+ §2.2 L320-340（吞吐量 + TG 编排）

**Affected tests**：

- `tests/jmx_skeleton_generator/test_setup_bind_sampler.py`：更新 4 case 期望 `numThreads × dpt` 个 group + 新增 deviceIndex 格式 case
- `tests/jmx_skeleton_generator/test_inline_sql_preprocessor.py`：新增 4 case
- `tests/jmx_skeleton_generator/test_batch_prepared_bind.py`：新增 3 case
- `tests/jmx_skeleton_generator/test_rest_write_bind.py`：新增 4 case
- `tests/jmx_skeleton_generator/test_write_thread_groups.py`：新增 6 case
- `tests/kwjdbc_svt/test_main.py`：新增 8 case（5 mode × bind=false/true 集成测）

**Migration 影响**：

- `col_tag_bind_mode=true` + `device_per_thread > 1` 的现网配置立即生效：SetupTG 多烤 `dpt` 倍 key，WriteTG bind 分支不再静默错配
- 现网 throughput 配置按旧公式（`rows_per_sec_per_table = throughput × num_threads`）调优 → 新公式 `× batch_lines × device_per_thread`，落库行数翻 `batch_lines × device_per_thread` 倍；建议 throughput 除以该因子以保持原落库速率
- 现有 fixture 不改：`test_model_col_bind.yaml` 的 dpt=2 暴露 gap #1，commit 2 自动修复（SetupTG 从烤 2 key 变 4 key）

## Open Questions

### 已收敛 ✅

1. 5 mode 命名维持（single_insert/batch_insert/single_prepared/batch_prepared/schemaless）— user confirmed, 2026-08-31
2. `batch_lines` 字段覆盖全部 5 mode — user confirmed
3. `R-PAR-016` 扩展为对称约束（`single_insert ∪ single_prepared` 都强制 batch_lines=1）— user confirmed
4. throughput 定义：1 sampler = 1 throughput tick；落库行数 = `batch_lines × device_per_thread` — user confirmed
5. `ms_step` 保留在 `ts_col.ms_step` 字段 — user confirmed
6. schemaless 模式：`batch_lines` = 每个 HTTP body 的 Line 数量 — user confirmed
7. **deviceIndex 语义 = 与 device_start 绑定的绝对设备号**，范围 `deviceIndex ∈ [device_start, device_start + device_per_thread - 1]` — user confirmed, 2026-08-31（修订先前 `[1, device_per_thread]` 1-indexed per-thread 局部编号）
8. **ptag 第 1 列值用内联 GString 拼接** `"${threadNum}_${deviceIndex}"`，**不**依赖 `ptagRuntimeValue` helper — user confirmed, 2026-08-31
9. **ts 整步语义**（**gap #6**）：每行 ts 间隔 = `ms_step`（非 `ms_step / batch_lines`）；单 SQL 覆盖时间窗口 = `batch_lines × ms_step` — user confirmed, 2026-08-31（合入本 DCR，不另开 DCR）

### 仍待 review ⏳

1. **D-17 JDBC bind path 真集群 smoke 缺失**：col-tag-bind-write DCR D-17 commit 仅跑过 jmeter -n + B1 assertion，未跑过真 KaiwuDB 集群验证落库行数。本 DCR commit 7 smoke 必跑：fixture 选 `test_model_col_bind.yaml` + dpt=2 + bind=true，验 `count(*) ≈ rows_per_sec_cluster × test_duration`、`count(distinct ptag) = 4`
2. **`single_prepared` 路径 prep body 首生成**：当前 `generate_write_thread_groups` 在 `single_prepared` 路径下不发射 prep body（直接 JDBCSampler Prepared Update），bind 分支需新增 `_build_batch_prepared_bind_preprocessor_body` 调用。新增 prep body 是否引入 JSR223PreProcessor overhead（每 tick 多 1 次 prep 调度）？
3. **smoke fixture 是否新建 vs 复用**：现有 `test_model_col_bind.yaml` dpt=2 已暴露 gap #1，端到端可验证；但 batch_insert + bind=true 是否在该 fixture 启用？若未启用需新增 fixture 配置