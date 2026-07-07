## Context

JMX 骨架生成模块负责创建 JMeter 测试计划的基础 XML 结构。JMeter 测试计划是树状结构，包含 TestPlan、ThreadGroup、JDBCSampler 等元素。骨架生成器创建这些元素的框架，具体内容由其他模块（写入方式、查询功能）填充。

## Goals / Non-Goals

**Goals:**
- 生成符合 JMeter 5.5+ 语法的 XML 结构
- 支持所有必需的 JMeter 组件（TestPlan、ThreadGroup、JDBCSampler 等）
- 支持变量定义和引用
- 支持 SetupThreadGroup 的特殊执行顺序
- 生成可被 JMeter 打开的 .jmx 文件

**Non-Goals:**
- 不实现具体的写入逻辑（由 direct-insert-write / write-strategies 模块实现）
- 不实现具体的查询逻辑（由 query-functionality 模块实现）
- 不实现吞吐量控制（由 throughput-control 模块实现）
- 不实现 schemaless 写入（SCHEMALESS 模式 T2 实现）

## Decisions

### 使用 `utils/xml_helpers` 构建 JMeter XML

**Decision:** JMX 骨架生成模块使用 `utils/xml_helpers.py` 创建 JMeter 标准 XML 元素（如 `HashTree`、`stringProp`、`boolProp` 等），`utils/xml_helpers.py` 基于 Python 标准库 `xml.etree.ElementTree` 实现。

**Rationale:**
- 由 `utils` 模块统一封装 JMeter XML 元素创建，避免各 JMX 生成模块重复实现
- Python 标准库，无需额外依赖
- JMX XML 结构相对简单，标准库足够

**Alternatives considered:**
- **lxml**: 功能更强大但需要额外依赖
- **字符串拼接**: 容易出错，难以维护
- **各模块自行使用 xml.etree.ElementTree**: 重复代码多，约定不一致

### 使用 JMeter XML 模板文件

**Decision:** 基础 JMX 元素使用预定义的 XML 模板，动态替换内容。

**Rationale:**
- JMeter XML 结构固定，模板清晰
- 避免手动构建复杂的 XML 层次
- 便于理解和维护

**Alternatives considered:**
- **完全动态构建**: 代码复杂，难以维护
- **JMeter GUI 录制后修改**: 无法自动化

### 线程组顺序处理

**Decision:** 按照 SetupThreadGroup (DDL) → SetupThreadGroup (共享内存) → 写入线程组 → 查询线程组的顺序生成。

**Rationale:**
- 符合规格书要求的执行顺序
- SetupThreadGroup 在常规线程组之前执行
- 写入在查询之前，确保查询有数据

**Alternatives considered:**
- **按用户配置顺序**: 不符合规格书要求
- **动态依赖关系**: 过于复杂

### 变量命名约定

**Decision:** 使用 JMeter 变量命名约定 `${变量名}`，变量名与配置参数一致。

**Rationale:**
- JMeter 标准约定
- 便于识别和修改
- 支持通过参数覆盖

**Alternatives considered:**
- **硬编码值**: 不灵活
- **自定义命名**: 不符合 JMeter 约定

### 共享内存初始化集成

**Decision:** 调用 `shared-memory-initializer` 模块生成 JSR223PreProcessor 组件，插入到 SetupThreadGroup 中。

**Rationale:**
- 职责分离：共享内存初始化逻辑由独立模块负责
- 复用性：其他模块也可复用共享内存加载组件
- 可测试性：共享内存加载逻辑可独立测试
- 数据结构采用 `List[List[Any]]`（行优先）+ 列顺序列表，兼顾直接写入和PreparedStatement两种策略

**Alternatives considered:**
- **在模块内实现共享内存加载**：职责不清晰，难以维护

### DDL SetupThreadGroup 返回结构

**Decision:** `generate_ddl_setup_thread_group` 返回**平铺列表**:`[SetupThreadGroup, hashTree, JDBCSampler, hashTree, JDBCSampler, hashTree, ...]`。`hashTree` 元素保留 JMeter XML 嵌套结构(JDBCSampler 作为其子节点),同时各 sampler 同步平铺到顶层,调用方可单层遍历同时定位 `SetupThreadGroup` 与 `JDBCSampler`,无需递归 `hashTree`。

