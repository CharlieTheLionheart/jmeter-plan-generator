# Quality Review

## 1. Boundary Conditions
**Status**: ⚠️ Warning
**Findings**:
- 设计文档和规格书对 CLI 参数缺失（如缺少位置参数）有明确处理（exit code 1），但未覆盖输入文件存在但内容为空、YAML 解析成功但根节点为 null 等边界场景。
- 输出目录 `-o` 指向无写权限路径时的行为未定义；规格书仅提到 "create the directory if it does not exist"，未提及权限不足或磁盘已满的降级策略。
- 种子生成阶段 "保留已生成的部分种子文件" 的规格（exit code 2 场景）未定义部分保留的具体范围：是仅保留当前表，还是保留所有之前已生成的表？
- 对 `test_cfg.yaml` 中 `write_config` 各表 `mode` 字段的非法值（非 `single_prepared` / `batch_prepared` / 其他合法模式）没有显式校验边界，可能静默跳过或导致下游 `JmxBuilder` 内部报错。
- `main()` 的 programmatic invocation 要求 "not call `sys.exit()` directly"，但未明确边界：如果用户从交互式环境调用 `main()` 且发生 `ValidationError`，异常对象本身是否被吞掉？当前决策说 "异常在 `main()` 中集中捕获"，这意味着调用方拿不到原始异常，只能拿到 exit code。

**Open Questions**:
1. 是否需要在 `test_cfg.yaml` 中显式指定输出 `.jmx` 文件名，还是统一使用 `test_plan.jmx`？（文件名边界未收敛）
2. 是否在 main.py 中校验 `write_config` 各表 `mode` 与已注册策略的一致性，还是交给 JmxBuilder 处理？（校验边界归属不清）
3. 种子文件目录层级：当不同数据库存在同名表时，是否需要增加数据库层级，改为 `seeds/{db_name}/{table_name}/...`？（目录边界未定义）

**Recommendations**:
- 在规格书中补充 "输入文件存在但为空/根节点为 null" 的边界场景定义，明确 exit code 1 是否覆盖此情况。
- 补充 `-o` 指向不可写路径时的错误行为：建议统一抛出 `OSError` 并映射为 exit code 5（未知异常），或新增 exit code 6 表示 I/O 错误。
- 明确部分种子保留的粒度：建议定义为 "保留所有已完整生成的表对应的种子目录"，避免用户误以为单表内部分列会被保留。
- 在 `main.py` 中增加 `write_config` 各表 `mode` 字段的显式白名单校验，避免非法 mode 值穿透到 `JmxBuilder`。
- 如果 programmatic invocation 是重要使用场景，建议增加 `main(argv=None)` 签名，并允许通过传入参数控制是否捕获异常（例如 `raise_errors=False` 默认行为）。

## 2. Rollback Plan
**Status**: ✅ Pass
**Findings**:
- 设计文档明确标注 "无需迁移"，`main.py` 是全新模块，不影响已有 openspec change 的实现。
- 输出物（`.jmx` 和 `seeds/`）默认直接覆盖，符合命令行工具惯例，回滚成本极低：只需删除输出目录或重新生成即可。
- 错误处理机制中，种子生成失败保留已生成文件、其他阶段失败不污染文件系统，天然支持部分回滚。
- 由于不修改任何已有模块内部实现，即使 `main.py` 存在缺陷，也可以通过回退到旧的手动调用方式（直接调用各模块 API）恢复工作流。

**Recommendations**:
- 无额外建议。当前设计对新增模块的零侵入特性已足够安全。

## 3. Test Coverage
**Status**: ⚠️ Warning
**Findings**:
- 规格书定义了 E2E invocation 要求（programmatic + CLI），但缺少对单元测试覆盖率的显式约束。
- 错误场景（exit code 1-5）在规格书中以 Scenario 形式列出，但未说明这些场景是通过单元测试还是 E2E 测试覆盖。
- `main.py` 作为编排层，核心逻辑是模块调用顺序和异常捕获；若各模块已有独立测试，则 `main.py` 的测试重点应放在 "调用顺序是否正确" 和 "异常是否被正确映射"，但规格书未明确这一点。
- 缺少对 `-vv` 与 `DEBUG` 日志级别映射的断言规格，以及 overwrite 时 `WARNING` 日志的断言规格。
- 规格书要求 `.jmx` 文件为 "valid XML readable by JMeter 5.5+"，但未定义如何验证（是通过 XML schema 校验，还是通过 JMeter 实际加载？）。

**Open Questions**:
1. 是否需要 `--dry-run` 模式，仅做配置校验不生成文件？（测试辅助能力缺失）

