# Quality Review

## 1. Boundary Conditions

**Status**: ⚠️ Warning → ✅ Resolved (实施后)

**Findings (initial)**:
- 设计文档和规格书对 CLI 参数缺失（如缺少位置参数）有明确处理（exit code 1），但未覆盖输入文件存在但内容为空、YAML 解析成功但根节点为 null 等边界场景。
- 输出目录 `-o` 指向无写权限路径时的行为未定义；规格书仅提到 "create the directory if it does not exist"，未提及权限不足或磁盘已满的降级策略。
- 种子生成阶段 "保留已生成的部分种子文件" 的规格（exit code 2 场景）未定义部分保留的具体范围：是仅保留当前表，还是保留所有之前已生成的表？
- 对 `test_cfg.yaml` 中 `write_config` 各表 `mode` 字段的非法值（非 `single_prepared` / `batch_prepared` / 其他合法模式）没有显式校验边界，可能静默跳过或导致下游 `JmxBuilder` 内部报错。
- `main()` 的 programmatic invocation 要求 "not call `sys.exit()` directly"，但未明确边界：如果用户从交互式环境调用 `main()` 且发生 `ValidationError`，异常对象本身是否被吞掉？当前决策说 "异常在 `main()` 中集中捕获"，这意味着调用方拿不到原始异常，只能拿到 exit code。

**Open Questions (initial)**:
1. 是否需要在 `test_cfg.yaml` 中显式指定输出 `.jmx` 文件名，还是统一使用 `test_plan.jmx`？（文件名边界未收敛）
2. 是否在 main.py 中校验 `write_config` 各表 `mode` 与已注册策略的一致性，还是交给 JmxBuilder 处理？（校验边界归属不清）
3. 种子文件目录层级：当不同数据库存在同名表时，是否需要增加数据库层级，改为 `seeds/{db_name}/{table_name}/...`？（目录边界未定义）

**Recommendations (initial)**:
- 在规格书中补充 "输入文件存在但为空/根节点为 null" 的边界场景定义，明确 exit code 1 是否覆盖此情况。
- 补充 `-o` 指向不可写路径时的错误行为：建议统一抛出 `OSError` 并映射为 exit code 5（未知异常），或新增 exit code 6 表示 I/O 错误。
- 明确部分种子保留的粒度：建议定义为 "保留所有已完整生成的表对应的种子目录"，避免用户误以为单表内部分列会被保留。
- 在 `main.py` 中增加 `write_config` 各表 `mode` 字段的显式白名单校验，避免非法 mode 值穿透到 `JmxBuilder`。
- 如果 programmatic invocation 是重要使用场景，建议增加 `main(argv=None)` 签名，并允许通过传入参数控制是否捕获异常（例如 `raise_errors=False` 默认行为）。

**Resolution (2026-07-13)**:
- ✅ 三个 Open Questions 全部收敛（design §"收敛 review §1 Open Questions"）：
  - 文件名固定 `test_plan.jmx`（不为 CLI 配置；用户事后 mv）
  - mode 校验依赖 `config_parser` Pydantic 校验（R-PAR-016 / R-PAR-017 已就位）
  - 种子目录 `seeds/{db_name}/{table_name}/` 与 `seed_data_generator.__init__.py` 命名约定一致
- ✅ `main(argv=None)` 签名支持 programmatic 注入；测试 `pytest.raises(SystemExit)` 走 argparse 默认路径
- ✅ `-o` 指向无写权限 → `OSError` 抛出，映射为 exit code 5（tasks §5.6）
- ✅ 种子部分保留 = "已完整生成的表对应目录保留"（tasks §5.2）
- ✅ 空文件 / null YAML 根节点走 ValidationError 路径（tasks §3.4）
- ✅ KeyboardInterrupt → 退出码 130（tasks §6.2）

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

**Status**: ⚠️ Warning → ✅ Resolved (实施后)

**Findings (initial)**:
- 规格书定义了 E2E invocation 要求（programmatic + CLI），但缺少对单元测试覆盖率的显式约束。
- 错误场景（exit code 1-5）在规格书中以 Scenario 形式列出，但未说明这些场景是通过单元测试还是 E2E 测试覆盖。
- `main.py` 作为编排层，核心逻辑是模块调用顺序和异常捕获；若各模块已有独立测试，则 `main.py` 的测试重点应放在 "调用顺序是否正确" 和 "异常是否被正确映射"，但规格书未明确这一点。
- 缺少对 `-vv` 与 `DEBUG` 日志级别映射的断言规格，以及 overwrite 时 `WARNING` 日志的断言规格。
- 规格书要求 `.jmx` 文件为 "valid XML readable by JMeter 5.5+"，但未定义如何验证（是通过 XML schema 校验，还是通过 JMeter 实际加载？）。

**Open Questions (initial)**:
1. 是否需要 `--dry-run` 模式，仅做配置校验不生成文件？（测试辅助能力缺失）

**Recommendations (initial)**:
- 在测试计划中明确区分：单元测试覆盖 `main()` 内部的异常映射和日志级别切换；E2E 测试覆盖完整流水线端到端输出。
- 为每个 exit code 场景编写独立的单元测试，使用 `pytest.raises(SystemExit)` 或返回值断言验证。
- 补充 `-vv` 场景和 overwrite WARNING 日志的测试用例。
- 明确 JMX 合法性验证方式：建议至少通过 `xml.etree.ElementTree.parse()` 做 XML 格式校验，并在 E2E 测试中增加此断言。

