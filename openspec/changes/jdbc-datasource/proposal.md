## Why

JMeter 测试计划中的所有 JDBCSampler 和 JSR223Sampler 都需要通过 JDBC 连接池访问数据库。JDBCDataSource 配置了数据库连接参数、连接池大小、驱动类等，是测试计划的基础配置。

## What Changes

- 新增 JDBCDataSource 生成功能，支持：
  - JDBCDataSource XML 元素生成
  - 连接参数配置：`dbUrl`、`username`、`password`、`driver`
  - 连接池配置：`poolMax`、`keepAlive`、`connectionAge`、`timeout`、`trimInterval`
  - 自动提交模式配置
  - 数据源名称 `jdbcConfig` 供采样器引用

## Capabilities

### New Capabilities
- `jdbc-datasource`: JDBCDataSource 生成能力

### Modified Capabilities
（无）

## Impact

- 依赖 config-parser 模块提供 conn_config
- JDBCDataSource 在 TestPlan 顶层定义
- 所有 JDBCSampler 通过 `dataSource="jdbcConfig"` 引用
- 使用 JMeter 变量引用配置参数（`${db_url}`、`${db_username}` 等）