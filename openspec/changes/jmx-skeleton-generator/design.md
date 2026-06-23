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
- 不实现具体的写入逻辑（由 direct-insert-write 模块实现）
- 不实现具体的查询逻辑（由 query-functionality 模块实现）
- 不实现吞吐量控制（由 throughput-control 模块实现）

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

## Risks / Trade-offs

### Risk: JMeter XML 版本兼容性
**Mitigation:** 测试生成的 JMX 文件在 JMeter 5.5+ 中可打开，文档中注明版本要求。

### Risk: Groovy 脚本安全性和复杂性
**Mitigation:** 简化脚本逻辑，仅实现数据加载。未来可考虑将脚本提取为独立文件。

### Trade-off: 不支持自定义 JMeter 插件
**Rationale:** 规格书中未要求，保持简单。未来可通过扩展添加。

## Migration Plan

无需迁移。这是一个新功能模块。