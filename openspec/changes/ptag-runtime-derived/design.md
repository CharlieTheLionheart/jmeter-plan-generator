# Design: ptag 第一列 runtime 派生 `{threadNum}_{deviceNum}` 格式

## Context

`col-tag-bind-write` 落地 commit 1-7 + 4 fix (D-9 ~ D-17) 后，bind path 的 SharedMemory 直接按 deviceCode lookup（D-21 弃用 hash 分组），但 SetupTG / WriteTG 仍硬编码 `for t in 0..numThreads`，`device_per_thread` 字段未参与 runtime 扩展。后果：

- `num_threads=20, device_per_thread=25` 应产 500 unique deviceCode，实测 20（KaiwuDB `count(distinct ptag_varchar_1) = 20`）
- 业务语义「设备 1 关心列 1-5 / 设备 3 关心列 6-10」要求每 device 有独立 ptag 值 + 独立列子集
- 当前 20 个 ptag 平均摊销到 500 行，达不到 per-device 隔离

本 change 把 `device_per_thread` 字段从「用户配置 + runtime 装饰」提升为「runtime 真参与」。

## Decisions

### Decision 1: ptag #1 命名格式 = `{threadNum}_{deviceNum}`

**Decision**：第一 ptag runtime 派生为 `"{threadNum}_{deviceNum}"` 字符串。

**Rationale**：
- threadNum ∈ [0, numThreads)（0-indexed；JMeter ThreadGroup `threadNum` API）
- deviceNum ∈ [1, devicePerThread]（1-indexed；与 `calculateDeviceNumber` 公式对齐：`deviceNumber = device_start + thread_num * device_per_thread + (row_index % device_per_thread)`，`row_index ∈ [0, devicePerThread)`）
- 例：`num_threads=20, device_per_thread=25` → `"0_1", "0_2", ..., "19_25"`（500 unique strings）

**Alternatives considered**：
- `device_{n}` （旧 DeviceIdentifier 输出）—— 已被 DCR author 否定，丢失 threadNum 维度
- `device{threadNum:02d}_{deviceNum:02d}` —— zero-pad 字符串排序更稳，但 JMeter Groovy `String.format` 性能与非格式化差异可忽略；为 readability 不补零

### Decision 2: SetupTG 双层 for-loop 展开 `numThreads × devicePerThread` SharedMemory key

**Decision**：SetupTG 把 `for t in 0..numThreads` 改 `for t in 0..numThreads: for b in 0..devicePerThread`，每个 iteration：
1. `deviceCode = "{t}_{b+1}"`（新格式）
2. 烤到 `__SHARED_MEM_{db}_{table}_bind[deviceCode] = {col_names: [...], row_values: [batchLines 行]}`

**Rationale**：
- SetupTG 一次完成所有 `numThreads × devicePerThread` key 的填充；WriteTG runtime 按 deviceCode 直接 lookup，无需 hash
- `batchLines` 仍每 device 烤 N 行（per-(deviceCode, b) 取不同 row seed，原 D-25 行为保留）

**Alternatives considered**：
- SetupTG 仅烤 `numThreads` 个 key，runtime devicePerThread 索引按旁路算 —— 与原 Decision 4 hash 分组等价，违反 D-21 key=deviceCode 决策
- SetupTG 烤 Lazy key —— JMeter WriteTG 并发访问 SetupTG lazy 写会触发 JMeterUtils 竞态，禁用

### Decision 3: WriteTG 循环 per-thread 跑 `devicePerThread` 次

**Decision**：ThreadGroup `LoopController.loops = numThreads × devicePerThread`（schedule 模式），每线程按 ThreadGroup 线程均摊执行 `devicePerThread` 次循环；每次循环 WriteTG PreProcessor：
1. 计算 `deviceIndex = (loop_iter % devicePerThread) + 1`
2. `deviceCode = "{threadNum}_{deviceIndex}"`
3. 写 `batchLines` 行同一 deviceCode

**Rationale**：
- JMeter ThreadGroup 默认按 thread 数量均摊总 loop，`loops = numThreads × dpt` ÷ `numThreads` = `dpt` 次 / 线程 ✓
- `deviceIndex` 派生避开 `__jmeter.IterationNum`（1-indexed, race-prone if JMeterMixedThreadGroup）改用 `(loop_iter % dpt) + 1` 形式更安全
- 仍保留原 `ConstantThroughputTimer calcMode=0`（spec §3.2 段），per-thread 频率独立稳态

