# Tasks: throughput-control

## 0. 范围与依赖确认

- [ ] 0.1 确认范围：仅生成 `ConstantThroughputTimer` XML 元素，附加到写入/查询线程组
- [ ] 0.2 确认 `throughput` 值单位为次/分钟（JMeter 原生单位）
- [ ] 0.3 确认 `calcMode=0`（This thread only），不设置额外下限（仅要求 > 0）
- [ ] 0.4 确认 `${write_throughput}` 和 `${query_throughput}` 由 `UserDefinedVariablesGenerator` 定义
- [ ] 0.5 确认多端协同时各端使用相同变量引用（变量值由外部编排注入）

## 1. 模块骨架

- [ ] 1.1 创建 `src/throughput_control/__init__.py` 导出 `ThroughputTimerGenerator`
- [ ] 1.2 创建 `src/throughput_control/throughput_timer_generator.py`
- [ ] 1.3 添加模块 docstring 说明本模块职责

## 2. ConstantThroughputTimer 元素生成

- [ ] 2.1 实现 `generate_timer(throughput_value, calc_mode=0)` 返回 XML Element
- [ ] 2.2 创建 `<ConstantThroughputTimer>` 元素，`testclass="ConstantThroughputTimer"`、`guiclass="TestBeanGUI"`
- [ ] 2.3 添加 `<stringProp name="ThroughputTimer.delay">${...}</stringProp>` 引用变量
- [ ] 2.4 添加 `<intProp name="calcMode">0</intProp>`
- [ ] 2.5 实现 `generate_write_timer()` 返回使用 `${write_throughput}` 的 timer
- [ ] 2.6 实现 `generate_query_timer()` 返回使用 `${query_throughput}` 的 timer

## 3. 边界条件处理

- [ ] 3.1 `throughput <= 0`：抛 `JmxGenerationError`（不在生成器静默处理）
- [ ] 3.2 极小浮点值（如 `0.016666667`）：使用精确值，不做截断
- [ ] 3.3 验证生成的 XML `throughput` 属性引用变量名正确

## 4. 线程组附加逻辑

- [ ] 4.1 `attach_to_thread_group(thread_group_element, timer_element)` 将 timer 作为子元素添加到线程组
- [ ] 4.2 确认 timer 在线程组的 `hashTree` 内而非直接子元素

## 5. 单元测试

- [ ] 5.1 测试 `generate_timer()` 输出的根元素 tag 为 `ConstantThroughputTimer`
- [ ] 5.2 测试 `calcMode=0` 属性存在
- [ ] 5.3 测试变量引用字符串正确
- [ ] 5.4 测试 `throughput <= 0` 抛 `JmxGenerationError`
- [ ] 5.5 测试极小浮点值（`0.016666667`）生成精确值
- [ ] 5.6 测试 `generate_write_timer()` 和 `generate_query_timer()` 变量名不同
- [ ] 5.7 测试输出 XML 可被 `xml.etree.ElementTree` 解析
- [ ] 5.8 运行全部单元测试并通过

## 6. 集成测试

- [ ] 6.1 端到端测试：生成含 timer 的 JMX，验证 `ConstantThroughputTimer` 出现在线程组内
- [ ] 6.2 端到端测试：多端场景下各端生成的 timer 使用相同变量名 `${write_throughput}`/`${query_throughput}`
- [ ] 6.3 验证生成的 JMX 为合法 XML（round-trip 解析）

## 7. Review 修复验证

- [ ] 7.1 确认 spec 中已补充吞吐量有效范围 `> 0` 及最小值说明
- [ ] 7.2 确认配置文档中已补充总吞吐量计算公式（`calcMode=0` 放大效应）
- [ ] 7.3 确认配置文档中已声明吞吐量单位为次/分钟
- [ ] 7.4 确认单元测试覆盖零/负吞吐量、极小浮点值场景

## 8. 代码审查

- [ ] 8.1 提交代码审查
- [ ] 8.2 确认 review.md findings 全部解决后方可合并
