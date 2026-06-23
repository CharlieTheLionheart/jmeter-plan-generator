## Why

KaiwuDB SVT 测试计划生成器需要控制写入和查询的吞吐量。JMeter 的 ConstantThroughputTimer 用于控制线程组的目标吞吐量。

## What Changes

- 新增吞吐量控制模块，支持：
  - 为每个写入线程组生成 ConstantThroughputTimer
  - 为每个查询线程组生成 ConstantThroughputTimer
  - 计算 per-thread 吞吐量（`throughput / num_threads`）
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