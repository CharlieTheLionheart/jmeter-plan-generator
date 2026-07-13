## Context

吞吐量控制模块负责为写入和查询线程组生成 ConstantThroughputTimer，用于控制目标吞吐量。JMeter 的 ConstantThroughputTimer 使用 `calcMode=0`（This thread only）时，每个线程独立达到目标吞吐量。

## Goals / Non-Goals

**Goals:**
- 为每个写入线程组生成 ConstantThroughputTimer（引用 `${write_throughput}` UDV 变量）
- 为每个查询线程组生成 ConstantThroughputTimer（直接嵌入字面数值，不引用 UDV 变量）
- 设置 `calcMode=0`（每个线程独立目标）
- UDV 中暴露默认 `${write_throughput}=120`（次/分钟，即每秒 2 次）
- 在 config_parser 阶段拒绝非正吞吐量值

**Non-Goals:**
- 不实现运行时动态吞吐量调整
- 不实现多端吞吐量分摊（由调用流水线负责）
- 不暴露 `${query_throughput}` UDV 变量（查询走字面数值）
- 不支持其他 calcMode 值（如 all active threads）

## Decisions

### 直接使用配置的 throughput 值

**Decision:** ConstantThroughputTimer 的 `throughput` 属性直接使用配置中的值，不除以线程数。

**Rationale:**
- `calcMode=0` 表示每个线程独立达到目标吞吐量
- 每个线程都目标达到 `throughput` 样本/分钟
- 集群总吞吐量 = `throughput × 端数 × 线程数`

**Alternatives considered:**
- **除以线程数**: 会导致集群总吞吐量不足

### 写入 vs 查询吞吐量的差异化处理

**Decision:**
- **写入线程组**：`ConstantThroughputTimer.throughput` 引用 JMeter 变量 `${write_throughput}`；该变量在 UDV 中定义，默认值 `120`（次/分钟 = 每秒 2 次）。
- **查询线程组**：`ConstantThroughputTimer.throughput` 是查询配置中 `QueryConfig.throughput` 数值的字符串形式（如 `"4"`），不走 UDV 变量。

**Rationale:**
- 写入吞吐量通常是全局策略（整个测试计划一种），适合作为 UDV 让运维通过 `-Jwrite_throughput=N` 在 JMeter 启动时覆盖
- 查询吞吐量为每个查询独立（不同查询期望不同 QPS），作为字面数值嵌入到对应 ThreadGroup，无需运行时整体切换
- 用户对两类吞吐量的使用场景不同：写入是 "全表打" 单一负载，查询是 "多表不同频率" 多负载
- `${query_throughput}` UDV 暴露会造成歧义（哪个查询的吞吐？）

**Alternatives considered:**
- **查询也走 `${query_throughput}` UDV**：丧失 per-query 个性化能力
- **查询也走 `${write_throughput}` UDV**：把读 / 写合并语义错位
- **per-query UDV `${q0_throughput}` / `${q1_throughput}`**：增加 UDV 维护面，与"query 不暴露 UDV"原则冲突

### 写入吞吐量默认值 120 (次/分钟)

**Decision:** UDV 中 `${write_throughput}` 默认值 = `120`（次/分钟 = 每秒 2 次）。

**Rationale:**
- 120 次/分钟 = 2 次/秒是 KaiwuDB SVT 场景的常规起步值（避免 0 流量死循环）
- 与既有 `WriteConfig.throughput` 字段 `default=1000.0` 不冲突：后者是 yaml 配置的"每分钟 1000 次"概念，UDV 默认值是"用户未覆盖时"的安全起步值，两者由调用方决定如何衔接
- 与 QueryConfig 默认 `100.0` 区分（读 / 写默认不同，体现不同业务负载）

**Alternatives considered:**
- **默认 0**：无意义，会让 JMeter 永远不发送请求
- **默认 60**（每秒 1 次）：过低
- **默认 1000** 与 `WriteConfig.throughput` 对齐：用户决策明确选 120

### calcMode = 0（This thread only）

**Decision:** ConstantThroughputTimer 的 `calcMode` 固定为 `0`，不做配置化。

**Rationale:**
- `calcMode=0` 是 JMeter 推荐用于"每线程目标 RPS"的模式
- SVT 场景固定此值，无需给用户选择
- 集群总吞吐量 = `${write_throughput} × 端数 × 线程数`，公式由部署侧消化

**Alternatives considered:**
- **多 calcMode 选择**: 与 SVT 用例不匹配，增加配置面

### 吞吐量单位：次/分钟

**Decision:** 统一使用 JMeter 原生的 **次/分钟** 作为单位，不在生成器或配置层做单位换算。

**Rationale:**
- `ConstantThroughputTimer.throughput` 字段语义固定为样本/分钟
- 用户若需要其他单位，应在配置前自行换算

