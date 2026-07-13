## Context

多端协同模块支持使用多个 JMeter 实例协同发压以增大测试压力。每张表独立计算设备范围，同一表在不同实例之间设备号不重叠。

## Goals / Non-Goals

**Goals:**
- 每张表独立计算设备范围
- 生成设备号计算脚本（统一来自单一 helper）
- 支持多端使用相同测试计划
- 输出下一实例的 `device_start`

**Non-Goals:**
- 不实现动态实例发现
- 不实现负载均衡（各端负载相同）
- 不在生成器内输出 "下一端 device_start" 至 JMX sampler / log / 文件

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

**Decision:** 将第一个 Primary Tag 占位符 `${device_code}` 替换为 `device_{local_device_start + (row_index % device_per_thread)}`。

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

### 单一设备号计算 helper（单源，杜绝拷贝漂移）

**Decision:** 在 `utils/preprocessor_helpers.py` 新增 `groovy_calculate_local_device_start_decl()`，返回 Groovy 函数定义：

```groovy
long calculateLocalDeviceStart(long deviceStart, int threadNum, int devicePerThread) {
    if (devicePerThread <= 0) {
        throw new RuntimeException("device_perThread must be > 0: " + devicePerThread)
    }
    return deviceStart + (long) threadNum * (long) devicePerThread
}
```

并通过既有 `all_groovy_decls()` 暴露给 Groovy 脚本运行时。`write_groups.py` 的 `BATCH_PREPARED_PREPROCESSOR_SCRIPT` 与 `single_prepared_strategy.get_preprocessor_code` 都直接调用此 helper，不再 inline `deviceStart + threadNum * devicePerThread` 表达式。

**Rationale:**
- 既有的 inline 算式在 `write_groups.py:38` 与 `single_prepared_strategy.py:78` 是两份等价 Groovy 代码，复制漂移风险
- `utils/preprocessor_helpers.py` 已经有 `calculateDeviceNumber` / `deviceIdentifier` helper；新增 `calculateLocalDeviceStart` 同步名称族
- 边界校验 `devicePerThread > 0` 内嵌于 helper，比 inline 表达式多一层防御

**Alternatives considered:**
- **保留两份 inline**: 复制漂移隐患，与既有 helper 风格不一致
- **抽 Python 端 helper**: Groovy 脚本运行时不能用，跨进程语义不一致

### device_start UDV 字段值改为 `${__P(device_start,1)}` 函数引用

**Decision:** `test_plan.generate_user_defined_variables` 把 `device_start` UDV 字段值从字面 `"1"` 改为字符串 `"${__P(device_start,1)}"`；`device_per_thread` 同样改为 `"${__P(device_per_thread,1)}"`。

**Rationale:**
- JMeter 加载 JMX 时解析 `${__P(...)}` 函数，调用 JMeter 属性查表
- `-Jdevice_start=1001` 启动 JMeter 时，JMeter 属性被覆盖；UDV 字段值动态解析为 `"1001"` 而不是字面 `"1"`
- 多端流水线可直接用 `jmeter -Jdevice_start=N -n -t plan.jmx` 切换起点设备号，**无需修改 JMX 文件**
- 与 throughput-control 的 `${write_throughput}` 形成统一约定：runtime 可覆盖的字段走 `${__P(name,default)}` 模式

**Alternatives considered:**
- **保留字面值 "1"**: 运行时不可调，多端流水线要修改 JMX 文件才生效
- **保留单一变量引用 `${device_start}`**: JMeter 函数语法错误——UDV 字段值不应含未求值的 JMeter 变量引用

### 多端编排：编排流水线职责

**Decision:** 多端编排（启动多 JMeter 实例、计算每端 `device_start`、捕获下一端起点）由调用测试计划的外部流水线脚本实现；生成器**不**在 JMX 内插入任何用于"告诉流水线下一端"信息的 sampler / listener / log / 文件。

**Rationale:**
- review §0 范围决策已敲定
- 在 JMX 中放 `BeanShellSampler` 输出启动下一端 device_start 会让生成器与 orchestration layer 耦合
- 外部流水线 `bash/python` 直接算 `device_start + Σ num_threads × device_per_thread` 比依赖生成器副作用更稳
- 若未来编排需求变化（如改用 k8s job），换 orchestration 比改 JMX 模板成本低

**Alternatives considered:**
- **生成器加 log Sampler**: 越权 + 增加 JMX 体积 + 难调试
- **生成器写 config.json**: 与 YAGNI 冲突
- **生成器暴露 REST endpoint**: 完全错位

## Migration Plan

迁移面：
- `test_plan.py:49` UDV `device_start` / `device_per_thread` 字段值由字面改 `${__P(...)}` 函数引用
- `utils/preprocessor_helpers.py` 新增 `groovy_calculate_local_device_start_decl()` 与 `all_groovy_decls()` 暴露
- `write_groups.py:38` `BATCH_PREPARED_PREPROCESSOR_SCRIPT` 改用 helper
- `write_strategies/single_prepared_strategy.py:78-83` 改用 helper

不需要 yaml 配置 schema 变更。