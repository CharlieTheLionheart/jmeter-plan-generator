## Context

Prepared Insert 模板生成器负责为 PreparedStatement 写入生成带 `?` 占位符的 INSERT SQL 模板。模板用于 `single_prepared` 和 `batch_prepared` 模式，在运行时由 JDBC 驱动绑定参数。

## Goals / Non-Goals

**Goals:**
- 为每个时序表生成 INSERT 模板
- 模板按表完全限定名索引
- 列名按建表字段顺序排列
- 条件执行：仅在有 prepared 模式时生成
- 关系表不参与

**Non-Goals:**
- 不生成关系表的模板（关系表仅用于元数据初始化）
- 不处理模板缓存（每次运行重新生成）

## Decisions

### 条件执行

**Decision:** 在 `main.py` 或 `jmx_builder` 中检查 `write_config`，仅当存在 `single_prepared` / `batch_prepared` 模式时才实例化该模块。

**Rationale:**
- 避免不必要的计算
- 关系表不参与，减少处理量

**Alternatives considered:**
- **无条件生成**: 浪费资源
- **在策略内部检查**: 逻辑分散

### 表完全限定名索引

**Decision:** 返回字典，键为 `db.table`（小写），值为 INSERT SQL 模板。

**Rationale:**
- 支持跨库引用
- 清晰的唯一标识
- 便于策略查找
- 与 DDL 生成器和 direct-insert-write 模块保持一致的表名格式

**Alternatives considered:**
- **按表名索引**: 跨库冲突
- **按对象索引**: 过于抽象

### SQL 标识符和关键字统一使用小写

**Decision:** 生成的 INSERT 模板中，所有 SQL 标识符（包括表名、列名）和 SQL 关键字（如 INSERT INTO、VALUES 等）统一使用小写，与 DDL 生成器和 direct-insert-write 模块保持一致。

**Rationale:**
- 与整个测试计划的其他模块统一 SQL 规范
- 虽然 KaiwuDB 对未加引号标识符的大小写不敏感，但统一使用小写可以提高测试计划的可读性和一致性
- 便于维护和调试
- 简化大小写转换逻辑，避免不同模块使用不同大小写规范

**Alternatives considered:**
- **关键字大写标识符小写**: 与其他模块不一致
- **保持原样**: 可能产生大小写不一致的问题

**示例:**
```python
# 正确：所有标识符和关键字统一小写
{
    'iot_monitor.t_cnc': 'insert into iot_monitor.t_cnc (ts, ptag_int8_1, col_int8_1) values (?, ?, ?)',
    'iot_metadata.t_workshop': 'insert into iot_metadata.t_workshop (pk_int8_1, col_varchar_1) values (?, ?)'
}

# 错误：混用大小写（与同模块其他 SQL 风格不一致）
{
    'iot_monitor.t_cnc': 'Insert Into iot_monitor.t_cnc (ts, ptag_int8_1, col_int8_1) Values (?, ?, ?)'
}
```

## Risks / Trade-offs

### Trade-off: 不生成关系表模板
**Rationale:** 关系表仅在 SetupThreadGroup 中使用 batch_insert 一次性初始化，不使用 PreparedStatement。

## Migration Plan

无需迁移。这是一个新功能模块。

