## Why

KaiwuDB SVT 测试计划生成器支持使用多个 JMeter 端协同发压以增大测试压力。每张表独立计算设备范围，同一表在不同端之间设备号不重叠。

## What Changes

- 新增多端协同模块，支持：
  - 每张表独立计算设备范围
  - 设备号计算公式：`local_device_start = device_start + thread_index * device_per_thread`
  - 下一发压端起始设备号：`本端起始设备号 + num_threads * device_per_thread`
  - 每个线程组生成 BeanShell/JSR223 脚本计算设备号
  - 多端使用相同的测试计划（含 throughput）
  - 不同表的设备范围可以重叠

## Capabilities

### New Capabilities
- `multi-end-coordination`: 多端协同发压能力

### Modified Capabilities
（无）

## Impact

- 依赖 throughput-control 模块提供吞吐量控制
- 在 JSR223PreProcessor 中生成设备号计算脚本
- 支持通过 `device_start` 参数划分设备范围
- 便于横向扩展测试压力