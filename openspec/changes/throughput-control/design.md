## Context

吞吐量控制模块负责为写入和查询线程组生成 ConstantThroughputTimer，用于控制目标吞吐量。JMeter 的 ConstantThroughputTimer 使用 `calcMode=0`（This thread only）时，每个线程独立达到目标吞吐量。

## Goals / Non-Goals

**Goals:**
- 为每个写入线程组生成 ConstantThroughputTimer
- 为每个查询线程组生成 ConstantThroughputTimer
- 设置 `calcMode=0`（每个线程独立目标）
- 支持 JMeter 变量引用

**Non-Goals:**
- 不实现动态吞吐量调整
- 不支持其他 calcMode 值（如 all active threads）

## Decisions

### 直接使用配置的 throughput 值

**Decision:** ConstantThroughputTimer 的 `throughput` 属性直接使用配置中的值（`${write_throughput}` 或 `${query_throughput}`），不除以线程数。

**Rationale:**
- `calcMode=0` 表示每个线程独立达到目标吞吐量
- 每个线程都目标达到 `throughput` 样本/分钟
- 集群总吞吐量 = `throughput × 端数 × 线程数`

**Alternatives considered:**
- **除以线程数**: 会导致集群总吞吐量不足

### 变量命名约定

**Decision:** 写入使用 `${write_throughput}`，查询使用 `${query_throughput}`。

**Rationale:**
- 清晰区分写入和查询的吞吐量
- 便于在 User Defined Variables 中定义
- 避免变量名冲突

**Alternatives considered:**
- **使用统一变量名**: 无法区分写入和查询
- **使用表级变量名**: 增加复杂度

### 最小吞吐量限制

**Decision:** 除要求吞吐量值 `> 0` 外，不设置额外最小吞吐量限制。

**Rationale:**
- JMeter `ConstantThroughputTimer` 通过毫秒级延时控制采样间隔，理论无硬性下限，仅受系统时钟精度约束。
- 可支持到 `0.001` 次/分钟级别的极小吞吐量。
- 业务层面的合理值由用户自行决定；生成器不引入无技术必要的硬编码下限。
- 典型配置示例：120 次/分钟。

**Alternatives considered:**
- **设置硬编码下限（如 `0.001`）**: 会排除合理的极低流量场景，无技术必要性。

### 吞吐量单位

**Decision:** 统一使用 JMeter 原生的 **次/分钟** 作为单位，不在生成器或配置层做单位换算。

**Rationale:**
- `ConstantThroughputTimer` 的 `throughput` 字段语义固定为样本/分钟。
- 引入秒、小时等单位需要额外配置解析/换算层，增加复杂度且无必要。
- 用户若需要其他单位表达，应在配置前自行换算为次/分钟。

**Alternatives considered:**
- **支持多种单位并在配置层统一换算**: 增加配置复杂度，超出本模块职责范围。

## Risks / Trade-offs

### Risk: 吞吐量值过大
**Mitigation:** 用户需根据实际情况配置合理的吞吐量值。可添加警告提示。

### Trade-off: 不验证吞吐量值的合法性
**Rationale:** JMeter 会在运行时处理无效值。生成阶段保持简单。

## Migration Plan

无需迁移。这是一个新功能模块。