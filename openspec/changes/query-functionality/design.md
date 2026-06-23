## Context

查询功能模块负责生成查询线程组和查询采样器。查询 SQL 中的 `?` 占位符需要在生成阶段解析并绑定到列种子文件，运行时从种子文件随机采样。

## Goals / Non-Goals

**Goals:**
- 解析 SQL 中的 `?` 占位符（排除字符串字面量）
- 通过上下文分析将占位符绑定到具体列
- 生成 JSR223PreProcessor Groovy 脚本
- 生成 JDBCSampler（使用 `Prepared Select Statement`）
- 生成独立的查询线程组
- 无法绑定时报错（如 `LIMIT ?`）

**Non-Goals:**
- 不支持复杂 SQL 解析（如子查询、CTE）
- 不支持非列参数（如 `LIMIT ?`）
- 不支持自定义参数绑定策略

## Decisions

### 使用状态机解析 SQL 占位符

**Decision:** 使用状态机遍历 SQL 字符，识别字符串字面量边界，跳过引号内的 `?`。

**Rationale:**
- 简单高效，无需完整 SQL 解析器
- 支持单引号和双引号字符串
- 处理转义字符（`\'`）

**Alternatives considered:**
- **正则表达式**: 难以正确处理字符串字面量
- **完整 SQL 解析器**: 过于复杂，引入额外依赖

### 通过正则提取列名上下文

**Decision:** 使用正则表达式从 `?` 前的 SQL 片段中提取列名。

**Rationale:**
- 支持常见模式：`表名.列名` 或 `列名`
- 支持常见操作符：`=`, `<>`, `!=`, `LIKE`, `IN` 等
- 简单直接，无需复杂语法分析

**Alternatives considered:**
- **完整 SQL 语法树**: 过于复杂
- **硬编码模式匹配**: 难以扩展

### SQL 标识符和关键字统一使用小写

**Decision:** 处理的用户配置查询 SQL 语句中，所有 SQL 标识符（包括表名、列名）和 SQL 关键字（如 SELECT、FROM、WHERE、INSERT、VALUES 等）统一使用小写，与整个测试计划的其他模块保持一致。

**Rationale:**
- 与整个测试计划的其他模块统一 SQL 规范
- 虽然 KaiwuDB 对未加引号标识符的大小写不敏感，但统一使用小写可以提高测试计划的可读性和一致性
- 便于维护和调试
- 简化大小写转换逻辑，避免不同模块使用不同大小写规范

**Alternatives considered:**
- **支持任意大小写**: 增加不必要的复杂性
- **关键字大写标识符小写**: 与其他模块不一致

**示例:**
```sql
-- 正确：所有标识符和关键字统一小写
select col_int8_1 from iot_monitor.t_cnc where ptag_int8_1 = ?
select pk_int8_1, col_varchar_1 from iot_metadata.t_workshop where pk_int8_1 = ?

-- 错误：使用了大写（虽然 KaiwuDB 支持，但不规范）
SELECT COL_INT8_1 FROM iot_monitor.t_cnc WHERE ptag_int8_1 = ?
```

### 无法绑定时报错

**Decision:** 当 `?` 无法关联到具体列时（如 `LIMIT ?`），在生成阶段抛出异常，拒绝生成测试计划。

**Rationale:**
- 尽早发现问题，避免运行时错误
- 明确告知用户配置问题

**Alternatives considered:**
- **使用默认值**: 不符合测试场景
- **跳过该参数**: 影响查询语义

### NULL 值处理

**Decision:** 种子文件中的字符串 `"null"` 在 Groovy 脚本中映射为空字符串 `""`，避免 JDBC 驱动误当作数据库 NULL。

**Rationale:**
- JDBC 驱动会将字符串 `"null"` 当作字面值，而非 SQL NULL
- 空字符串在多数场景下等效于 SQL NULL
- 保持简单，避免复杂的类型判断

**Alternatives considered:**
- **使用 JDBC setNull()**: 需要在 JDBCSampler 中处理，增加复杂度
- **保留 "null" 字符串**: 不符合测试场景

### 查询线程组独立配置

**Decision:** 每个查询配置生成独立的查询线程组，各自挂载 ConstantThroughputTimer。

**Rationale:**
- 不同查询可能有不同的目标吞吐量
- 独立线程组便于监控和调试
- 符合规格书要求

**Alternatives considered:**
- **共用线程组**: 难以区分不同查询的吞吐量
- **查询串行执行**: 不符合性能测试场景

## Risks / Trade-offs

### Risk: 正则表达式覆盖不全
**Mitigation:** 在文档中说明支持的模式，添加测试用例覆盖常见场景。未来可扩展为 SQL 语法树解析。

### Risk: 列名冲突
**Mitigation:** 通过表完全限定名（`db.table.col`）区分同名列。

### Trade-off: 不支持复杂 SQL
**Rationale:** 性能测试场景通常使用简单查询。如果需要复杂查询，可以手工修改生成的 JMX。

## Migration Plan

无需迁移。这是一个新功能模块。