**Alternatives considered:**
- **支持多种单位并在配置层统一换算**: 增加配置复杂度

### 合法性校验在 config_parser 阶段（≥ > 0）

**Decision:** 吞吐量值的合法性校验（`throughput > 0`）由 `config_parser` 的 Pydantic 模型 validator 完成，**不**在 JMX 生成阶段检查。

**Rationale:**
- config_parser 是配置的第一道闸门，校验前置让用户在加载 yaml 阶段就发现问题
- 当前 `WriteConfig.throughput` 已经是 `Field(default=1000.0, ge=0)`：仅要求 `>= 0`，需要改为 `gt=0`（严格 `> 0`）
- 当前 `QueryConfig.throughput` 也是 `Field(default=100.0, ge=0)`：同样改 `gt=0`
- 修改两字段约束 + 加自定义错误消息足够，无需再起 `JmxGenerationError`

**Alternatives considered:**
- **JMX 生成阶段校验**: 用户配置错误延迟到生成阶段，不友好
- **JMeter 运行时校验**: 完全失败于运行时，定位成本高

### 多端吞吐量协调：本模块**不**做

**Decision:** throughput-control 模块**不**实现多端吞吐量分摊、不读取多端配置、不在 JMX 内嵌入"每端比例"标签。每个生成的 JMX 是单端测试计划；多端协同的吞吐量划分由调用流水线（启动 JMeter 的外部编排层）负责。

**Rationale:**
- 与设计文档已敲定的"多端设备号分摊"职责边界一致（design.md §3.6）：测试计划生成器仅生成单一实例的测试计划；多端分摊由调用方处理
- 模块边界清晰：本模块只生成 timer 元素；不做多端策略
- 文档层面（proposal.md / design.md / review §1）之前有"多端使用相同 throughput"的表述，需要在本变更中修正——未来不再有"多端"语义在本模块内讨论

**Alternatives considered:**
- **本模块内做多端分摊**: 越权 + 与设备号职责边界冲突

### 模块路径：`src/throughput_control/`

**Decision:** 实现独立模块于 `src/throughput_control/{__init__.py, throughput_timer_generator.py}`；`jmx_skeleton_generator/generators/write_groups.py` 与 `query_groups.py` 通过该模块生成 timer 而不是 inline `constant_throughput_timer_element(...)` 调用。

**Rationale:**
- 与其他 jmx_skeleton_generator 子方向（已存在的 write_groups / query_groups / ddl_setup）一致——独立子包管理一类 concern
- 后续若新增吞吐相关策略（如 ramp-up、burst pattern）可在本模块内扩展
- 解耦后 jmx_skeleton_generator 内 write_groups / query_groups 体积下降

**Alternatives considered:**
- **保留在 jmx_skeleton_generator 内**: 已有模块糅多类 concern，可读性下降
- **新增 utils 子模块**: utils 偏向静态工具，与"面向 JMeter 元素生成"的 throughput 控制语义错位

## Risks / Trade-offs

### Risk: `${write_throughput}` UDV 默认值与 WriteConfig.throughput 字段默认不一致
**Mitigation:** 文档明确两个默认值的语义差异（UDV 默认 120 是安全起步；yaml 字段默认 1000.0 是配置层的合理猜测）；实际部署时 caller 决定注入哪一个作为生效值。

### Risk: 模块拆分后 write_groups / query_groups 依赖新模块
**Mitigation:** `throughput_control` 模块不引入新依赖，只消费 `utils/xml_helpers.constant_throughput_timer_element`；模块路径解耦不影响运行时性能。

### Trade-off: 不在生成阶段校验 throughput > 0
**Rationale:** config_parser 已前置校验；生成阶段重复校验冗余。

## Migration Plan

1. 新建 `src/throughput_control/` 模块（含 `__init__.py` 与 `throughput_timer_generator.py`）
2. `generate_user_defined_variables` 扩展：注入 `${write_throughput}` 字段，默认 120
3. write_groups.py / query_groups.py 改造：调用 `throughput_control` 模块替换 inline `constant_throughput_timer_element` —— 写线程组传 `${write_throughput}`；查询线程组传 `qc.throughput` 字面数值
4. config_parser 模型 `WriteConfig.throughput` / `QueryConfig.throughput` 约束从 `ge=0` 改 `gt=0`
5. 删除 query-functionality 之前设计的 `throughput_var` 参数与 spec §"Throughput variable reference is caller-controlled" 场景（连带修改 query-functionality/spec.md / design.md / tasks.md 与 test_query_throughput.py）
6. 删除 / 更新本模块之前的 review §1.4 "多端吞吐量协调" Finding 措辞（已与多端设备号职责对齐）
