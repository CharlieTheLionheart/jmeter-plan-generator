## Why

KaiwuDB SVT 测试计划生成器需要根据配置中的 `val_range` 和 `seed_num` 生成列种子数据和行种子数据总集。列种子文件供查询时 `?` 占位符采样使用，行种子总集供写入线程拷贝装配数据。种子数据生成是测试数据模拟的核心。

## What Changes

- 新增种子数据生成模块，支持：
  - 列种子数据生成（按列类型和 `val_range` 生成 `seed_num` 行数据）
  - 数值类型生成（支持区间表达式、固定值）
  - 字符串类型生成（支持正则表达式）
  - 枚举类型生成（支持顺序循环选取）
  - 外键引用采样（从被引用表的主键种子数据中采样）
  - NULL 值生成（基于 `null_rate` 随机打散）
  - 行种子总集生成（按列序号拼接列种子文件，循环填充较短的列）
- 输出列种子文件（命名：`{列序号}_{列名}.{类型名}`）
- 输出行种子总集（用于共享内存初始化）

## Capabilities

### New Capabilities
- `seed-data-generation`: 种子数据生成能力，包括列种子文件和行种子总集

### Modified Capabilities
（无）

## Impact

- 依赖 config-parser 模块提供解析后的配置数据
- 依赖 ddl-generator 模块提供的列名
- 新增种子数据生成模块，使用 Python 生成随机数据
- 生成的列种子文件将保存到 `seeds/{table}/` 目录
- 生成的行种子总集将在 JMX SetupThreadGroup 中加载到共享内存