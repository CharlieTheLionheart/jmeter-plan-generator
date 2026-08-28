## ADDED Requirements

### Requirement: ptag 第一列 runtime 派生 `{threadNum}_{deviceNum}` 格式

`col_tag_bind_mode=true` 时，`primary_tags[0]`（ptag 第一列）runtime 派生为 `"{threadNum}_{deviceNum}"` 字符串：

- `threadNum ∈ [0, numThreads)`：0-indexed JMeter ThreadGroup 线程号
- `deviceNum ∈ [1, devicePerThread]`：1-indexed per-thread 设备号
- 共 `numThreads × devicePerThread` 唯一 ptag 值（如 `num_threads=20, device_per_thread=25` → `"0_1", "0_2", ..., "19_25"`）

#### Scenario：第一 ptag runtime 派生覆盖 val_range / seed_num

- **WHEN** fixture `write_config[tbl_name=X].col_tag_bind_mode = true` + `primary_tags[0]` 不带 `val_range` 与 `seed_num`（或显式空）
- **THEN** SetupTG 烤 `__SHARED_MEM_{db}_{X}_bind` 时，第一 ptag 列值取 `"{threadNum}_{deviceNum}"` 字符串，**不**读列种子 CSV
- **AND** WriteTG PreProcessor runtime 同样按 `"{threadNum}_{deviceNum}"` 拼第一 ptag，不读列种子

#### Scenario：SetupTG 烤 `numThreads × devicePerThread` 个 SharedMemory key

- **WHEN** WriteConfig 含 `num_threads=N`, `device_per_thread=D`
- **THEN** SetupTG bind sampler 烤 `N × D` 个 key 到 `__SHARED_MEM_{db}_{table}_bind`
- **AND** 每 key 对应一组列子集（`col_names` + `row_values[batchLines]`），与原 D-21 决策一致
- **AND** WriteTG PreProcessor 按当前 iteration 的 `deviceIndex` 派生 key 直接 lookup

#### Scenario：第二 ptag+ 列仍走 val_range / seed_num

- **WHEN** `primary_tags` 含 ≥ 2 列
- **THEN** 仅第一列 runtime 派生；其余列仍走 val_range / seed_num
- **AND** WriteTG PreProcessor 顺序写：第一 ptag 用 `{threadNum}_{deviceNum}`、第二 ptag+ 取 `vals[t % vals.size()]`（与原 D-21 `group_id` 决策对齐）

### Requirement: ThreadGroup LoopController 调度

`col_tag_bind_mode=true` 时，WriteTG `ThreadGroup.LoopController.loops = numThreads × devicePerThread`，每线程独立跑 `devicePerThread` 次循环（JMeter ThreadGroup 均摊总 loop 到各线程）。

#### Scenario：每线程循环 per-device

- **WHEN** ThreadGroup 循环 `loops = N × D`
- **THEN** 每个 thread 跑 `D` 次（`N × D / N = D`），每次循环写 `batch_lines` 行同一 deviceCode
- **AND** deviceIndex 派生：第 `iter` 次循环的 deviceIndex = `(iter % D) + 1`

### Requirement: fixture 字段弱化

`primary_tags[0]` 可省略 `val_range` + `seed_num`，仅保留 `col_type` + `type_proportion`（仍用于 DDL 类型推导）。Pydantic `ColTypeConfig` 字段保留向后兼容。

#### Scenario：删 val_range 后 fixture 仍 parse

- **WHEN** fixture `primary_tags[0]` 只含 `col_type: varchar(32)` + `type_proportion: 1.0`
- **THEN** Pydantic 解析通过，不抛 `ValidationError`
- **AND** orchestrator 跳列种子 CSV 生成（runtime 不读）

#### Scenario：第二 ptag 仍 val_range 强约束

- **WHEN** `primary_tags[1]` 带 `val_range: "^[A-Z][0-9]+$"` + `seed_num: 50`
- **THEN** 第二 ptag 列种子 CSV 按既有逻辑生成（不受本 change 影响）

## REMOVED Requirements

### Removal: `hash(ptag_tuple) mod num_threads` 分组决策

原 `col-tag-bind-write` DCR Decision 4（2026-08-05 proposal）规定的 `hash(ptag_tuple) mod num_threads` 分组在 `fcaef6f` (D-21, 2026-08-14) commit 后**已经实际失效** —— SetupTG bind sampler 已改按 deviceCode 直接 lookup，hash 不再参与。本 change 显式删除 spec 引用以避免后续 reader 误把 Decision 4 当现行设计。

## MODIFIED Requirements

### Modification: 主 spec §col_tag_bind_mode 段（line ~138 区域）

新增「ptag #1 runtime 派生约定」段落 + 引用本 delta spec。
