## Why

不同写入方式（直接 INSERT、PreparedStatement、schemaless）需要不同的实现逻辑。策略模式支持插件化扩展，便于添加新写入方式而不修改核心代码。

## What Changes

- 新增写入策略模块，支持：
  - `WriteStrategy` 抽象基类
  - 策略注册表（`STRATEGY_REGISTRY`）
  - 5 种策略实现：
    - `SingleInsertStrategy` - 单条直接 INSERT
    - `BatchInsertStrategy` - 批量直接 INSERT
    - `SinglePreparedStatementStrategy` - 单条 PreparedStatement
    - `BatchPreparedStatementStrategy` - 批量 PreparedStatement（使用 JSR223Sampler）
    - `SchemalessWriteStrategy` - 无模式写入（预留）
  - 策略选择机制

## Capabilities

### New Capabilities
- `write-strategies`: 写入策略模式框架和实现

### Modified Capabilities
- `direct-insert-write`: 策略模式重构 single_insert/batch_insert 实现

## Impact

- 重构 direct-insert-write 中的写入逻辑为策略模式
- 新增 PreparedInsertTemplateGenerator 依赖
- 支持通过注册表添加新策略
- 扩展性：新增策略无需修改核心代码