**Alternatives considered**：
- `for deviceIndex in 1..devicePerThread` 跑多 Write TG —— 装配复杂度高；Schedule 单 TG 足够
- 用 `__jmeter.ThreadNum`/`__jmeter.IterationNum` —— 1-indexed 且跟 LoopController 调度耦合，改用 `(loop_iter % dpt) + 1` 更稳

### Decision 4: 第一 ptag fixture 字段删 `val_range` + `seed_num`

**Decision**：fixture YAML 第一 ptag `col_type` + `type_proportion` 保留（仍用于 DDL 类型推导），但 `val_range` + `seed_num` 删除。pydantic `ColTypeConfig` 字段保留向后兼容（其他列仍可用），orchestrator 看到第一 ptag 没 `val_range` → 不生成列种子文件。

**Rationale**：
- orchestrator 阶段不再为第一 ptag 烧 enum 派生列种子（避免浪费 + 避免 runtime 仍尝试读 `vals[t % vals.size()]` 索引）
- 第二+ ptag 字段全保留，多 ptag 场景仍走 val_range 派生

**Alternatives considered**：
- 改 `PrimaryTagColTypeConfig` 类型，把 `val_range` / `seed_num` 字段从 Pydantic 模型中删除 —— 兼容面更广，但 Pydantic schema breaking change；倾向于保留字段（向后兼容）+ fixture 不填即可

### Decision 5: `hash(ptag_tuple) mod num_threads` 决策失效

**Decision**：原 DCR `col-tag-bind-write` Decision 4（2026-08-05 设计）的 hash 分组在 D-21 commit `fcaef6f` 改为 per-deviceCode key 直接 lookup 后，**实际已失效**。本 change 显式从主 spec 删除 Decision 4 引用，避免后续 reader 误把 Decision 4 当现行设计。

**Rationale**：
- Decision 4 与 D-21 决定同时存在，spec 读者易混淆
- 显式删除 = 让 spec 与代码同步

## Open Questions

### 待 review ⏳

1. **多端协同设备号推进**：spec §3.2 行 ~158 写「下一发压端起始设备号 = 本端 + numThreads × dpt」隐含 device 序列 1..N 连续。本 change 把 ptag 格式改 `{threadNum}_{deviceNum}` 是 thread-local 命名，跨端拼接需各自推导 thread 范围；与原 spec 该段需 review 是否仍以"deviceNumber 连续"语境为准
2. **shig fixture (test_model_shig.yaml) 的 FK 链路**：`ptag_varchar_1` 用 `[A-Z][0-9]{2,4}$` + `seed_num=50`，第二 ptag 用 `enum:op_group_1..4` + `seed_num=4`。删第一 ptag `val_range`/`seed_num` 后，第一 ptag runtime 派生 = `{threadNum}_{deviceNum}`（如 `0_1, 0_2, ...`），与既有 FK 引用（`ptag_varchar_1_1, ..., ptag_varchar_1_50`）的 `val_range="^[A-Z][0-9]{2,4}$"` 不再匹配 —— 需重写 shig fixture 的 FK 引用列 / 全部删 FK
3. **compose 测试用例**：col-bind pytest 用 `seed_num=5 + num_threads=2` 期望 `__SHARED_MEM_*_bind` 5 行；本 change 后期望 = `2 × dpt` 行（如 dpt=2 → 4 行；dpt=4 → 8 行）。pytest 需同步更新

## Risks

| 风险 | 缓解 |
|---|---|
| 多 ptag fixture 第一 ptag 改 runtime 派生后，FK 链断 | shig fixture 重新设计 FK 链路；其他 fixture 无 FK |
| 5 fixture 删 `val_range`/`seed_num` 与 orchestrator 兼容（fixture 仍 parse 过） | pydantic 字段保留，fixture 不填即可 |
| LoopController.loops 扩到 `numThreads × dpt` 影响 throughput 浮动 | 保留 ConstantThroughputTimer per-thread 调度，per-cycle 写 batchLines 行；log 内 throughput 监测 |
| 旧 write_groups PreProcessor `(r=0..batchLines)` 同步改 per-deviceIndex 后，pytest 期望值更新面广 | commit 2 含集成测 + pytest 同步更新 |

## Migration Plan

1. commit 1 — DCR + spec 关联（仅文档）
2. commit 2 — 代码 + 测试（5 个生成器改写 + 单测 + 集成测）
3. commit 3 — fixture 清理（5 fixture 删字段）
4. commit 4 — 真集群 5min smoke（dist ptag = 500 验证）

无需回滚；commit 3 与 commit 4 顺序敏感（commit 4 在 commit 3 之后）。
