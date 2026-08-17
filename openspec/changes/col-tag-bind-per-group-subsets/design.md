# Design: col-tag-bind-per-group-subsets

## Context

前 DCR `col-tag-bind-write` 在 §4.3 简化说明段落明确收敛到"每组共享同一组列子集（`colsSubset.take(colNumPerTag)` 固定前 N 列）"——design §5 Open Question 0 已关。本 DCR 推翻这个收敛：

**业务语义**（design §1 Context 已说明）：
> "设备 ↔ 列子集"是有意义的（设备 1 关心列 1-5，其他列对它无效），并非"全列都激活但 99% 是 NULL"。

commit 5/6 + D-12/D-13/D-14 把 bind 路径修到"能跑起来"——但跑出来的列子集是**简化版**（device_1 和 device_3 都写同一组列，只 row_values 不同），**不是设计意图真实现**。DB 实测：

| group | ptag | 写过的列（非 NULL） |
|---|---|---|
| 0 | device_1 | col_float4_1, col_float8_1, col_bool_1, col_float8_2, col_char_1（按字母序前 5） |
| 1 | device_3 | col_float4_1, col_float8_1, col_bool_1, col_float8_2, col_char_1（同一组列！） |

正确语义应是：

| group | ptag | 写过的列（非 NULL） |
|---|---|---|
| 0 | device_1 | col_bool_1, col_char_1, col_float4_1, col_float8_1, col_float8_2 |
| 1 | device_3 | col_int4_1, col_int8_1, col_timestamp_1, col_varchar_1, col_varchar_2 |

每个 ptag 真的只关心自己相关的列——**互补写**而非**共享写**。

## Goals / Non-Goals

**Goals**：
- SetupTG bind sampler 按 `group_id * col_num_per_tag` 取列 offset，每组写不同列子集
- wrap-around 处理 `col_num_per_tag * num_threads < dataColumns.size()` 的场景
- 新增 pytest case 验列子集按 offset 计算正确
- smoke DB 断言升级：device_1 与 device_3 的非空列**互补不重叠**

**Non-Goals**：
- 改 spec §col_tag_bind_mode 段（"每组不同列"是同一 requirement 的实现细节，无需 spec 级修改）
- 改 JDBC 路径（commit 4 `801ed46` 是简化版，独立 fix 留给后续 DCR）
- 改 full-row path（D-15 独立 bug，与本 DCR 无关）

## Implementation

### 1. SetupTG bind sampler（`shared_memory_setup.py` 行 197 附近）

```groovy
// 旧：def colNamesSubset = dataColumns.take(colNumPerTag)
int colStart = (groupId * colNumPerTag) % dataColumns.size()
def colNamesSubset = (1..colNumPerTag).collect { idx ->
    dataColumns[(colStart + idx - 1) % dataColumns.size()]
}
```

`colStart = groupId * colNumPerTag` 取 offset（fixture 10 data_cols + num_threads=2 + col_num_per_tag=5 = 10 刚好覆盖，无 wrap）；`% dataColumns.size()` 处理 `col_num_per_tag * num_threads < dataColumns.size()` 时循环回到开头。

### 2. Write TG bind path 不动

Write TG PreProcessor 读 `col_names` 列表直接用——SetupTG 烤的列表变了，Write TG 自然写不同列。无须改动 `rest_write_groups.py` / `write_groups.py`。

### 3. 反退化 §8.8 升级

DB 断言从"device_1 与 device_3 都写 col_float4_1 等（共享列）"升级为"device_1 写的 5 列 与 device_3 写的 5 列 **不重叠**"。

pytest case `test_bind_subset_per_group_offset`（`tests/jmx_skeleton_generator/test_setup_bind_sampler.py`）：
- 10 data_cols（col_bool_1, col_char_1, col_float4_1, col_float8_1, col_float8_2, col_int4_1, col_int8_1, col_timestamp_1, col_varchar_1, col_varchar_2，按字母序）
- col_num_per_tag=5, num_threads=2
- 断言 group 0 col_names = 前 5 列（按字母序）
- 断言 group 1 col_names = 后 5 列（offset 5）

## Risks

- **Behavior 变更**：之前 smoke 跑过的 device_1 + device_3 都写同一组列——改后两组列互补。**这是 bug 修复，不是 regression**。
- **fixture 对齐**：fixture 10 data_cols + col_num_per_tag=5 + num_threads=2 刚好覆盖，无 wrap——若未来 fixture 改 `data_col_count: 12`，wrap 自动生效。
- **pytest 全量**：现有 745 全绿（修改 BindSetup 不影响其他 case）；新增 1 case 验列子集计算正确。

## Open Questions

（无 — 唯一语义已与 design §1 Context 对齐）

## Verification

- `pytest tests/jmx_skeleton_generator/test_setup_bind_sampler.py -v` → 6 pass（5 旧 + 1 新）
- `pytest tests/` → 746 passed（745 + 1 新增），0 regress
- smoke schemaless bind path：iot_monitor.meters 10 行，device_1 与 device_3 非空列互补
- DB 验证 SQL：`SELECT count(*) GROUP BY ptag_varchar_1` 给出 2 个不同 group + per-column 计数与 fixture 5 列对齐
