## Context

KaiwuDB SVT 测试计划生成器已经通过多个 openspec change 拆分解耦了 Parser、ColumnNamer、SeedGenerator、DDLGenerator、PreparedInsertTemplateGenerator、JmxBuilder 等核心模块，但缺少一个显式的 CLI 入口与端到端编排层。`main.py` 是规格书与设计文档中明确列出的模块，负责把上述模块按正确顺序串联起来，并将最终产物落地到文件系统。

当前 `openspec/changes/` 中没有任何 change 覆盖 `main.py`，导致：
- CLI 参数格式没有约束
- 模块调用顺序没有显式规格
- 错误处理与退出码没有统一约定
- `.jmx` 和 `seeds/` 输出路径没有显式定义

## Goals / Non-Goals

**Goals:**
- 实现 `main.py` 作为项目 CLI 入口
- 定义并约束模块调用顺序和数据流
- 统一错误分类与退出码
- 通过 `-v/-vv` 控制日志级别
- 将生成的 `.jmx` 和 `seeds/` 目录落地到指定输出目录
- 为 E2E 测试提供可执行的入口

**Non-Goals:**
- 不修改 Parser、JmxBuilder 等已有模块的内部实现
- 不引入新的写入策略或查询模式
- 不提供交互式配置向导
- 不提供配置热重载或守护进程模式
- 不处理 pip/uv 包安装后的 console script 注册（仅实现模块级入口函数）

## Decisions

### 使用 argparse 作为 CLI 框架

**Decision:** 使用 Python 标准库 `argparse` 实现 CLI 参数解析。

**Rationale:**
- `argparse` 是标准库，无需额外依赖
- 当前 CLI 只需要少量参数（两个位置参数 + `-o/-v`），`argparse` 足够表达
- 与项目“最小依赖”原则一致

**Alternatives considered:**
- **click / typer**: 功能更强大，但引入额外依赖；当前参数复杂度不需要这些框架
- **手动解析 sys.argv**: 容易出错，不利于后续扩展

### 模块实例化顺序采用设计文档 §2.3 流水线

**Decision:** `main.py` 按以下顺序实例化并调用模块：
1. `ModelParser.parse(model_yaml)` → `ModelConfig`
2. `TestParser.parse(cfg_yaml)` → `TestConfig`
3. `ColumnNamer(model_config)` → `ColumnNameList`
4. `SeedGenerator(model_config, column_names)` → 种子文件路径
5. `DDLGenerator(model_config, column_names)` → DDL 列表
6. 如果 `write_config` 中存在 `single_prepared` 或 `batch_prepared` 模式，则执行 `PreparedInsertTemplateGenerator(model_config, column_names)`
7. `JmxBuilder(model_config, test_config, column_names, seeds, ddl, prepared_templates)` → `.jmx` 文件

**Rationale:**
- 与设计文档 §2.3 序列图保持一致
- 种子生成与 DDL 生成相互独立，但为简化实现按顺序执行
- `PreparedInsertTemplateGenerator` 仅在需要时执行，避免不必要的计算

**Alternatives considered:**
- **完全并行种子与 DDL 生成**: 可缩短耗时，但会增加错误处理复杂度；当前单线程生成已满足需求
- **把所有对象在 JmxBuilder 内部实例化**: 会破坏模块间的显式依赖关系，不利于单元测试

### 错误分类与退出码

**Decision:** 按异常类型映射退出码：
- `ValidationError` → `1`
- `SeedGenerationError` → `2`
- `DdlGenerationError` → `3`
- `JmxGenerationError` → `4`
- 成功 → `0`
- 未知异常 → `5`

**Rationale:**
- 设计文档 §6.2 已给出解析阶段退出码 `1`，扩展其他阶段便于脚本化调用和 CI 判断
- 分类退出码便于用户在自动化流程中快速定位失败阶段

**Alternatives considered:**
- **所有错误统一退出码 `1`**: 实现简单但排查困难
- **每个错误码按具体规则细分**: 过于复杂，当前阶段不需要

### 输出目录结构

**Decision:** 输出目录下包含：
- `{test_plan_name}.jmx`（默认 `test_plan.jmx`，可通过 `test_cfg.yaml` 或 CLI 覆盖）
- `seeds/{database_name}/{table_name}/{index}_{col_name}.csv` 种子文件

**Rationale:**
- 与设计文档 §2.2 和 §3.4 保持一致
- 按表分子目录便于管理和调试
- `.jmx` 与 `seeds/` 放在同一目录下，方便直接复制到 JMeter 执行环境

**Alternatives considered:**
- **种子文件与 JMX 放在同级目录**: 表多时文件散乱
- **按时间戳创建子目录**: 增加用户查找成本

### 日志级别通过 `-v/-vv` 控制

**Decision:** 默认日志级别为 `WARNING`；`-v` 设置为 `INFO`；`-vv` 设置为 `DEBUG`。

**Rationale:**
- 与设计文档 §6.2 一致
- 默认只输出警告和错误，保持终端干净
- `-vv` 输出 DEBUG 便于排查模块间数据传递问题

**Alternatives considered:**
- **使用 `--log-level` 字符串参数**: 更灵活但不符合设计文档约定

### 异常在 `main()` 中集中捕获

**Decision:** `main()` 函数负责捕获所有业务异常和未知异常，记录日志并返回退出码；各模块只负责抛出对应异常类型。

**Rationale:**
- 单一职责：`main.py` 负责编排与退出，模块负责生成逻辑
- 便于统一日志格式和错误报告
- 便于单元测试时分别测试异常路径

**Alternatives considered:**
- **各模块自行调用 sys.exit**: 破坏模块可测试性
- **不捕获异常，直接抛出堆栈**: 不利于终端用户体验