**Rationale:**
- 调用方(`JMXAssembler`)通常按"元素出现顺序"做 XML 序列化,平铺列表可直接 `extend` 到 JMX 顶层序列,无需区分嵌套/扁平
- 单元测试断言("列表里能查到 `JDBCSampler` tag"、`num_threads` 出现在 ThreadGroup 文本)只扫单层,平铺列表与该断言约定对齐

**Alternatives considered:**
- **纯嵌套**(`[SetupThreadGroup, hashTree(嵌套所有 sampler)]`):调用方需递归 `hashTree` 才能定位 sampler,API 不友好
- **纯扁平**(`[SetupThreadGroup, JDBCSampler, hashTree, JDBCSampler, hashTree, ...]`,丢掉 hashTree 嵌套):破坏 JMeter XML 实际嵌套结构,无法直接序列化

### 查询线程组 Query Type 决策

**Decision:** 查询线程组的 JDBCSampler `queryType` **固定为 `Prepared Select Statement`**,统一通过 `?` 占位符 + `JSR223PreProcessor` 绑定参数执行。`QueryConfig` **不**包含 `mode` 字段,不支持 `statement` 模式(将参数拼接进 SQL 字符串)。

**Rationale:**
- 遵循 `docs/specs/kwdb-svt-test-plan-generator-spec.md` v1.4 (2026-06-15) 决策:**移除 `query_config.mode` 属性,查询统一走 prepared_statement**
- PreparedStatement 路径唯一,生成器只需维护一种绑定逻辑,降低参数注入与转义复杂度
- 占位符无法绑定到具体列(如 `LIMIT ?`)时,由 `TestConfig` 校验阶段直接报错(spec v1.4 §查询配置备注)

**Cross-change dependency:**
> ⚠️ 此前 config-parser 模块已按 spec v1.4 移除 `QueryConfig.mode`。本模块 `query_groups.generate_query_thread_groups` 必须与该决策一致,不得引入 `mode` 字段或额外 `queryType` 分支。

### 写入线程组 Sampler 类型决策

**Decision:** 写入线程组的 Sampler 类型由 `WriteConfig.mode` 决定:

**Decision:** 写入线程组的 Sampler 类型由 `WriteConfig.mode` 决定：

| 写入模式 | Sampler 类型 | PreProcessor |
|----------|-------------|-------------|
| `batch_prepared` | `JSR223Sampler`（Groovy JDBC batch） | `JSR223PreProcessor` 准备批次数据 |
| `single_prepared` | `JDBCSampler`（Prepared Update Statement） | `JSR223PreProcessor` 绑定参数 |
| `single_insert` | `JDBCSampler`（Update Statement） | `JSR223PreProcessor` 绑定参数 |
| `batch_insert` | `JDBCSampler`（Update Statement） | `JSR223PreProcessor` 绑定参数 |
| `schemaless` | `JSR223Sampler`（Groovy line protocol） | T2 |

**Rationale:**
- `batch_prepared` 必须使用 `JSR223Sampler`：JMeter `JDBCSampler` 的 `Prepared Update Statement` 每次只绑定一组参数，无法实现真正的 JDBC batch（`addBatch/executeBatch`）。必须通过 Groovy 脚本直接操作 JDBC `PreparedStatement`。
- `JSR223PreProcessor` 负责数据准备：`batch_prepared` 的 PreProcessor 从共享内存行种子总集随机拷贝连续 `batch_lines` 行、装配时间戳和设备标识，写入线程变量 `__BATCH_ROWS_${tableName}` 供 Sampler 读取。
- 详细 Groovy 脚本见 `write-strategies/design.md` §JSR223Sampler 用于 batch_prepared。

**Cross-change dependency:**
> ⚠️ 本模块的 Sampler 类型决策依赖于 `write-strategies` 模块的定义。具体约束见 `../write-strategies/design.md` §JSR223Sampler 用于 batch_prepared。本模块实现者必须与 write-strategies 模块保持一致，不得独立决定 `batch_prepared` 使用 `JDBCSampler`。

## Risks / Trade-offs

### Risk: JMeter XML 版本兼容性
**Mitigation:** 测试生成的 JMX 文件在 JMeter 5.5+ 中可打开，文档中注明版本要求。

### Risk: Groovy 脚本安全性和复杂性
**Mitigation:** 简化脚本逻辑，仅实现数据加载。未来可考虑将脚本提取为独立文件。

### Trade-off: 不支持自定义 JMeter 插件
**Rationale:** 规格书中未要求，保持简单。未来可通过扩展添加。

## Migration Plan

无需迁移。这是一个新功能模块。