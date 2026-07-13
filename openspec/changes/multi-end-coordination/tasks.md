# Tasks: multi-end-coordination

## 0. 范围决策确认（Review §0 已决策）

- [x] 0.1 确认多端协同**发压由外部流水线脚本负责**，不在生成器职责范围
- [x] 0.2 生成器仅保证 JMX 模板支持通过 JMeter 属性（如 `${__P(device_start,1)}`）读取 `device_start`
- [x] 0.3 确认以下均归属外部编排：device_start 输出位置、注入机制、冲突验证
- [x] 0.4 设备号计算公式统一使用 `${__threadNum}`

## 1. UDV `${__P(...)}` 函数引用注入点（design 决策）

- [ ] 1.1 `src/jmx_skeleton_generator/generators/test_plan.py:49` 把 `"device_start"` UDV 字段值改为字面字符串 `"${__P(device_start,1)}"`
- [ ] 1.2 同处把 `"device_per_thread"` UDV 字段值改为字面字符串 `"${__P(device_per_thread,1)}"`
- [ ] 1.3 `conn_pool_size` / `db_username` / `db_password` / `db_url` / `test_duration` / `write_throughput` 保持既有字段值（不统一改写，仅标注）

## 2. 单一设备号计算 helper（design 决策 "单一 helper"）

- [ ] 2.1 `src/utils/preprocessor_helpers.py` 新增 `groovy_calculate_local_device_start_decl()` 返回 Groovy 函数（边界 `devicePerThread > 0`）
- [ ] 2.2 `all_groovy_decls()` 把新 helper decl 拼接到现有 decls 输出
- [ ] 2.3 `src/jmx_skeleton_generator/generators/write_groups.py:38` `BATCH_PREPARED_PREPROCESSOR_SCRIPT` 改用 `calculateLocalDeviceStart(...)` helper
- [ ] 2.4 `src/write_strategies/single_prepared_strategy.py:78-83` 改用同一个 `calculateLocalDeviceStart(...)` helper（去掉内联 `deviceStart + threadNum * devicePerThread`）
- [ ] 2.5 边界：helper 内 `devicePerThread <= 0` 抛 `RuntimeException`（单点防御）

## 3. 多端编排：生成器**不**实现

- [ ] 3.1 JMX 不包含 `BeanShellSampler` / `JSR223Sampler` / `SampleLog` 用于"输出下一端 device_start"
- [ ] 3.2 集成测试反向验证：渲染完整 JMX 不存在 `device_next_instance` / `multi_end_split` / `next_device_start` 等符号
- [ ] 3.3 文档（`docs/migration-throughput-control.md` 或新增 `docs/multi-end-pipeline-contract.md`）记录流水线的 device_start 计算与 `-J` 注入约定

## 4. 单元测试（design 决策对应的可独立验证用例）

- [ ] 4.1 UDV 字段值测试：渲染后的 UDV XML 中 `device_start == "${__P(device_start,1)}"`（字面字符串，未求值）
- [ ] 4.2 UDV 字段值测试：`device_per_thread == "${__P(device_per_thread,1)}"`
- [ ] 4.3 UDV 不破坏：`write_throughput == "120"`（保持字面）
- [ ] 4.4 helper 函数测试：`calculateLocalDeviceStart` Groovy 函数暴露于 `all_groovy_decls()`
- [ ] 4.5 helper 边界测试：Groovy 内 `devicePerThread = 0` 抛 RuntimeException
- [ ] 4.6 write_groups Groovy 测试：BATCH_PREPARED 脚本不再内联 `deviceStart + threadNum * devicePerThread`
- [ ] 4.7 single_prepared Groovy 测试：get_preprocessor_code 调用 helper 同名函数
- [ ] 4.8 JMX 集成测试：完整 JMX 不含 "next_instance" / "BeanShellSampler" 用于 device_start 输出
- [ ] 4.9 -J 属性行为文档测试（手动 JMeter 调用）：`-Jdevice_start=1001` 启动后 `vars.get("device_start")` 返回 1001

## 5. 集成测试

- [ ] 5.1 端到端：完整 JMX 内含 UDV `${__P(device_start,1)}` 字段
- [ ] 5.2 端到端：BATCH_PREPARED 与 SINGLE_PREPARED 两条路径设备号公式共享 helper
- [ ] 5.3 JMX 为合法 XML（round-trip 解析）

## 6. Review 修复验证

- [x] 6.1 review §0 范围决策已敲定并落到本 tasks §0
- [x] 6.2 review §1 边界：`device_per_thread > 0` 由 helper 承担
- [x] 6.3 review §1 边界：`device_start` UDV 走 `${__P(name,default)}` 模式
- [x] 6.4 review §3 测试覆盖：新加 §4 9 条用例
- [x] 6.5 review §4 向后兼容：UDV 字段值变更不影响单端用户体验（默认 1）
- [x] 6.6 review §5 任务粒度：本 tasks.md §1-§5 拆分更细

## 7. 代码审查

- [ ] 7.1 提交代码审查
- [ ] 7.2 确认 review.md findings 全部解决后方可合并