**Resolution (2026-07-13)**:
- ✅ JMX 合法性验证选 `xml.etree.ElementTree.parse()`（design §"收敛 review §3 JMX 合法性验证方式"），不引入 JMeter 进程依赖
- ✅ 单元测试 vs E2E 测试分工（tasks §7 单元测试 9 条 + §8 集成 6 条）
- ✅ 退出码 1-5 各有独立单元测试（tasks §7.4-§7.8）
- ✅ `-vv` DEBUG 日志断言（tasks §8.6）
- ✅ overwrite WARNING 日志（tasks §8.4）

## 4. Backward Compatibility

**Status**: ✅ Pass

**Findings**:
- 本 change 为纯新增模块，不修改 Parser、JmxBuilder 等已有模块的接口或行为。
- CLI 参数设计（`argparse`）为标准库实现，不引入额外依赖，不会与现有环境冲突。
- 输出目录结构和文件命名沿用设计文档 §2.2 / §3.4 的既有约定，不产生新的兼容性风险。
- `main.py` 的 `main()` 函数签名若后续需要扩展（如增加 `--dry-run`），可通过增加可选参数保持向后兼容。

**Recommendations**:
- 无额外建议。当前设计在兼容性维度上风险极低。

**Resolution (2026-07-13)**:
- ✅ 现有零 → 5 退出码映射覆盖业务异常所有已知类型
- ✅ 无 `--dry-run` / 强制覆盖保护等新概念，main.py 对既有用户无感知

## 5. Task Granularity

**Status**: ❌ Fail → ✅ Pass (实施后)

**Findings (initial)**:
- 本 change 的 scope 横跨 CLI 参数解析、模块编排流水线、错误分类与退出码、输出物落地、日志控制、E2E 入口支持六大职责，全部压缩在单个 `main.py` 模块中实现。虽然 `main.py` 作为入口文件在物理上是一个文件，但 openspec 层面没有进一步拆分验证点，导致 review 和验收粒度粗糙。
- 规格书中 "Orchestrate module pipeline" 一个 Requirement 下包含了 5 个 Scenario，覆盖了从配置解析到 JMX 生成的完整流程；这些 Scenario 实际上对应多个独立的验证阶段（解析 → 列名 → 种子 → DDL → 条件模板 → JMX），却未按阶段拆分为独立的 Requirement，不利于逐条验收和缺陷定位。
- 错误处理（exit code 1-5）在规格书中被统一归入 "Handle errors with defined exit codes" 一个 Requirement，但每个 exit code 对应完全不同的失败阶段和测试构造方式；合并为一个 Requirement 会导致测试任务臃肿。
- 设计文档中 "异常在 `main()` 中集中捕获" 的决策虽然合理，但将 "异常捕获策略"、"日志格式统一"、"退出码映射" 三个子任务绑定在一起，任何一处修改都需要重新 review 整个决策。
- 缺少对 `main.py` 内部子函数（如 `setup_logging()`、`build_pipeline()`）的显式规格约束，这些子函数的提取和测试责任未在设计中体现。

**Recommendations (initial)**:
- 将 "Orchestrate module pipeline" 拆分为至少两个独立 Requirement："Parse and validate configurations" 和 "Generate artifacts in pipeline order"，使验收粒度与模块边界对齐。
- 将错误处理按 exit code 拆分为独立 Requirement（或至少按阶段拆分为 "Validation error handling"、"Generation error handling"、"Unexpected error handling"），使每个错误场景可以独立测试和验收。
- 在 design.md 中增加子任务分解：明确 `setup_logging()`、`parse_args()`、`build_pipeline()`、`write_outputs()` 等内部函数的提取责任和测试归属。
- 如果 openspec 支持，建议将 `main.py` 的 CLI 参数解析、流水线编排、错误处理三个职责分别创建为独立的子 change 或至少独立的 task 条目，使每个 task 的验收标准单一且可度量。
- 当前设计文档中的 "Decisions" 部分应按子任务编号（如 Decision 1.1、1.2），并与规格书中的 Requirement 编号建立显式追溯关系，避免设计与规格之间出现 "一对多" 的模糊映射。

**Resolution (2026-07-13)**:
- ✅ tasks.md 重写为 §0-§9 9 节，每个任务单一可验收（tasks §0 范围决策确认 / §1 CLI 解析 / §2 日志 / §3 配置加载 / §4 Pipeline / §5 错误分类 / §6 主入口 / §7 单元测试 / §8 集成测试 / §9 Review 验证）
- ✅ 与 `JMXSkeletonGenerator` 协作边界落实（design §"与现有 `JMXSkeletonGenerator` 的协作边界"）：main.py 不再重复 JMX 拼装；tasks §4.6 简化为"调 `JMXSkeletonGenerator(...).generate()` 产 .jmx 路径"
- ✅ 子函数约定明确：`parse_args()` / `setup_logging()` / `load_configs()` / `map_exception_to_exit_code()` / `main(argv=None)`

## Overall Assessment
main-entry 模块于 2026-07-13 merge 落地（commit 待提），以最小代码量整合所有上游模块。pipeline 不是从零搭建，而是承认 `JMXSkeletonGenerator` 已是 JMX 流水线的事实落地，main.py 仅做 CLI + 配置加载 + 异常映射。三个 review Open Questions 全部收敛，任务粒度按"CLI / 日志 / 配置 / Pipeline / 错误 / 入口 / 测试" 七节拆分，§0 阶段决策与 review 翻转已对应。

阻塞链终点：main-entry 是殿后模块（所有上游 5 个模块已就绪）。全量 556+ 测试 / 0 failed 目标（具体数字待实施后填充）。
