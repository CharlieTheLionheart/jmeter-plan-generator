# Proposal: col-tag-bind-per-group-subsets

## What Changes

把 col_tag_bind_mode 下"每组共享同一组列子集"的设计改为"每组不同列子集"——按 `group_id` 决定列起始 offset，让不同 hash group 真正写**不同**非空列（设备 1 关心列 1-5，设备 3 关心列 6-10，等等）。

具体改动：
- `src/jmx_skeleton_generator/generators/shared_memory_setup.py::BindSetup` 写 `colNamesSubset` 时按 `group_id * col_num_per_tag` 取 offset（`dataColumns[(groupId * colNumPerTag) % dataColumns.size()..]`），wrap-around 处理 `col_num_per_tag * num_threads < dataColumns.size()` 的情况
- 新增 pytest case `test_bind_subset_per_group_offset` 验 num_threads=2 + 10 data_cols + col_num_per_tag=5 → group 0 取 [col_bool_1, col_char_1, col_float4_1, col_float8_1, col_float8_2]、group 1 取 [col_int4_1, col_int8_1, col_timestamp_1, col_varchar_1, col_varchar_2]
- smoke 反退化断言升级：DB `SELECT count(*) GROUP BY ptag` 应显示不同 group 的 bind 列**不重叠**（D-16 移除前的简化版断言只验"≥2 个不同 ptag"，升级版验"每个 group 自己的非空列不重叠"）
- 设计文档 `docs/superpowers/specs/2026-08-05-col-tag-bind-write-design.md` §4.3 简化说明段落更新（"原计划"→"现"）

**业务语义**：bind 模式的真实价值是"ptag 组合 → 列子集"映射——每个 ptag 只关心自己相关的列。设备 1 关心列 1-5，设备 3 关心列 6-10，**不是"全列都激活但 99% NULL"**（design §1 Context 已说明）。

**回归影响**：
- 之前 fixture 用 `num_threads=2 + device_per_thread=2 + seed_num=5` 跑出 10 行 device_1+device_3，**所有 bind 列**都非 NULL、**所有非 bind 列**都 NULL。改后：
  - device_1 写 col_bool_1 + col_char_1 + col_float4_1 + col_float8_1 + col_float8_2（非 NULL），col_int4_1 + col_int8_1 + col_timestamp_1 + col_varchar_1 + col_varchar_2（NULL）
  - device_3 写 col_int4_1 + col_int8_1 + col_timestamp_1 + col_varchar_1 + col_varchar_2（非 NULL），col_bool_1 + col_char_1 + col_float4_1 + col_float8_1 + col_float8_2（NULL）
- 整体行数不变（10 行），但 **device_1 与 device_3 的非空列互补**——这才是 bind 的真实业务语义
- col_num_per_tag=5 + num_threads=2 = 10 列刚好覆盖（无需 wrap-around）；fixture 数据列数 10 正好对齐

**反退化 §8.7（单元）**：已通过 `test_hash_distribution_no_degeneracy` 验 hash 分布。**新增** `test_bind_subset_per_group_offset` 验列子集按 group_id 计算正确。

**反退化 §8.8（冒烟）**：升级——DB 验"device_1 写的 5 列 ≠ device_3 写的 5 列"（不重叠），与现有"≥2 个不同 ptag"并存。

## Capabilities

### New Capabilities
- `col-tag-bind-per-group-subsets`: bind 模式下每组 hash 分组写**不同**列子集（按 group_id offset），不再共享前 N 列

### Modified Capabilities
（无——spec §col_tag_bind_mode 段只描述"列子集"概念，"每组不同列"是同一 requirement 的实现细节；不需改 spec.md）

## Impact

**Affected code**：
- `src/jmx_skeleton_generator/generators/shared_memory_setup.py::BindSetup`（行 197 `colNamesSubset = dataColumns.take(colNumPerTag)` 改为按 `group_id` offset）
- `tests/jmx_skeleton_generator/test_setup_bind_sampler.py`（新增 `test_bind_subset_per_group_offset` case）
- `docs/superpowers/specs/2026-08-05-col-tag-bind-write-design.md` §4.3 简化说明更新
- `openspec/changes/col-tag-bind-write/tasks.md` 加 §11 follow-up 任务（标记 D-15 设计意图修正）

**Affected APIs**：（无）

**Affected fixtures**：
- `tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml` 数据列保持 10 列不变
- `tests/kwjdbc_svt/fixtures/test_cfg_col_bind.yaml` 保持 `col_num_per_tag: 5`、`num_threads: 2`（刚好对齐）

**风险**：
- 现有 commit 5/6 + D-12/D-13/D-14 smoke 验过的行为会变——之前"device_1 与 device_3 都写同一组列"会变成"互补写不同列"。**这是 bug 修复，不是 behavior regression**
- pytest 全量 745/745 维持（新增 1 case）
- smoke 反退化断言升级：JTL 仍 10 行 + device_1/device_3 分布不变；DB 验证由"count=10"升级为"device_1 写的 5 列 与 device_3 写的 5 列不重叠"

<success_criteria>
- pytest 746/746 pass（745 + 新增 1 case）
- smoke iot_monitor.meters：10 行，device_1 写 col_bool_1/char_1/float4_1/float8_1/float8_2 非 NULL，device_3 写 col_int4_1/int8_1/timestamp_1/varchar_1/varchar_2 非 NULL；两类列互不重叠
- design §4.3 简化说明段落更新
- 现有 pytest 全量不 regress
</success_criteria>

<unlocks>
- 完成此 DCR 后，col-tag-bind-write 8 commits 的语义才是设计意图真实现（之前 commit 5/6 + D-12/D-13/D-14 修复的是"bind 路径能跑起来"，但跑出来的列子集是错的简化版）
- D-15（full-row path escapeLineValue PatternSyntaxException）独立于本 DCR，按原计划归档 follow-up
- D-17（JDBC bind path smoke）独立于本 DCR，按原计划归档 follow-up
</unlocks>
