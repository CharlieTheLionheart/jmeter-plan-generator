# Project Context

> 本文件为 OpenSpec 提供项目级背景，供 AI 在生成 proposal / spec / design / tasks 时参考。
> 内容提炼自 [docs/designs/kwdb-svt-test-plan-generator-design.md](../docs/designs/kwdb-svt-test-plan-generator-design.md)。

## Purpose

KaiwuDB SVT 测试计划生成器：读取两份 YAML 配置（`test_model.yaml` 数据库场景模型、`test_cfg.yaml` 测试运行时配置），生成可直接运行的 JMeter 压测计划，用于 KaiwuDB 的写入与查询性能/稳定性测试（SVT）。

输出物：

- **JMeter 测试计划文件**（`.jmx`）：内嵌建库建表 DDL、线程组编排、写入/查询采样器。
- **列种子缓存文件**：每表一个子目录，每列一个纯文本文件（一行一个种子值），JMX 中仅保留路径引用，不内嵌数据。

## Tech Stack

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ | YAML 生态成熟，规格要求 |
| 数据校验 | Pydantic V2 | 声明式 schema、高性能、自动错误信息 |
| YAML 解析 | PyYAML | Python 标准生态 |
| JMX 生成 | XML 元素树逐节点构建（非模板字符串、非 lxml.etree） | JMeter XML 属性名/顺序有特殊要求，手动控制更安全 |
| 测试 | pytest + pytest-cov + pytest-mock | Python 事实标准，覆盖率目标 ≥80% |
| 包管理 | uv / pip + pyproject.toml | 现代化 Python 项目配置 |
| 运行时脚本 | Groovy（JMeter JSR223） | 唯一支持 JSR223 Compilable 编译缓存，性能最佳 |

## Project Conventions

### Code Style

- 全量类型注解，使用 ruff 做静态检查。
- SQL 数据类型名称大小写不敏感，生成器内部统一按**全小写**处理，DDL / 模板输出均为小写。
- 列名遵循固定格式 `{前缀}_{类型}_{序号}`，前缀映射：
  `data_cols→col`、`primary_tags→ptag`、`regular_tags→rtag`、`primary_keys→pk`（如 `col_int8_1`、`ptag_varchar_1`）。
- 列种子文件名约定：`{列序号}_{列名}.{类型名}`（列序号按表中除时间戳列外的字段顺序从 1 起，类型名为规范化基本类型）。

### Architecture Patterns

分层架构（parser → generator → builder），模块职责单一：

- `models.py` — Pydantic 数据模型（库/表/列、测试配置）。
- `parser.py` — YAML 解析 + 一致性校验（规则 R-PAR-001 ~ R-PAR-015）。
- `column_namer.py` — 按 `type_proportion` 用 **floor + 贪心** 算法分配列数并生成列名。
- `seed_gen.py` — 列种子离线生成（数值/区间/正则/枚举/ref 外键、NULL 打散）。
- `ddl_generator.py` — CREATE DATABASE / TABLE（关系表、时序表）。
- `prepared_insert_template_generator.py` — 条件生成带 `?` 的 INSERT 模板（仅 `single_prepared`/`batch_prepared`）。
- `jmx_builder.py` — 组装 JMeter 线程组与采样器 XML。
- `strategies/` — 写入方式**策略模式**插件化（single/batch × insert/prepared + schemaless），经 `STRATEGY_REGISTRY` 注册。
- `utils/` — XML 便捷构造、val_range 表达式解析。

关键设计决策：