**Recommendations**:
- 在测试计划中明确区分：单元测试覆盖 `main()` 内部的异常映射和日志级别切换；E2E 测试覆盖完整流水线端到端输出。
- 为每个 exit code 场景编写独立的单元测试，使用 `pytest.raises(SystemExit)` 或返回值断言验证。
- 补充 `-vv` 场景和 overwrite WARNING 日志的测试用例。
- 明确 JMX 合法性验证方式：建议至少通过 `xml.etree.ElementTree.parse()` 做 XML 格式校验，并在 E2E 测试中增加此断言。

## 4. Backward Compatibility
**Status**: ✅ Pass
**Findings**:
- 本 change 为纯新增模块，不修改 Parser、JmxBuilder 等已有模块的接口或行为。
- CLI 参数设计（`argparse`）为标准库实现，不引入额外依赖，不会与现有环境冲突。
- 输出目录结构和文件命名沿用设计文档 §2.2 / §3.4 的既有约定，不产生新的兼容性风险。
- `main.py` 的 `main()` 函数签名若后续需要扩展（如增加 `--dry-run`），可通过增加可选参数保持向后兼容。

**Recommendations**:
- 无额外建议。当前设计在兼容性维度上风险极低。

## 5. Task Granularity
**Status**: ❌ Fail
**Findings**:
- 本 change 的 scope 横跨 CLI 参数解析、模块编排流水线、错误分类与退出码、输出物落地、日志控制、E2E 入口支持六大职责，全部压缩在单个 `main.py` 模块中实现。虽然 `main.py` 作为入口文件在物理上是一个文件，但 openspec 层面没有进一步拆分验证点，导致 review 和验收粒度粗糙。
- 规格书中 "Orchestrate module pipeline" 一个 Requirement 下包含了 5 个 Scenario，覆盖了从配置解析到 JMX 生成的完整流程；这些 Scenario 实际上对应多个独立的验证阶段（解析 → 列名 → 种子 → DDL → 条件模板 → JMX），却未按阶段拆分为独立的 Requirement，不利于逐条验收和缺陷定位。
- 错误处理（exit code 1-5）在规格书中被统一归入 "Handle errors with defined exit codes" 一个 Requirement，但每个 exit code 对应完全不同的失败阶段和测试构造方式；合并为一个 Requirement 会导致测试任务臃肿。
- 设计文档中 "异常在 `main()` 中集中捕获" 的决策虽然合理，但将 "异常捕获策略"、"日志格式统一"、"退出码映射" 三个子任务绑定在一起，任何一处修改都需要重新 review 整个决策。
- 缺少对 `main.py` 内部子函数（如 `setup_logging()`、`build_pipeline()`）的显式规格约束，这些子函数的提取和测试责任未在设计中体现。

**Recommendations**:
- 将 "Orchestrate module pipeline" 拆分为至少两个独立 Requirement："Parse and validate configurations" 和 "Generate artifacts in pipeline order"，使验收粒度与模块边界对齐。
- 将错误处理按 exit code 拆分为独立 Requirement（或至少按阶段拆分为 "Validation error handling"、"Generation error handling"、"Unexpected error handling"），使每个错误场景可以独立测试和验收。
- 在 design.md 中增加子任务分解：明确 `setup_logging()`、`parse_args()`、`build_pipeline()`、`write_outputs()` 等内部函数的提取责任和测试归属。
- 如果 openspec 支持，建议将 `main.py` 的 CLI 参数解析、流水线编排、错误处理三个职责分别创建为独立的子 change 或至少独立的 task 条目，使每个 task 的验收标准单一且可度量。
- 当前设计文档中的 "Decisions" 部分应按子任务编号（如 Decision 1.1、1.2），并与规格书中的 Requirement 编号建立显式追溯关系，避免设计与规格之间出现 "一对多" 的模糊映射。

## Overall Assessment
本 change 作为端到端编排入口，在架构定位上清晰，边界条件和回滚计划设计合理，向后兼容风险极低。然而，任务粒度是本模块的最大短板：设计文档和规格书将过多职责压缩在少数几个大颗粒度条目下，导致验收标准模糊、测试构造成本高、缺陷定位困难。建议优先按 "解析 → 生成 → 错误处理" 三大阶段重新拆分 Requirement 和 task 条目，并补充内部子函数的显式规格。三个 Open Questions（文件名边界、mode 校验边界、种子目录层级）均集中在边界条件和任务粒度维度，应在细化 task 时一并收敛。测试覆盖维度需补充单元测试与 E2E 测试的分工定义，以及 JMX 合法性验证的具体手段。综合建议：在编码实施前，先完成 task 粒度的拆分和 Open Questions 的决策收敛。
