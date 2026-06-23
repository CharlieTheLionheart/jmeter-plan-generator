## Context

JDBCDataSource 是 JMeter 测试计划中的数据库连接池配置。所有 JDBCSampler 和 JSR223Sampler 都需要通过 JDBCDataSource 获取数据库连接。JDBCDataSource 需要在 TestPlan 层级定义，并通过 `dataSource` 名称供采样器引用。

## Goals / Non-Goals

**Goals:**
- 生成 JDBCDataSource XML 元素
- 配置数据库连接参数（dbUrl、username、password、driver）
- 配置连接池参数（poolMax、keepAlive、connectionAge、timeout、trimInterval）
- 设置自动提交模式
- 正确定位 JDBCDataSource 在 JMX 中的位置

**Non-Goals:**
- 不实现动态连接池管理
- 不支持多数据源配置
- 不支持动态生成任意 `conn_config` 参数：本期仅暴露 `db_url` 和 `conn_pool_size` 两个连接相关参数（`db_username`/`db_password` 沿用既有变量），其余 `conn_config` 条目不在 JDBCDataSource 中动态生成
- 不支持其他数据库驱动：`driver` 固定为 `com.kaiwudb.Driver`
- 不将连接池参数（`connectionAge`/`timeout`/`trimInterval` 等）配置化：保持硬编码，后续按需暴露

## Decisions

### 数据源名称固定为 jdbcConfig

**Decision:** JDBCDataSource 的 `dataSource` 属性固定为 `"jdbcConfig"`，所有采样器通过该名称引用。

**Rationale:**
- 简化配置，避免数据源名称管理
- 符合 JMeter 约定，易于理解和维护

**Alternatives considered:**
- **使用表名作为数据源名称**: 增加复杂度，不必要

### 使用 JMeter 变量引用配置参数

**Decision:** 数据库 URL、用户名、密码、连接池大小等参数使用 JMeter 变量引用（`${db_url}` 等）。

**Rationale:**
- 支持通过 `-Jdb_url=...` 命令行参数覆盖
- 支持在不同环境使用相同测试计划
- 符合 JMeter 最佳实践

**Alternatives considered:**
- **硬编码配置值**: 不灵活，不支持环境切换

### 自动提交模式开启

**Decision:** JDBCDataSource 的 `autocommit` 属性设置为 `true`。

**Rationale:**
- DDL 语句需要自动提交
- 简化事务管理
- 符合设计文档要求

**Alternatives considered:**
- **关闭自动提交**: 需要手动提交事务，增加复杂度

### 仅暴露 db_url 和 conn_pool_size 两个动态参数

**Decision:** 本期 JDBCDataSource 仅将 `db_url`（`dbUrl="${db_url}"`）和 `conn_pool_size`（`poolMax="${conn_pool_size}"`）作为可通过 `-J` 覆盖的动态参数；`db_username`/`db_password` 沿用既有 `${db_username}`/`${db_password}` 变量；其余 `conn_config` 条目和连接池参数不动态生成。

**Rationale:**
- 覆盖当前测试场景的实际需求，避免过度设计
- 动态遍历 `conn_config` 生成任意 `<elementProp>` 增加复杂度且无即时收益
- 连接池参数（`connectionAge`/`timeout`/`trimInterval`）大部分场景使用相同配置，硬编码足够
- 其他参数的暴露后续按需添加，保持本期范围清晰

**Alternatives considered:**
- **动态遍历 conn_config 生成全部参数**: 复杂度高，本期无需求，列为 Non-Goal

### 驱动类固定为 com.kaiwudb.Driver

**Decision:** `driver` 固定为 `com.kaiwudb.Driver`，本期仅支持 KaiwuDB。

**Rationale:**
- 测试目标数据库为 KaiwuDB，无多数据库需求
- 固定驱动类简化配置，避免无谓的扩展点

**Alternatives considered:**
- **支持多驱动配置**: 当前无需求，列为 Non-Goal，后续按需添加

## Risks / Trade-offs

### Risk: 驱动类名称错误
**Mitigation:** KaiwuDB 驱动类名称固定为 `com.kaiwudb.Driver`，在文档中注明。

### Trade-off: 连接池参数固定
**Rationale:** 大部分场景使用相同配置。如果需要调整，可以手动修改生成的 JMX。

## Migration Plan

无需迁移。这是一个新功能模块。