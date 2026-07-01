## Why

T0 阶段需要实现基本的写入功能，包括单条和批量直接 INSERT 写入。这是测试计划生成器的核心功能，用于向时序表持续写入测试数据。

## What Changes

- 新增直接 INSERT 写入功能，支持：
  - `single_insert` 模式：单条 INSERT 语句执行
  - `batch_insert` 模式：批量 INSERT 语句（`INSERT INTO ... VALUES (...),(...)`）
  - 写入采样器生成（JDBCSampler）
  - JSR223PreProcessor 数据准备（从共享内存拷贝行数据、装配时间戳）
  - 第一个 Primary Tag 占位符替换（`${device_code}` → `device_{设备号}`）
  - 设备号计算（基于线程索引和 `device_per_thread`）

## Capabilities

### New Capabilities
- `direct-insert-write`: 直接 INSERT 写入能力（T0 阶段）

### Modified Capabilities
（无）

## Impact

- 依赖 config-parser 模块提供写入配置
- 依赖 seed-data-generator 模块提供行种子总集路径
- 依赖 jmx-skeleton-generator 提供写入线程组骨架
- 使用 Groovy 脚本实现 JSR223PreProcessor 数据准备逻辑
- 生成的 JMX 写入线程组将替换骨架中的占位符