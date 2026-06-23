## Why

KaiwuDB SVT 测试计划生成器需要支持查询配置，生成独立的查询线程组。查询功能用于模拟生产环境中的读操作，验证数据库的查询性能。

## What Changes

- 新增查询功能模块，支持：
  - 查询 SQL 中 `?` 占位符解析和绑定到列
  - 从列种子文件随机采样
  - JSR223PreProcessor 脚本生成
  - 无法绑定时报错（如 `LIMIT ?`）
  - NULL 值处理（种子文件中的 `"null"` → 空字符串）
  - 查询采样器生成（JDBCSampler，使用 `Prepared Select Statement`）
  - 独立的查询线程组（每个查询一个线程组）

## Capabilities

### New Capabilities
- `query-functionality`: 查询功能和参数绑定能力

### Modified Capabilities
（无）

## Impact

- 依赖 config-parser 模块提供查询配置
- 依赖 seed-data-generator 模块提供列种子文件路径
- 依赖 jmx-skeleton-generator 提供查询线程组骨架
- 使用 Groovy 脚本实现参数采样
- 生成的 JMX 查询线程组将替换骨架中的占位符