# ptag 第一列 runtime 派生 `{threadNum}_{deviceNum}` 格式

## Why

`col-tag-bind-write` 路径（2026-08-05 起 8 commits + 4 fix）下，`ptag_varchar_1` 第一列的取值仍由 fixture 的 `val_range` enum / `seed_num` 派生。SetupTG / WriteTG 仅**第一 ptag 覆盖**成 `deviceIdentifier(deviceNumber)`，且 `device_per_thread` 字段当前**形同虚设**：

- SetupTG `for t in 0..numThreads` 只产 `numThreads` 个 SharedMemory key
- WriteTG PreProcessor 使用 `calculateDeviceNumber(threadNum, ..., r)`，`r ∈ [0, batchLines)` 而非 `[0, device_per_thread)`
- 实测 `num_threads=20, device_per_thread=25` 仅生成 20 个 distinct ptag 值（KaiwuDB `count(distinct ptag_varchar_1) = 20`），期望 500

业务层诉求：ptag 第一列按 `{threadNum}_{deviceNum}` 格式生成，让每线程真正负责 `device_per_thread` 个独立设备；`device_per_thread` 字段由此不再是装饰性配置。

主 spec 当前隐含走 val_range enum + calculateDeviceNumber 覆盖路径，与"每线程管一组设备"业务期望不符。

## What Changes

启用 col_tag_bind_mode 时，ptag 第一列 runtime 派生：

| 维度 | 现行为 | 新行为 |
|---|---|---|
| ptag #1 值格式 | `{deviceCode}`（calculator 输出如 `device_1, device_2`） | `{threadNum}_{deviceNum}`（如 `0_1, 0_2, 1_1, ..., 19_25`） |
| 唯一 deviceCode 数 | `numThreads × batchLines`（dpt 失效） | `numThreads × devicePerThread`（dpt 真生效） |
| SetupTG SharedMemory key 数 | `numThreads` | `numThreads × devicePerThread` |
| ThreadGroup 循环 | 每个 thread 跑 N 次（按 batch_lines/batch 摊销） | 每 thread 跑 `devicePerThread` 次；每 cycle 写 batchLines 行同一 deviceCode |
| fixture 第一 ptag 字段 | `val_range` + `seed_num` 必填（orchestrator 仍生成列种子，但 runtime 覆盖） | `val_range` + `seed_num` **删**（runtime 完全派生，第一 ptag 不读列种子） |
| ptag #2+ 列 | 仍走 val_range + seed_num | 仍走 val_range + seed_num（不变） |
| hash 分组 | `hash(ptag_tuple) mod num_threads`（Decision 4 历史决策） | 废止 —— SetupTG 已经按 deviceCode 直接烤 key，无须 hash 映射 |

## Capabilities

### New Capabilities

- `ptag-runtime-derived`：ptag 第一列 runtime 按 `{threadNum}_{deviceNum}` 派生，device_per_thread 真生效

### Modified Capabilities

- `col-tag-bind-write`：原 Decision 4（`hash(ptag_tuple) mod num_threads` 分组）**失效** —— 已由 D-21 (commit `fcaef6f`) 改为 per-deviceCode SharedMemory 直接 lookup，spec 需同步删除 Decision 4 引用

## Impact

**Affected code**：

- `src/utils/preprocessor_helpers.py`：新增 helper `ptag_runtime_value(thread_num, device_num)` → Python + Groovy 双语
- `src/jmx_skeleton_generator/generators/shared_memory_setup.py::BindSetup`：双层 for-loop（t + b），每 cycle 烤 `deviceCode = "{t}_{b+1}"`
- `src/jmx_skeleton_generator/generators/write_groups.py`：batch_prepared PreProcessor 改按 `deviceIndex` 外层循环，每个 deviceIndex 写 batchLines 行；第一 ptag 用 helper
- `src/direct_insert_write/preprocessor_generator.py`：同上
- `src/jmx_skeleton_generator/generators/rest_write_groups.py`：schemaless InfluxDB Line 同步
- `tests/kwjdbc_svt/fixtures/test_model_*.yaml`：5 个 fixture 删第一 ptag 列的 `val_range` + `seed_num`
- `docs/specs/kwdb-svt-test-plan-generator-spec.md` §col_tag_bind_mode 段：插入「ptag #1 runtime 派生约定」+ 关联本 DCR + 删除 Decision 4 hash 分组引用
- `tests/jmx_skeleton_generator/test_setup_bind_sampler.py` 等单测：dpt 展开 + 派生格式覆盖
- `tests/kwjdbc_svt/test_main.py` / `test_main_col_bind.py` / `test_main_routes_schemaless_influxdb.py` 集成测：fixture 删字段后必须仍 parse + 生成通过

**Affected docs**：

- 主 spec §col_tag_bind_mode 段（line ~138）
- `docs/designs/kwdb-svt-test-plan-generator-design.md` §4.3 bind path 设计：清 hash 分组

**Migration 影响**：

- 现存 `col_tag_bind_mode=true` 用户配置需删第一 ptag `val_range` + `seed_num`
- 任何依赖 `device_1` 格式的 Query SQL / 现有 fixture 需更新
- pytest 中硬编 `seed_num=5` 期望值的 case 同步改

## Open Questions

### 已收敛 ✅

1. ptag 命名格式：`{threadNum}_{deviceNum}`（user confirmed，2026-08-28）
2. device_per_thread 真生效：SetupTG / WriteTG 循环展开 `numThreads × dpt`（实测 smoke 后续 review）
3. 第二 ptag+ 列：仍走 val_range + seed_num（不动）

### 仍待 review ⏳

1. LoopController.loops 跟 throughput 调度的交互：现 spec §col_tag_bind_mode 段行 ~135 写「ConstantThroughputTimer calcMode=0」，与 dpt 展开后 throughput 是按 per-thread 还是 per-device 衡量？（建议：仍 per-thread，与原 spec 对齐；per-cycle 写 batchLines 行 → effective throughput = `numThreads × write_throughput`，每个 device 平均 `write_throughput / dpt` 行/秒）
2. 多端协同（多 SVt-test-server 拼接）：spec §3.2 写「下一发压端起始 = 本端 + numThreads × dpt」，与原 Decision 4 hash 分组冲突，待 review 验证
3. fixture `primary_tags` 单元素时 `seed_num`/`val_range` 字段是否整个字段段删除（变空）还是保留 `col_type` + `type_proportion` 二字段（推荐后者 —— 减少 schema 改动面，pydantic 字段保留但 runtime 不读）