1. **双配置解耦**：模型与运行时配置分离，同一数据模型可被不同压测策略复用。
2. **种子与 JMX 分离落盘**：降低 JMX 体积、支持超大 `seed_num`，运行时随机采样。
3. **关系表 vs 时序表职责分离**：关系表仅在 `SetupThreadGroup` 一次性初始化写入；时序表按 `write_config` 持续发压。
4. **行种子总集 + 共享内存**：`SetupThreadGroup` 单线程一次性拼接行种子总集放入 JMeter `props`，所有写入线程共享，随机拷贝连续 `batch_lines` 行；列间按建表顺序绑定，不做笛卡尔积对齐。
5. **多端协同设备隔离**：各端用相同测试计划，仅以 `device_start` 划分设备范围，按表独立计算不重叠的设备号区间。

### Testing Strategy

- 单元测试覆盖各模块（models/column_namer/utils 90%+，parser/seed_gen 85%+，strategies 80%+）。
- 集成测试对比 DDL 预期 SQL、校验 JMX XML 合法性。
- E2E 冒烟：生成完整 `.jmx` 后用 `jmeter -n -t plan.jmx` 验证语法。
- 目标：每个验收点转化为可验证测试（先写测试再实现）。

### Git Workflow

- 主分支：`develop-2.0`；当前工作分支：`refactor/generic-test-plan`。
- 采用 OpenSpec 驱动：变更先建 `openspec/changes/<change-id>/`（proposal + spec + design + tasks），实现完成后归档。

## Domain Context

- **关系库 `rel_dbs`**：元数据表，启动阶段初始化写入一次，不参与持续发压。
- **时序库 `ts_dbs`**：性能测试主对象，含时间戳列、primary_tags（≤4，值绑定设备后固定，作唯一标识，禁浮点/变长非-VARCHAR）、regular_tags、data_cols。
- **写入模式 `WriteMode`**：`single_insert` / `batch_insert` / `single_prepared` / `batch_prepared` / `schemaless`。
  - `batch_prepared` 用 `JSR223Sampler` 手写 JDBC `addBatch()`/`executeBatch()`（JMeter 原生 JDBCSampler 无法一次绑定多组参数）。
- **查询模式 `QueryMode`**：`statement` / `prepared_statement`，统一以 `Prepared Select Statement` 执行，`?` 由 `JSR223PreProcessor` 从种子文件随机取值注入。
- **时间戳与首个 ptag** 不进入列种子：时间戳由写入线程按 `base_time + batch_seq × ms_step` 装配；首个 ptag 列种子为占位串 `?ptag1?`，运行时按设备号替换为 `device_{n}`。

## Important Constraints

- JMeter 线程组**不能嵌套**；`SetupThreadGroup` 与普通 `ThreadGroup` 为并列关系，靠 JMeter 执行机制保证先后顺序。
- 当前版本要求所有写入线程组使用**相同 `num_threads`**，生成阶段校验一致性，避免全局同名变量冲突。
- `type_proportion` 同一列组之和必须等于 1.0（容差 ±1e-9）。
- `with_hash` 取值范围 `[1, 50000]`；`primary_tag_count ≤ 4`。
- `nullable=false` 时 `null_rate` 必须为 `0.0`；`primary_tags` 的 `nullable` 必须为 `false`。
- NULL 计入 `seed_num` 总数，按 `round(seed_num × null_rate)` 生成后随机打散。
- 查询 SQL 中无法绑定到具体列的 `?` 直接报 `ValidationError`，拒绝生成。

## External Dependencies

- **JMeter**：测试计划运行引擎（`JDBCDataSource`、`JDBCSampler`、`JSR223Sampler`/`PreProcessor`、`ConstantThroughputTimer`）。
- **KaiwuDB JDBC 驱动**：`com.kaiwudb.Driver`，连接串形如 `jdbc:kaiwudb://host:port/db`。
- **Groovy**：JMeter `lib/` 下的 JSR223 脚本运行时。

## Reference

- 设计文档：[docs/designs/kwdb-svt-test-plan-generator-design.md](../docs/designs/kwdb-svt-test-plan-generator-design.md)
- 设计评审：[docs/designs/design-review-2026-06-11.md](../docs/designs/design-review-2026-06-11.md)
