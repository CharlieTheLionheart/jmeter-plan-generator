# Tasks: multi-end-coordination

## 0. 范围决策确认（Review §0 已决策）

- [ ] 0.1 确认多端协同**发压由外部流水线脚本负责**，不在生成器职责范围
- [ ] 0.2 生成器仅保证 JMX 模板支持通过 JMeter 属性（如 `${__P(device_start,1)}`）读取 `device_start`
- [ ] 0.3 确认以下均归属外部编排：device_start 输出位置、注入机制、冲突验证
- [ ] 0.4 设备号计算公式统一使用 `${__threadNum}`

## 1. 模块骨架

- [ ] 1.1 创建 `src/multi_end_coordination/__init__.py` 导出 `DeviceRangeCalculator`
- [ ] 1.2 创建 `src/multi_end_coordination/device_range_calculator.py`
- [ ] 1.3 添加模块 docstring 说明本模块职责和范围边界

## 2. 设备范围计算工具

- [ ] 2.1 实现 `calculate_local_device_start(device_start, thread_num, device_per_thread)` 返回设备起始值
- [ ] 2.2 公式：`device_start + thread_num * device_per_thread`
- [ ] 2.3 实现 `calculate_device_number(device_start, thread_num, device_per_thread, row_index)` 返回行内设备号
- [ ] 2.4 公式：`device_start + thread_num * device_per_thread + (row_index % device_per_thread)`
- [ ] 2.5 实现 `calculate_device_range(device_start, device_per_thread, num_threads)` 返回全局设备范围
- [ ] 2.6 边界：`device_per_thread <= 0` 时抛 `ValueError`（除零保护）
- [ ] 2.7 边界：`device_start < 0` 时记录警告但不阻塞（负数设备号取决于 KaiwuDB 支持情况）

## 3. JMX 设备号模板支持

- [ ] 3.1 确认 JMX 中使用 `${__P(device_start,1)}` 读取 `device_start`
- [ ] 3.2 确认所有 `${__threadNum}` 引用统一
- [ ] 3.3 不在 User Defined Variables 中重复定义 `device_start`（避免与 `${__P}` 冲突）

## 4. Primary Tag 替换支持

- [ ] 4.1 实现 `replace_first_ptag_placeholder(row_aggregate_csv_path, device_number)` 替换 `${device_code}`
- [ ] 4.2 替换为 `device_{device_number}`
- [ ] 4.3 在 `direct-insert-write` 的 PreProcessor 中调用此工具

## 5. 单元测试

- [ ] 5.1 测试设备号计算公式正确性（已知输入验证输出）
- [ ] 5.2 测试 `device_per_thread = 0` 抛 `ValueError`
- [ ] 5.3 测试 `device_per_thread = 1` 正常工作
- [ ] 5.4 测试极大 `device_start` 值不溢出（Python int 无限宽）
- [ ] 5.5 测试 `row_index % device_per_thread` 在边界行为正确
- [ ] 5.6 测试 Primary Tag 替换输出格式
- [ ] 5.7 运行全部单元测试并通过

## 6. 集成测试

- [ ] 6.1 端到端：验证生成 JMX 中的设备号计算使用 `${__threadNum}`
- [ ] 6.2 端到端：验证多端场景下各端使用相同的公式和变量引用
- [ ] 6.3 验证设备范围重叠时（外部编排责任）生成器不报错

## 7. Review 修复验证

- [ ] 7.1 确认边界值（device_per_thread > 0 防御）已在 §2.6 实现
- [ ] 7.2 确认 `device_start` 最小值建议 >= 1 已在文档中说明
- [ ] 7.3 确认 JMX 中 `device_start` 统一使用 `${__P(device_start,1)}`
- [ ] 7.4 确认冲突验证责任归属外部编排（生成器不做跨实例校验）

## 8. 代码审查

- [ ] 8.1 提交代码审查
- [ ] 8.2 确认 review.md findings 全部解决后方可合并
