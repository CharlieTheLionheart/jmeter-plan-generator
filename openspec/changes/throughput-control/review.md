# Quality Review

## 1. Boundary Conditions

**Status**: ⚠️ Warning

**Findings**:
- 吞吐量值的合法性验证缺失：Design 明确声明"不验证吞吐量值的合法性"，但 JMeter 对无效值（如负数、零、极大值）的运行时行为未说明。
- `calcMode=0` 下每个线程独立达到目标吞吐量，集群总吞吐量 = `throughput × 端数 × 线程数`，当端数或线程数较大时，实际总吞吐量可能远超用户预期，存在配置误用风险。
- 极低吞吐量场景（如 `0.016666667`，即 1 次/分钟）在 spec 中已覆盖；最小吞吐量已决策为仅要求 `> 0`，不设置额外下限。
- 多端协同时使用相同 throughput，但未说明当各端线程数不一致时，如何保证每端总吞吐量符合预期。

**Open Questions**:
1. ✅ **最小吞吐量**：已决策——不设置额外最小阈值，仅要求吞吐量值 `> 0`；JMeter 使用毫秒级延时，理论可支持到 `0.001` 次/分钟级别；典型配置为 120 次/分钟。
2. ✅ **吞吐量单位**：已决策——统一使用 JMeter 原生次/分钟单位，不在生成器或配置层做单位换算；用户需在配置前自行换算。

**Recommendations**:
- 在 spec 中补充吞吐量有效范围为 `> 0`，并说明不设置额外最小下限的决策；
- 在配置文档中增加总吞吐量计算公式说明，提醒用户 `calcMode=0` 的放大效应；
- 在配置文档中显式声明吞吐量单位为次/分钟，用户需自行完成其他单位到次/分钟的换算。

## 2. Rollback Plan

**Status**: ✅ Pass

**Findings**:
- 纯新增模块，Migration Plan 已声明"无需迁移"。
- 回滚操作仅为移除 ConstantThroughputTimer 元素的生成逻辑，不影响已有线程组结构。
- 无数据迁移、无 schema 变更、无外部状态依赖。

**Recommendations**:
- 无。新功能天然可回滚。

## 3. Test Coverage

**Status**: ⚠️ Warning

**Findings**:
- Spec 已覆盖写入/查询线程组的 timer 生成、`calcMode=0`、变量引用、低吞吐量浮点值等主路径场景。
- 缺失以下测试要求：
  - 吞吐量值为 `0` 或负数时的生成行为（拒绝还是静默处理）；
  - 缺失 `write_throughput` / `query_throughput` 变量定义时 JMeter 的运行表现；
  - 多端协同下各端 timer 生成的一致性验证；
  - 生成的 JMX 中 ConstantThroughputTimer 的 XML 结构校验（如 `intProp` 标签完整性与属性名正确性）。

**Recommendations**:
- 在 spec 中补充负向场景：零/负吞吐量输入、缺失变量定义时的预期行为；
- 增加 JMX 输出结构校验测试，验证 `ConstantThroughputTimer` 节点及其子属性；
- 增加多端协同集成测试，确保各端生成的 timer 使用相同变量名与 `calcMode`。

## 4. Backward Compatibility

**Status**: ✅ Pass

**Findings**:
- 无 Modified Capabilities，无破坏性变更。
- 依赖 direct-insert-write 和 query-functionality 的线程组输出，未修改其接口契约。
- `${write_throughput}` 与 `${query_throughput}` 为新增变量约定，不影响既有变量。

**Recommendations**:
- 在 User Defined Variables 的生成文档中说明新变量的默认值策略（如未配置时的行为）；
- 若下游模块未来需要读取吞吐量配置，建议将变量名作为常量导出，避免硬编码。

## 5. Task Granularity

**Status**: ❌ Fail

**Findings**:
- `tasks.md` 已被删除（当前目录下不存在），无法核对任务粒度。
- 本模块虽逻辑相对集中（仅生成 ConstantThroughputTimer），但仍涉及多个独立切面：
  - 写入线程组 timer 生成；
  - 查询线程组 timer 生成；
  - `calcMode=0` 的固定设置；
  - 变量引用字符串的拼装；
  - 多端协同下的相同 throughput 处理。
  若任务粒度过粗，将难以并行开发和独立验证。
- Design 中 Open Questions 已全部解决，无需再为配置解析/换算层预留任务边界。

**Recommendations**:
- 将实现拆分为以下最小可验证任务：
  1. 实现 `ConstantThroughputTimer` XML 节点生成器（通用，接受 throughput 值与 calcMode）；
  2. 实现写入线程组 timer 附加逻辑（使用 `${write_throughput}`）；
  3. 实现查询线程组 timer 附加逻辑（使用 `${query_throughput}`）；
  4. 实现多端协同时的吞吐量一致性保证（验证各端使用相同变量引用）；
  5. 编写单元测试：验证 timer 节点结构、`calcMode=0`、变量引用字符串；
  6. 编写边界测试：零/负吞吐量、极小浮点值、缺失变量；
  7. 编写集成测试：端到端生成含 timer 的 JMX 并做 XML 结构校验。
- 每条任务附带验收标准（输入配置片段 → 预期 XML 输出片段）。

## Overall Assessment

`throughput-control` 的提案、Spec 和设计方向清晰，模块职责单一，回滚与兼容性风险极低。但存在以下阻塞项：

1. **任务粒度未细化**：`tasks.md` 缺失，无法进入实现阶段；建议按上述推荐拆分任务，每项可独立验证。
2. **边界条件待补齐**：零/负值处理未明确，需在 spec 中补充。

在补齐 `tasks.md`、明确零/负值边界条件后，本变更可以进入实现阶段。
