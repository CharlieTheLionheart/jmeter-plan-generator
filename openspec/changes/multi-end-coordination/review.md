# Quality Review

## 0. 范围决策（Scope Decision）
**Status**: ✅ 已决策

**结论**: 多端协同**发压**由调用测试计划的**流水线脚本**负责实现，**不在测试计划生成器的职责范围内**。本模块中的多端协同描述仅用于**说明多端协同发压的可能性和方法**，并非生成器需要实现的功能。

**因此以下原 Open Questions 均归属外部编排/流水线，不由生成器负责，视为已关闭**：
- `device_start` 输出位置（控制台/文件/环境变量）→ 由流水线脚本决定与捕获。
- `device_start` 注入机制与 `${__P(device_start,1)}` 读取约定 → 由流水线脚本注入；生成器仅保证模板可通过 JMeter 属性读取。
- 设备号冲突验证责任 → 由外部编排工具负责，生成器不做跨实例冲突校验。

**对生成器的唯一要求**: 生成的 JMX 模板支持通过 JMeter 属性（如 `${__P(device_start,1)}`）读取 `device_start`，使流水线脚本能在多端场景下注入不同起始值。其余协同逻辑（输出、注入、冲突校验、编排）一概不在生成器范围内。

## 1. Boundary Conditions
**Status**: ⚠️ Warning
**Findings**: 设备号计算公式的边界条件未充分覆盖。当前公式 `local_device_start = device_start + thread_index * device_per_thread` 未定义当 `device_start` 为 0 或负数时的行为。`row_index % device_per_thread` 在 `device_per_thread = 0` 时会导致除零错误。此外，当设备号总数超过数据库字段允许的最大值（如 INT 上限）时，未定义溢出处理策略。规格书中未提及 `device_start` 的合法取值范围校验。输出位置和注入机制也未明确。
**Open Questions**:
1. 下一实例的 `device_start` 输出到哪里？（控制台、文件、环境变量？）
2. `device_start` 需要通过 JMeter 命令行参数（如 `-Jdevice_start=N`）注入，JMX 中是否应统一使用 `${__P(device_start,1)}` 读取？用户自定义变量 Arguments 中是否还需要保留 `device_start` 项？
**Recommendations**: 在生成器中增加 `device_per_thread > 0` 的前置校验；明确 `device_start` 的最小值（建议 >= 1）；补充设备号溢出的防御逻辑或告警机制；在规格书中增加边界值场景的异常处理要求；明确下一实例 `device_start` 的输出形式（建议优先输出到控制台/日志，便于编排工具捕获）；统一 JMX 中 `device_start` 的读取方式为 `${__P(device_start,1)}`，并清理用户自定义变量中的重复项以避免配置歧义。

## 2. Rollback Plan
**Status**: ✅ Pass
**Findings**: 该模块为纯新增功能，不修改现有代码路径。Migration Plan 明确标注"无需迁移"。多端协同功能可通过不传递 `device_start` 参数直接回退到单端模式，现有单端测试计划不受影响。`device_start` 默认值机制（如 `${__P(device_start,1)}`）天然支持向后兼容。
**Recommendations**: 保持当前无状态设计，确保单端与多端模式使用同一套测试计划模板。

## 3. Test Coverage
**Status**: ⚠️ Warning
**Findings**: 规格书覆盖了正常场景（单表设备范围计算、线程本地设备起始值、Groovy 脚本生成、多实例协同、跨表范围重叠、下一实例 device_start 输出、Primary Tag 替换）。但缺少以下测试场景：多实例间设备号冲突的验证测试、device_per_thread 或 num_threads 为边界值（如 1、极大值）时的行为、设备号循环覆盖场景（当前设计明确不支持循环，但需有测试确认行为）、以及 `device_start` 通过命令行注入的端到端集成测试。此外，是否需要在运行时或生成阶段验证设备号不冲突，尚未明确。
**Open Questions**:
1. 是否需要验证设备号不冲突？
**Recommendations**: 补充多实例冲突检测的集成测试用例；增加边界值参数（device_per_thread=1, num_threads=1, 极大 device_start）的单元测试；补充命令行参数 `-Jdevice_start=N` 注入的端到端测试场景；若设备号循环覆盖不在本次范围，需在测试文档中明确标记为已知限制。若决定引入冲突验证，应在生成阶段增加设备范围重叠检查（同一表跨实例），并补充对应的自动化测试。若决定不引入，需在规格书中明确声明冲突验证由外部编排工具负责。

## 4. Backward Compatibility
**Status**: ✅ Pass
**Findings**: 本模块为新增能力，不修改现有单端测试计划生成逻辑。`device_start` 参数通过 JMeter 属性注入，默认值为 1，现有单端用户无需任何改动。多端与单端共用同一测试计划模板，仅通过外部参数区分，对现有用户零影响。
**Recommendations**: 在文档中明确说明单端用户无需关注此模块；确保 `device_start` 默认值在各处（JMX 属性、用户自定义变量）保持一致。

## 5. Task Granularity
**Status**: ⚠️ Warning
**Findings**: 设计文档中的任务粒度偏粗。当前设计将"生成设备号计算脚本"、"输出下一实例 device_start"、"Primary Tag 替换"等多个子功能合并描述，缺乏可独立交付和验证的子任务拆分。例如：JSR223PreProcessor 脚本生成逻辑、设备范围计算逻辑、下一实例 device_start 输出逻辑，各自涉及不同文件修改，应拆分为独立任务。此外，关于 `device_start` 注入机制和输出位置的问题尚未解决，直接影响任务边界定义。
**Recommendations**: 将多端协同模块拆分为更细粒度的实现任务：① 设备范围计算工具类/方法；② JSR223PreProcessor Groovy 脚本生成器；③ 下一实例 device_start 输出接口（明确输出到控制台/日志/文件）；④ Primary Tag 替换逻辑与设备号绑定；⑤ 命令行参数注入规范与 JMX 属性读取统一。每个子任务应包含独立的验收标准和测试要求。

## Overall Assessment
本模块设计思路清晰，新增功能对现有系统零侵入，向后兼容性良好。**经范围决策（见第 0 节）**：多端协同发压由调用测试计划的流水线脚本实现，不在生成器职责内；原 Open Questions（`device_start` 输出位置、注入机制、冲突验证责任）均归属外部编排，视为已关闭。生成器侧仅需保证 JMX 模板可通过 JMeter 属性读取 `device_start`。剩余可改进项仅为边界值校验与测试覆盖（如 `device_per_thread > 0` 防御、模板属性读取的端到端断言），均为非阻塞，可在 tasks 阶段收敛。
