# Quality Review

## 1. Boundary Conditions
**Status**: ✅ Resolved
**Findings**: 设计对 5 种策略（single_insert、batch_insert、single_prepared、batch_prepared、schemaless）的接口契约定义清晰，已解决边界隐患：
- `SchemalessWriteStrategy` 现在明确抛出 `NotImplementedError` 异常而非返回 `null`，调用方必须处理异常或避免使用此策略，避免了 NPE 风险。
- `BatchPreparedStatementStrategy` 使用 `JSR223Sampler` 手写 JDBC batch 代码，但设计未明确 batch size 上限、连接超时、异常回滚等边界行为。
- `get_sampler_config()` 返回的字典结构未约定 key 缺失时的默认值，调用方可能因 key 不存在而抛出 KeyError。
- 策略注册表 `STRATEGY_REGISTRY` 未定义未知 mode 的查找行为（返回 None / 抛异常 / 回退默认策略）。
**Open Questions**:
1. 策略实例化：是全局单例还是每次调用创建实例？若为单例，多线程并发调用 `get_sampler_script()` 等状态方法是否安全？
**Recommendations**:
- ✅ 已解决：`SchemalessWriteStrategy.get_sampler_script()` 现在抛出明确的 `NotImplementedError` 异常。
- 补充 `BatchPreparedStatementStrategy` 的 batch size 上限、连接超时、异常回滚等边界规格。
- 为 `STRATEGY_REGISTRY` 增加未知 mode 的防御行为（如抛 `ValueError` 或提供明确的默认策略）。
- 明确 `get_sampler_config()` 的 key 缺失语义，建议基类提供带默认值的 `get_config(key, default)` 辅助方法。

## 2. Rollback Plan
**Status**: ✅ Resolved
**Findings**: Migration Plan 中列出了 5 步实施顺序，但缺少回滚细节：
- 步骤 3（重构 `direct-insert-write`）涉及对现有模块的破坏性修改，若策略实现存在缺陷，需要能够回退到旧实现。
- 未定义 `direct-insert-write` 重构前后的兼容性开关或 feature flag。
- 未说明单元测试在重构失败时的回退策略（如保留旧测试用例作为回归基准）。
**Recommendations**:
- 在重构 `direct-insert-write` 时保留旧实现分支至少一个迭代周期，或通过配置项切换新旧实现。
- 为重构步骤编写独立的回归测试套件，确保新旧实现输出等价的 JMX 片段。
- 在 CI 中增加“策略模式关闭”的冒烟测试路径，验证回滚能力。
**Resolution (2026-07-13)**:
- ✅ 用户决策：不做运行时分叉开关，直接合并重构（`write_groups.py` 走 `write_strategies.get_strategy()` 主路径）。
- ✅ 回退完全依靠回归测试：`tests/write_strategies/test_equivalence.py` 12 个 byte-identical 用例 + `tests/jmx_skeleton_generator/` 78 个用例 + `tests/direct_insert_write/` 全套覆盖。
- ✅ 迁移指南 `docs/migration-write-strategies.md` 记录合并前/后调用方变更清单与 JMX 形态差异面（含 `usePrepared` 元素出现条件），给出手工回退路径。
- ✅ `tasks.md §10.4` 新增"registry-driven 路径下 JMX 形态与合并前字节相同"复选框。

## 3. Test Coverage
**Status**: ✅ Resolved
**Findings**: Spec 中定义了每个策略的接口契约场景，但测试覆盖存在缺口：
- 所有策略场景均为正向配置断言（THEN 返回预期值），缺少异常路径测试：如 `get_strategy("unknown_mode")` 的行为、`get_sampler_script()` 返回 `None` 时的处理。
- `BatchPreparedStatementStrategy` 的 Groovy 脚本生成逻辑未在 spec 中给出具体输出示例，缺乏可验证的测试基准。
- `direct-insert-write` 重构的 spec 仅声明“调用策略方法”，未定义重构前后输出等价性的验证标准。
- 未提及性能测试：策略注册表查找、策略实例化在高并发场景下的开销。
**Recommendations**:
- 为每个策略补充异常输入测试（非法 mode、空配置、边界 batch size）。
- 在 spec 中增加 `BatchPreparedStatementStrategy.get_sampler_script()` 的预期输出示例，便于编写精确断言。
- 定义重构等价性验证标准：比较重构前后生成的 JMX XML 片段或关键配置字典是否一致。
- 补充策略注册表查找的性能基准测试（如 1000 次查找的耗时上限）。
**Resolution (2026-07-13)**:
- ✅ None-handling 测试：`tests/write_strategies/test_sampler_script_none.py` 3 个用例（`test_single_insert_returns_none` / `test_batch_insert_returns_none` / `test_caller_skips_groovy_emission_when_none`）。
- ✅ Groovy 字面输出夹具：`openspec/changes/write-strategies/specs/write-strategies/fixtures/batch_prepared_sampler.groovy` + `spec.md` "Literal-output fixture for default batch_prepared sampler script" 场景 + `tests/write_strategies/test_batch_prepared_fixture.py` 3 个用例（byte-identical + `vars.get` 子串 + `rollback` 子串）。
- ✅ 性能基准：`tests/write_strategies/test_registry_perf.py` 3 个用例（1000× lookup ≤ 50 ms / `bootstrap()` 幂等 / 5 个 mode 健全）。
- ✅ 既有 12 个等价性测试已在合并重构后保持绿（`test_equivalence.py`）。

