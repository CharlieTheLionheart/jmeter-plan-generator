## Why

KaiwuDB SVT 测试计划生成器需要根据配置中的 `type_proportion` 分配实际列数，并按照固定格式生成列名。列名用于 DDL 生成、种子数据文件命名、JMX 采样器等所有模块，必须保持一致。

## What Changes

- 新增列名生成模块，支持：
  - 按 `type_proportion` 分配实际列数（`floor + 贪心` 算法）
  - 按固定格式 `{前缀}_{类型}_{序号}` 生成列名
  - 前缀映射：`col`（data_cols）、`ptag`（primary_tags）、`rtag`（regular_tags）、`pk`（primary_keys）
  - 返回列名列表和列序号映射

## Capabilities

### New Capabilities
- `column-naming`: 列名生成和列数分配能力

### Modified Capabilities
（无）

## Impact

- 依赖 config-parser 模块提供表配置
- 输出列名列表供 DDL 生成器、种子数据生成器、写入采样器生成器、查询采样器生成器使用
- 使用 Python 实现分配算法