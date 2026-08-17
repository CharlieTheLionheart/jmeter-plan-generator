# Spec: col-tag-bind-per-group-subsets

## ADDED Requirements

### `per-group-column-subsets`

bind 模式下，每张表的列子集按 `group_id` 决定列起始 offset，每组写**不同**列（非共享前 N 列）。

#### 场景

`col_tag_bind_mode=true` 时，SetupTG bind sampler 按以下公式计算每个 `group_id` 的列子集：

```
col_start = (group_id * col_num_per_tag) % data_columns_count
col_names_subset = data_columns_sorted[(col_start + i) % data_columns_count for i in 0..col_num_per_tag-1]
```

- `data_columns_count` = 表的 `data_col_count`
- `data_columns_sorted` = 列种子文件名按字母序（与现有排序一致）
- wrap-around 处理 `col_num_per_tag * num_threads < data_columns_count` 的场景

#### 业务语义

bind 模式的真实价值是"ptag 组合 → 列子集"映射——每个 ptag 只关心自己相关的列：

- `num_threads=2 + col_num_per_tag=5 + data_col_count=10` 的 fixture 场景：
  - group 0（device_1）写 `col_bool_1, col_char_1, col_float4_1, col_float8_1, col_float8_2`
  - group 1（device_3）写 `col_int4_1, col_int8_1, col_timestamp_1, col_varchar_1, col_varchar_2`
  - 两组列**互补不重叠**

#### 反退化

- §8.7 单元：`test_bind_subset_per_group_offset` 验 SetupTG 烤的 col_names 列表按 group_id 正确 offset
- §8.8 冒烟：DB 验证 device_1 与 device_3 写的非空列**不重叠**

#### 适用范围

- 仅 bind 路径（schemaless + JDBC）
- `col_tag_bind_mode=false`（默认）行为不变
- `col_num_per_tag=0` 或 `col_num_per_tag>data_col_count` 时按 `WriteConfig.check_col_tag_bind_mode_positive` / main entry 校验拦截
