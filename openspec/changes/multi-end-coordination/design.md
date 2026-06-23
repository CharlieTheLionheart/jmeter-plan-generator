## Context

多端协同模块支持使用多个 JMeter 实例协同发压以增大测试压力。每张表独立计算设备范围，同一表在不同实例之间设备号不重叠。

## Goals / Non-Goals

**Goals:**
- 每张表独立计算设备范围
- 生成设备号计算脚本
- 支持多端使用相同测试计划
- 输出下一实例的 `device_start`

**Non-Goals:**
- 不实现动态实例发现
- 不实现负载均衡（各端负载相同）

## Decisions

### 每张表独立计算

**Decision:** 每张表独立计算设备范围，不同表的设备范围可以重叠。

**Rationale:**
- 不同表数据相互独立
- 便于配置管理
- 符合规格书要求

**Alternatives considered:**
- **全局设备池**: 过于复杂
- **表间隔离浪费**: 不必要

### 设备号计算公式

**Decision:** 使用公式 `local_device_start = device_start + thread_index * device_per_thread`。

**Rationale:**
- 线程间设备号连续
- 便于追踪
- 符合规格书要求

**Alternatives considered:**
- **随机分配**: 不便于调试
- **全局累加**: 跨表不连续

### 输出下一实例的 device_start

**Decision:** 生成器输出下一实例的 `device_start` 值，供编排工具使用。

**Rationale:**
- 便于自动化部署
- 避免设备号重叠

**Alternatives considered:**
- **用户手动计算**: 容易出错
- **存储在文件**: 增加复杂度

### 第一个 Primary Tag 替换

**Decision:** 将第一个 Primary Tag 占位符 `?ptag1?` 替换为 `device_{local_device_start + (row_index % device_per_thread)}`。

**Rationale:**
- 设备号标识设备
- 符合设计文档要求

**Alternatives considered:**
- **不替换设备号**: 无法区分设备
- **使用其他格式**: 不符合约定

## Risks / Trade-offs

### Risk: device_start 冲突
**Mitigation:** 输出下一实例的 `device_start`，编排工具负责正确传递。

### Trade-off: 设备号循环
**Rationale:** 当前不支持循环使用设备号。如果设备数不足，新数据会覆盖旧数据。

## Migration Plan

无需迁移。这是一个新功能模块。