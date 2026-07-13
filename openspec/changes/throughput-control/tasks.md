# Tasks: throughput-control

## 0. 范围与依赖确认

- [x] 0.1 确认范围：生成 `ConstantThroughputTimer` XML 元素；写入引用 `${write_throughput}` UDV；查询嵌入字面数值
- [x] 0.2 确认 `throughput` 单位为次/分钟（JMeter 原生单位）
- [x] 0.3 确认 `calcMode=0`（This thread only），不设额外下限
- [x] 0.4 确认 `${write_throughput}` 由 `test_plan.generate_user_defined_variables` 注入，默认值 120（次/分钟）
- [x] 0.5 确认 `QueryConfig.throughput` 直接喂 timer，**不**走 UDV；多端协调由调用流水线负责

## 1. 模块骨架

- [ ] 1.1 创建 `src/throughput_control/__init__.py` 导出 `ThroughputTimerGenerator` 与 `DEFAULT_WRITE_THROUGHPUT = 120.0`
- [ ] 1.2 创建 `src/throughput_control/throughput_timer_generator.py`
- [ ] 1.3 模块 docstring 说明三职责：build write timer / build query timer / expose default
- [ ] 1.4 在 `src/throughput_control/__init__.py` 中加接口隔离注释引导（design §"模块路径"）

## 2. ConstantThroughputTimer 元素生成

- [ ] 2.1 实现 `generate_write_timer()` 返回引用 `${write_throughput}` 的 timer
- [ ] 2.2 实现 `generate_query_timer(query_throughput)` 返回嵌入字面数值的 timer；参数为 float，转 `str()` 后作为 `throughput` 属性
- [ ] 2.3 创建 `<ConstantThroughputTimer>` 元素，`testclass="ConstantThroughputTimer"`、`guiclass="TestBeanGUI"`
- [ ] 2.4 添加 `<stringProp name="ThroughputTimer.delay">${...}</stringProp>` 元素
- [ ] 2.5 添加 `<intProp name="calcMode">0</intProp>`

## 3. 合法性校验（迁移到 config_parser 阶段）

- [ ] 3.1 `config_parser/models.py::WriteConfig`：`throughput` 字段约束 `ge=0` 改为 `gt=0`
- [ ] 3.2 `config_parser/models.py::QueryConfig`：`throughput` 字段约束 `ge=0` 改为 `gt=0`
- [ ] 3.3 两字段校验错误消息明确 "throughput must be > 0"

## 4. UDV 注入（write_throughput 默认 120）

- [ ] 4.1 `test_plan.generate_user_defined_variables` 扩展：注入 `${write_throughput}` 字段，默认值 120.0
- [ ] 4.2 不注入 `${query_throughput}` UDV（per design 决策"查询不引用 UDV"）
- [ ] 4.3 `test_plan.py` docstring 加"write_throughput UDV 默认"说明

## 5. jmx_skeleton_generator 调用迁移

- [ ] 5.1 `src/jmx_skeleton_generator/generators/write_groups.py`：删除 inline `constant_throughput_timer_element(...)`；改为 `from throughput_control import generate_write_timer`
- [ ] 5.2 `src/jmx_skeleton_generator/generators/query_groups.py`：删除 inline `constant_throughput_timer_element(...)`；改为 `from throughput_control import generate_query_timer`；传 `qc.throughput` 字面数值
- [ ] 5.3 删除 query-functionality 之前设计的 `throughput_var` 参数与 spec §"Throughput variable reference is caller-controlled" 场景（spec/design/tasks/tests 同步修改）

## 6. 多端协调（**不**实现）

- [ ] 6.1 删除 proposal.md / design.md / review.md §1.4 中"多端吞吐量协调"措辞
- [ ] 6.2 tasks.md §0.5 加注"多端协调由调用流水线负责，本模块不实现"
- [ ] 6.3 单元测试验证：模块内不存在"multi_end / split_throughput / per_end_ratio"等符号

## 7. 单元测试

- [ ] 7.1 测试 `generate_write_timer()` 输出的根元素 tag 为 `ConstantThroughputTimer`
- [ ] 7.2 测试 `calcMode=0` 属性存在
- [ ] 7.3 测试 `throughput` 属性为字符串 `"${write_throughput}"`
- [ ] 7.4 测试 `generate_query_timer(4.0)` 输出的 `throughput` 属性为字符串 `"4"`（**不是** `${query_throughput}`）
- [ ] 7.5 测试 `generate_query_timer(0.016666667)` 嵌入精确值
- [ ] 7.6 测试 `generate_query_timer` 不同值彼此独立
- [ ] 7.7 测试 `generate_user_defined_variables` 输出含 `write_throughput = "120"`
- [ ] 7.8 测试 `generate_user_defined_variables` 输出**不**含 `query_throughput`
- [ ] 7.9 测试 `WriteConfig.throughput=0` 抛 config validation 错误
- [ ] 7.10 测试 `QueryConfig.throughput=-1` 抛 config validation 错误
- [ ] 7.11 运行全部单元测试并通过

## 8. 集成测试

- [ ] 8.1 端到端：生成含 write timer 的 JMX，验证 `ConstantThroughputTimer` 引用 `${write_throughput}`
- [ ] 8.2 端到端：生成含 query timer 的 JMX，验证 `throughput` 是字面数值
- [ ] 8.3 端到端：UDV 解析后含 `write_throughput=120`，**不**含 `query_throughput`
- [ ] 8.4 验证生成的 JMX 为合法 XML（round-trip 解析）

## 9. query-functionality 端连带修改

- [ ] 9.1 `query-functionality/spec.md`：删除或改写 §"Throughput variable reference is caller-controlled"；新增 §"Generate query timer with literal throughput value"
- [ ] 9.2 `query-functionality/design.md`：决策 18 改写为"qc.throughput 直接喂 throughput_control.generate_query_timer"
- [ ] 9.3 `query-functionality/tasks.md`：§7.5 改写（删除 `throughput_var` 参数）
- [ ] 9.4 `query-functionality/tests/jmx_skeleton_generator/test_query_throughput.py`：重写 3 个测试为"字面数值"语义
- [ ] 9.5 `query-functionality/src/.../query_groups.py`：删除 `throughput_var` 参数；改为 `qc.throughput` 直接喂

## 10. Review 修复验证

- [ ] 10.1 review.md §1 / §2 / §3 / §4 / §5 措辞统一到新决策（D1-D5）
- [ ] 10.2 §1 Boundary 翻 ✅ Resolved：throughput 校验在 config_parser 完成；多端协调由 caller 负责
- [ ] 10.3 §3 Test Coverage 翻 ✅ Resolved：新增字面数值 / write UDV 默认值 / config 校验 / 不导出 query_throughput 4 类测试
- [ ] 10.4 §4 Backward 翻 ✅ Pass：唯一接口变化是 `write_throughput` UDV 默认注入；不删除既有变量

## 11. 代码审查

- [ ] 11.1 提交代码审查
- [ ] 11.2 确认 review.md findings 全部解决后方可合并
