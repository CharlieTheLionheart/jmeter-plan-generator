## Why

T1 阶段的 PreparedStatement 写入需要预先生成带 `?` 占位符的 INSERT 模板。模板用于 `single_prepared` 和 `batch_prepared` 模式，在运行时由 JDBC 驱动绑定参数。

## What Changes

- 新增 Prepared Insert 模板生成模块，支持：
  - 为每个时序表生成带 `?` 占位符的 INSERT 模板
  - 模板按表完全限定名（`db.table`）索引
  - 列名按建表字段顺序排列
  - 仅当 `write_config` 中存在 `single_prepared` / `batch_prepared` 时生成
  - 关系表不参与模板生成（仅用于元数据初始化）

## Capabilities

### New Capabilities
- `prepared-insert-template`: PreparedStatement INSERT 模板生成能力

### Modified Capabilities
（无）

## Impact

- 依赖 config-parser 模块提供配置
- 依赖 column-namer 模块提供列名
- 输出模板字典供写入策略模块使用
- 条件执行：仅在有写入策略需要时生成