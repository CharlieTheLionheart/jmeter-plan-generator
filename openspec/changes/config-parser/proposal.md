## Why

KaiwuDB SVT 测试计划生成器需要支持灵活的配置方式，通过 YAML 配置文件定义测试场景的数据库模型（表结构、列类型、种子数据）和测试参数（连接配置、写入/查询模式）。配置解析是整个生成器的核心基础模块，为后续的 DDL 生成、种子数据生成、JMX 生成等所有模块提供输入数据。

## What Changes

- 新增 `src/config_parser/models.py` 文件，集中定义所有 Pydantic 配置数据模型，作为本 change 的核心交付物之一
- 新增 `test_model.yaml` 配置文件解析器，支持：
  - 关系库（`rel_dbs`）和时序库（`ts_dbs`）配置
  - 库级别字段：`name`、`if_not_exists`、`with_encoding`、`comment`、`retentions`、`partition_interval`（时序库专用）
  - 表级别字段：`name`、`comment`、`if_not_exists`、`with_hash`、`ts_col`（时序表专用）、`primary_key_count`、`data_col_count`、`primary_tag_count`、`regular_tag_count`
  - 列类型配置（`primary_keys`、`data_cols`、`primary_tags`、`regular_tags`）：`col_type`、`type_proportion`、`val_range`、`seed_num`、`nullable`、`null_rate`
- 新增 `test_cfg.yaml` 配置文件解析器，支持：
  - 连接配置（`conn_config`）：`db_url`、`conn_pool_size`、`device_start`、`test_duration`
  - 写入配置（`write_config`）：`tbl_name`、`throughput`、`mode`、`batch_lines`、`device_per_thread`、`num_threads`
  - 查询配置（`query_config`）：`query`、`throughput`、`num_threads`
- 实现配置校验逻辑，包括：
  - 必填字段检查
  - `type_proportion` 总和校验（必须等于 1.0）
  - `seed_num` 与 `nullable`/`null_rate` 的合法性校验
  - 外键引用格式校验（`ref:库名.表名.列名`）
  - Primary Tag 类型限制校验（不支持 float4/float8，最多 4 个，强制 nullable=false）
  - Tag 列字符类型长度限制（最大 128 字节）

## Capabilities

### New Capabilities
- `config-parser`: 配置文件解析与校验能力，包括 YAML 文件加载、结构解析、规则校验和错误报告

### Modified Capabilities
（无）

## Impact

- 新增 Python 配置解析模块，依赖 `pyyaml` 库
- 为 DDL 生成器、种子数据生成器、JMX 生成器提供结构化配置数据
- 配置错误需要在生成阶段提前暴露，避免生成无效的测试计划