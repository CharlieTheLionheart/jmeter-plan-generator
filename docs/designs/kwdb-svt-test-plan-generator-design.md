# KaiwuDB SVT 通用测试计划生成器概要设计

## 1. 系统架构

### 1.1 整体架构



### 1.2 模块职责

| 模块 | 职责 |
|------|------|
| 配置管理模块 | 负责加载、解析、校验用户配置，提供配置合并和默认值填充能力 |
| 场景生成引擎 | 根据配置生成数据库、表、列的元数据模型，分配数据类型 |
| SQL 构建模块 | 根据元数据模型生成 DDL、DML、DQL 语句 |
| JMeter 计划生成模块 | 将 SQL 语句和测试配置转换为 JMX 文件格式 |
| 输出模块 | 负责将生成的内容写入文件系统，支持多种输出格式 |

---

## 2. 核心设计

### 2.1 写入策略设计

写入方式采用策略模式设计，便于后续扩展：

```
WriteStrategy (接口)
├── StmtWriteStrategy (当前实现)
├── PreparedStatementWriteStrategy (未来)
├── BatchWriteStrategy (未来)
├── KafkaSyncWriteStrategy (未来)
└── CustomWriteStrategy (用户自定义)
```

---

## 3. 数据模型

### 3.1 配置模型

配置类聚合所有配置项：

- `TestPlanConfig` - 根配置，包含所有子配置
- `DatabaseConfig` - 数据库配置
- `TableConfig` - 表配置
- `DataTypeConfig` - 数据类型配置
- `WriteConfig` - 写入配置
- `QueryConfig` - 查询配置
- `JMeterConfig` - JMeter 配置
- `OutputConfig` - 输出配置

### 3.2 元数据模型

生成器内部使用的元数据模型：

- `DatabaseSchema` - 数据库模型
  - `name`: 数据库名称
  - `type`: 数据库类型（RELATIONAL / TIME_SERIES）
  - `tables`: 表列表

- `TableSchema` - 表模型
  - `name`: 表名称
  - `type`: 表类型（RELATIONAL / TIME_SERIES）
  - `columns`: 列列表
  - `primaryKeyColumns`: 主键列（关系表）
  - `primaryTagColumns`: Primary Tag 列（时序表）

- `ColumnSchema` - 列模型
  - `name`: 列名称
  - `dataType`: 数据类型
  - `position`: 列位置
  - `isPrimaryKey`: 是否为主键（关系表）
  - `isPrimaryTag`: 是否为 Primary Tag（时序表）

---

## 4. 输出目录结构

```
output/
├── test_plan.jmx           # JMeter 测试计划
├── ddl_scripts/
│   ├── database_create.sql
│   ├── table_create.sql
│   └── index_create.sql
├── metadata/
│   ├── database_summary.json
│   ├── table_details.json
│   └── report.md
└── config/
    └── used_config.json    # 实际使用的配置
```

---

## 5. 扩展点设计

### 5.1 写入策略扩展

新增写入方式时：
1. 实现 `WriteStrategy` 接口
2. 在配置中注册新的策略名称
3. 通过 `customStrategyClass` 配置项指定实现类

### 5.2 查询生成器扩展

新增查询类型时：
1. 实现 `QueryGenerator` 接口
2. 在 `QueryType` 枚举中注册新类型
3. 在查询配置中添加新类型的配置项

### 5.3 数据类型扩展

新增数据类型时：
1. 在 `DataType` 枚举中定义新类型
2. 在 `DataTypeConfig` 中添加配置项
3. 在 SQL 构建模块中实现类型到 SQL 类型的映射

---

## 6. 修订历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2026-05-15 | liujin | 初始版本，从规格书分离出的概要设计 |