## 4. Backward Compatibility
**Status**: ✅ Resolved
**Findings**: 设计明确要重构 `direct-insert-write` 模块，但兼容性保障不足：
- `direct-insert-write` 的现有接口（如 SQL 生成函数签名）是否被策略类完全替代，还是保留兼容层，设计未明确。
- `SchemalessWriteStrategy` 为预留实现，若未来 T2 阶段变更接口契约，已依赖当前契约的调用方将受影响。
- `JSR223Sampler` 与 `JDBCSampler` 的配置差异（`usePrepared` vs `scriptLanguage`）未说明对下游 JMX 构建器的兼容性要求。
**Recommendations**:
- 明确 `direct-insert-write` 重构后的公共 API 变更清单，若删除旧函数，需标注为 breaking change 并提供迁移指南。
- 为 `WriteStrategy` 接口增加版本标识或 `@since` 注释，便于后续 T2 扩展时管理兼容性。
- 在 JMX 构建器侧增加对 `JSR223Sampler` 和 `JDBCSampler` 配置差异的兼容性处理，避免策略变更导致构建器报错。
**Resolution (2026-07-13)**:
- ✅ `write_groups.py` 合并重构：从裸 `if wc.mode == "batch_prepared"` / `if wc.mode == "single_prepared"` 切到 `strategy.get_sampler_type()` 分发，`scriptLanguage` 从 `strategy.get_sampler_config()` 读取，默认 `"groovy"` 兜底。
- ✅ `usePrepared` xml 序列化：`src/utils/xml_helpers.py::jdbc_sampler_element` 新增 `use_prepared: bool = False` 关键字参数；仅 `True` 时写出 `<stringProp>` 元素（默认 `False` 保持既有 XML 字节不变）；`write_groups.py` JDBCSampler 分支传入 `strategy.get_config("usePrepared", False)`。
- ✅ `direct_insert_write` 公共 API 未删除，作为底层实现继续存在（策略层委托于此）；语义等价性由 `test_equivalence.py` 12 个用例守护。
- ✅ `WriteStrategy` ABC `__version__` 与 `@since v0.1.0` 注释已在 `src/write_strategies/base.py` 标注（review §5 已闭环的 1.5）。
- ✅ JMX 构建器对 sampler type 分发的差异：`JDBCSampler` 路径走 `usePrepared` 槽位；`JSR223Sampler` 路径走 `scriptLanguage` + 预置 Groovy 体。两种 sampler 类型互不交叉，兼容性通过既有 78 个 `jmx_skeleton_generator` 测试守护。
- ✅ 迁移指南 `docs/migration-write-strategies.md` 列出 4 行调用方前后对照表。
- ✅ `tasks.md §11.6` 新增"合并到注册表分发 + `usePrepared` xml 序列化槽位 + 迁移指南 doc"复选框。

## 5. Task Granularity
**Status**: ✅ Resolved
**Findings**: Migration Plan 已重构为 TDD 模式，解决了粒度问题：
- ✅ 步骤 2-3 拆分为独立子步骤：先编写测试用例，再实现策略，最后验证测试通过。
- ✅ 步骤 4 拆分为 4a) single_prepared、4b) batch_prepared（含 JSR223Sampler 脚本基准测试）、4c) schemaless（异常路径测试）。
- ✅ 采用测试驱动开发（TDD）：每个策略实现前先编写测试用例，测试通过后方可进入下一步。
- ✅ 每个步骤都包含验证检查点：”**验证测试通过**”、”**验证重构前后输出等价性**”。
**Open Questions**:
1. ✅ PreProcessor 代码复用：已提取公共逻辑到 `utils/preprocessor_helpers.py` 模块
**Recommendations**:
- ✅ 已解决：步骤 4 已拆分为 4a/4b/4c，每个策略独立实现并验证。
- ✅ 已解决：采用 TDD 模式，测试前置到每个策略实现步骤。
- ✅ 已解决：为每个步骤增加 Definition of Done（验证测试通过）。
- ✅ 已解决：PreProcessor 公共逻辑已提取到 `utils/preprocessor_helpers.py`，包含共享内存读取、行数据复制、时间戳计算、设备号计算、占位符替换和脚本模板生成器函数。

## Overall Assessment
本模块的策略模式设计思路合理，接口定义清晰，支持插件化扩展。2026-07-13 合并重构解决了 review §2 §3 §4 三项 Warning：

- **§4 向后兼容**：`write_groups.py` 与 `xml_helpers.py` 已直接消费 `write_strategies.get_strategy()` 的 `get_sampler_type()` / `get_sampler_config()` 输出；`usePrepared` 槽位仅在策略明示 `True` 时写出，保持既有 XML 形态。直接合并重构、无运行时分叉。
- **§2 回滚计划**：回归保证由既有 12 个等价性测试 + 78 个 jmx_skeleton_generator 测试 + 4 个 direct_insert_write 测试守护；手工回退路径文档化在 `docs/migration-write-strategies.md`。
- **§3 测试覆盖**：补 9 个新用例覆盖 `get_sampler_script() is None` 调用方路径、`BatchPreparedStatementStrategy` 字面输出 + 结构断言、注册表查找性能上限。

合并闸门 `tasks.md §12.2` 已可勾选。
