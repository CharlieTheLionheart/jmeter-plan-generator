## Why

KaiwuDB SVT 测试计划生成器需要根据配置文件中的数据库模型定义生成对应的建库建表 DDL 语句。DDL 生成是测试数据初始化的前提，确保测试场景的数据库结构与配置一致。

## What Changes

- 新增 DDL 生成模块，支持：
  - 关系库 DDL 生成（`CREATE DATABASE`、`CREATE TABLE`）
  - 时序库 DDL 生成（`CREATE DATABASE`、`CREATE TABLE`、`RETENTIONS`、`PARTITION INTERVAL`、`PRIMARY TAGS`、`WITH HASH`）
  - 列名生成（`{列类型前缀}_{列数据类型}_{序号}`）
  - `IF NOT EXISTS` 语法支持
  - `WITH ENCODING` 语法支持
  - 表注释和库注释支持
  - `NOT NULL` 约束生成（基于 `nullable` 配置）
- 支持按库和表组织 DDL 输出
- 输出可执行的 SQL 脚本文件

## Capabilities

### New Capabilities
- `ddl-generation`: DDL 语句生成能力，包括建库建表语句、列定义、约束等

### Modified Capabilities
（无）

## Impact

- 依赖 config-parser 模块提供解析后的配置数据
- 新增 DDL 生成模块，使用 Python 字符串模板或 f-string 生成 SQL
- 生成的 DDL 将用于 SetupThreadGroup 的 DDL 执行阶段