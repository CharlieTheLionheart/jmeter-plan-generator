## Why

KaiwuDB SVT 测试计划生成器需要控制写入和查询的吞吐量。JMeter 的 ConstantThroughputTimer 用于控制线程组的目标吞吐量。

> **STATUS (2026-09-11)**：原 proposal 第 7 条「支持 JMeter 变量引用（`${write_throughput}`）」已被**反转**为 **cfg 字面烤死** — 写入 timer 现在直接烤死 cfg `WriteConfig.throughput` 字符串字面量，`${write_throughput}` UDV 已移除（commit `187064f` + `0b75075` + `eb6e8d6` + `72aae2d`）。设计动机：「**写入线程组**的 throughput 是 cfg-driven 业务负载，不是运维调参，不应走 `${__P(...)}` 间接层」。查询线程组路径（`${query_throughput}`）的 UDV 引用原本就**从未实现**——查询路径一直是字面量。完整的反向语义对齐见主 spec [docs/specs/kwdb-svt-test-plan-generator-spec.md](../../docs/specs/kwdb-svt-test-plan-generator-spec.md) §2.0 + §Timer 配置段，以及 DCR commit `0b75075`。

## What Changes

- 新增吞吐量控制模块，支持：
  - 为每个写入线程组生成 ConstantThroughputTimer
  - 为每个查询线程组生成 ConstantThroughputTimer
  - 写入 / 查询吞吐量配置值即为每线程目标（**不**做 `throughput / num_threads` 除法，配置值直接作为 `ConstantThroughputTimer.throughput` 引用）
  - 设置 `calcMode=0`（This thread only）
  - 支持 JMeter 变量引用（`${write_throughput}`、`${query_throughput}`）
  - 多端协同时每端使用相同的 throughput

## Capabilities

### New Capabilities
- `throughput-control`: 吞吐量控制能力

### Modified Capabilities
（无）

## Impact

- 依赖 direct-insert-write 模块提供写入线程组
- 依赖 query-functionality 模块提供查询线程组
- 在线程组中附加 ConstantThroughputTimer
- 支持 JMeter 变量覆盖