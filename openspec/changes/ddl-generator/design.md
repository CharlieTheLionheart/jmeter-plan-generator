## Context

DDL 生成模块负责将配置解析模块输出的结构化配置转换为 KaiwuDB 可执行的 SQL 语句。生成的 DDL 将在 JMeter 测试计划的 SetupThreadGroup 中执行，用于创建测试所需的数据库和表结构。

## Goals / Non-Goals

**Goals:**
- 生成符合 KaiwuDB 语法的 DDL 语句
- 支持关系库和时序库的完整语法特性
- 列名生成遵循 `{type_prefix}_{data_type}_{sequence}` 规范
- 支持约束生成（`NOT NULL`、`PRIMARY KEY`、`PRIMARY TAGS`）
- 输出结构化的 DDL 脚本

**Non-Goals:**
- 不支持 DDL 的增量更新或版本管理
- 不支持自定义 SQL 片段注入
- 不执行 DDL 语句，仅生成

## Decisions

### 使用模板字符串生成 DDL

**Decision:** 使用 Python f-string 生成 DDL 语句。

**Rationale:**
- 简单直接，易于理解和维护
- DDL 语句格式固定，模板清晰
- 不需要复杂的 SQL 构建库
- 便于调试和错误追踪

**Alternatives considered:**
- **SQLAlchemy**: 过于重量级，配置结构不适合 ORM 映射
- **Jinja2 模板**: 引入额外依赖，f-string 足够使用
- **字符串拼接**: 可读性差，易于出错

### 列名生成器作为独立模块

**Decision:** 将列名生成逻辑抽象为独立的 `ColumnNameGenerator` 类。

**Rationale:**
- 列名生成规则复杂（类型前缀、数据类型、序号），独立封装便于测试
- 多个模块（DDL 生成、种子数据生成、JMX 生成）都需要生成列名，避免重复代码
- 便于后续扩展列名生成规则

**Alternatives considered:**
- **内联生成**: 代码重复，不易维护
- **在配置解析阶段生成**: 增加配置模块复杂度，列名是展示层逻辑

### DDL 输出格式

**Decision:** 输出为 SQL 脚本，按库和表分组组织，使用分号作为语句分隔符。

**Rationale:**
- KaiwuDB 支持分号分隔的多语句一次执行，符合标准 SQL 习惯
- 分组组织便于阅读和调试
- 可以轻松转换为 JMX JSR223 脚本

**Alternatives considered:**
- **输出为字典或列表**: 不便于直接执行
- **输出为 JMX XML 片段**: 增加与 JMX 生成器的耦合

### 表名使用限定名

**Decision:** CREATE TABLE 语句中的表名必须使用带数据库名的限定名格式（`database.table_name`），且整个测试计划中所有对表的引用都应使用限定名。

**Rationale:**
- 在 JMeter 测试计划中，连接可能在不同数据库间切换，使用限定名可确保引用正确
- 避免数据库上下文切换导致的引用歧义
- KaiwuDB 支持标准 SQL 限定名语法，兼容性好
- 规范化命名约定，提高测试计划的可读性和维护性

**Alternatives considered:**
- **使用非限定名**: 需要在每个语句前添加 `USE database`，增加语句数量和复杂性
- **动态数据库上下文**: 在 JMX 中维护当前数据库状态，复杂度高且容易出错

**示例:**
```sql
-- 正确：使用限定名
create database iot_metadata;
create table iot_metadata.t_workshop (
    pk_int8_1 int8 not null,
    col_varchar_1 varchar(16),
    primary key (pk_int8_1)
);

-- 错误：使用非限定名（除非已执行 USE iot_metadata）
CREATE TABLE t_workshop (
    pk_int8_1 INT8 NOT NULL,
    col_varchar_1 VARCHAR(16),
    PRIMARY KEY (pk_int8_1)
);
```

### 数据类型规范化

**Decision:** 在 DDL 生成时将配置中的数据类型转换为 KaiwuDB 语法（小写），与标识符大小写规范保持一致。

**Rationale:**
- 配置文件中使用小写便于阅读
- KaiwuDB SQL 语法不区分大小写
- 与 SQL 标识符统一使用小写的规范保持一致
- 集中转换逻辑，避免重复

**Alternatives considered:**
- **配置中使用大写**: 不符合 Python 配置习惯
- **在配置解析阶段转换**: 数据类型解析与展示逻辑混杂
- **关键字大写标识符小写**: 增加不必要的规则复杂度

### SQL 标识符和关键字统一使用小写

**Decision:** 生成的 DDL 语句中，所有 SQL 标识符（包括数据库名、表名、列名、约束名等）和 SQL 关键字（如数据类型、INT8、VARCHAR、PRIMARY KEY、NOT NULL 等）统一使用小写。

**Rationale:**
- 虽然 KaiwuDB 对未加引号标识符和 SQL 关键字的大小写不敏感，但统一使用小写可以提高测试计划的可读性和一致性
- 小写更符合现代编码规范，便于阅读和维护
- 统一的命名规范便于下游模块引用和调试
- 简化大小写转换逻辑，避免关键字和标识符使用不同大小写的复杂性

**Alternatives considered:**
- **关键字大写标识符小写**: 符合传统 SQL 编码风格，但增加规则复杂度
- **保持原样**: 配置中的大小写可能不一致，影响规范性
- **混合使用**: 难以维护，容易产生歧义

**示例:**
```sql
-- 正确：所有标识符和关键字统一小写
create database iot_metadata;
create table iot_metadata.t_workshop (
    pk_int8_1 int8 not null,
    col_varchar_1 varchar(16),
    primary key (pk_int8_1)
);

-- 正确：时序表
create database iot_monitor;
create table iot_monitor.t_cnc (
    ts timestamp,
    ptag_int8_1 int8 not null,
    col_int8_1 int8,
    primary tags (ptag_int8_1)
);

-- 错误：使用了大写（虽然 KaiwuDB 支持，但不规范）
CREATE DATABASE IoTMetadata;
CREATE TABLE IOT_METADATA.T_WORKSHOP (
    PK_INT8_1 INT8 NOT NULL,
    COL_VARCHAR_1 VARCHAR(16),
    PRIMARY KEY (PK_INT8_1)
);
```

## Risks / Trade-offs

### Risk: KaiwuDB DDL 语法版本差异
**Mitigation:** 在文档中注明适用的 KaiwuDB 版本，预留版本兼容性扩展点。

### Risk: 列名生成规则变更影响多个模块
**Mitigation:** 使用独立的列名生成器，规则变更只需修改一处。

### Trade-off: 不支持复杂约束（如外键）
**Rationale:** 规格书中未要求外键约束，外键仅作为引用关系使用。未来可通过扩展添加。

## Migration Plan

无需迁移。这是一个新功能模块。