### 与现有 `JMXSkeletonGenerator` 的协作边界

**Decision:** `main.py` 不重复 `JMXSkeletonGenerator`（[src/jmx_skeleton_generator/generators/skeleton.py](../../../../src/jmx_skeleton_generator/generators/skeleton.py)）的 JMX 元素组装逻辑。后者已实现：
- `TestPlan` + `UserDefinedVariables` + `JDBCDataSource` + `DDLSetupThreadGroup` + `SharedMemorySetupThreadGroup` + `WriteThreadGroups` + `QueryThreadGroups` 顺序拼装
- `assemble()` 调 `JMXAssembler` + `JMXWriter.write(output_dir)` 输出

`main.py` 仅做：
1. CLI 参数解析（argparse）
2. YAML 配置加载（`config_parser.parse_test_model_yaml` / `parse_test_cfg_yaml`）
3. 列名生成（`ColumnNamer`）
4. 种子文件生成（`seed_data_generator.generate_seeds`）
5. DDL 语句生成（`ddl_generator.generate`）
6. Prepared Insert 模板生成（条件：仅当 write_config 含 prepared mode）
7. 调 `JMXSkeletonGenerator(test_config, ddl_statements, prepared_templates, seed_csv_paths, output_dir).generate()` 获取 .jmx 路径
8. 退出码映射 + 异常集中捕获

**Rationale:**
- 与 `kwjdbc_svt-main-entry` 任务粒度修复（review §5 Recommendation）一致：main.py 仅做 CLI/编排/错误处理三大职责；JMX 元素装配下放到 `JMXSkeletonGenerator` 已有接口
- 避免双轨 JMX assembler 实现漂移
- 模块调用顺序由 `JMXSkeletonGenerator.generate()` 隐式约束；main.py 只需传正确输入

**Alternatives considered:**
- **main.py 重新拼接所有 generator 模块**: 与 JMXSkeletonGenerator 重复，违反 review §5 子模块边界
- **JMXSkeletonGenerator 改名为 JmxBuilder 并迁入 main.py**: 越权（多层依赖）

### 收敛 review §1 Open Questions

**Decision:**
- **Q1 文件名**：固定 `test_plan.jmx`（不开 CLI 配置；用户若需改名可事后 `mv`），简化 spec
- **Q2 mode 校验**：依赖 `config_parser` 的 Pydantic 校验（`R-PAR-016`/`R-PAR-017`），main.py 不重复校验
- **Q3 种子目录层级**：`seeds/{db_name}/{table_name}/`（与既有 `seed_data_generator.__init__.py:10` 命名约定一致），不加额外层级

**Rationale:**
- 文件名 / mode 校验 / 目录层级三个 Open Questions 都有现成下游约定（CLI 后 mv / config_parser R-PAR-* / seed_data_generator 既有命名）
- 不在 main.py 引入新概念，降低 review 与测试面

**Alternatives considered:**
- **三个 Q 各自新增 CLI flag / 校验路径**: 增加 review 面与测试负担

### 收敛 review §3 JMX 合法性验证方式

**Decision:** JMX 合法性通过 `xml.etree.ElementTree.parse()` 做 XML 格式校验（spec §"Output JMX file lands in output directory" 场景已覆盖）；不引入 JMeter 进程作为验证依赖（CI 跑不起 JMeter）。

**Rationale:**
- CI 环境无 JMeter runtime；XML 格式校验是 lightweight 验证
- 设计文档 §6.2 已给出"valid XML readable by JMeter 5.5+" 表述；XML well-formed 是最小有效检查

**Alternatives considered:**
- **用 JMeter headless 验证**: 跨平台依赖过重，超出本模块 scope

### 错误处理：异常集中捕获 vs 模块自管

**Decision (沿用既有决策):** `main()` 集中捕获所有业务异常与未知异常；各模块只负责抛出对应异常类型（见既有 §"异常在 `main()` 中集中捕获"）。

**新增增强:** `main(argv=None)` 签名允许 programmatic 注入（测试用），默认行为仍捕获异常并返回 exit code。

**Rationale:**
- Programmatic 友好：单元测试用 `main(["test_model.yaml", "test_cfg.yaml"])` 直接传 argv，不污染 `sys.argv`
- 与既有 §"Programmatic invocation returns exit code" 场景一致

**Alternatives considered:**
- **`main()` 强制捕获**: 阻止 pytest.raises 路径
- **`main()` 强制抛出**: 破坏 programmatic invocation（review §1 第 5 点）

## Risks / Trade-offs

### Risk: 模块接口变动导致 main.py 频繁修改
**Mitigation:** main.py 仅依赖各模块公开入口类的构造/调用约定；各模块变更时应同步更新 main.py 的调用代码，并通过 E2E 测试捕获不兼容。

### Risk: 输出目录已存在同名文件被覆盖
**Mitigation:** 默认直接覆盖，符合命令行工具惯例；后续可通过 `--force` / `--no-clobber` 选项扩展，不在本 change 中实现。

### Risk: PreparedInsertTemplateGenerator 条件判断逻辑与 write_config 模式耦合
**Mitigation:** 在 `main.py` 中集中检查 `test_config.write_config` 各表的 `mode` 字段，只要存在 `single_prepared` 或 `batch_prepared` 即执行；未来若新增模式，只需扩展判断条件。

### Trade-off: 种子生成与 DDL 生成串行执行
**Rationale:** 当前实现更简单，错误定位清晰；若后续性能成为瓶颈，可再引入并行。

## Migration Plan

无需迁移。`main.py` 是新增模块，不影响已有 openspec change 的实现。
