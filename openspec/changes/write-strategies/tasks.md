# Tasks: write-strategies

## 0. 范围与依赖确认

- [x] 0.1 确认范围：策略模式抽象 + 5 种策略实现 + direct-insert-write 重构
- [x] 0.2 确认依赖 `utils/preprocessor_helpers` 提供公共 PreProcessor 逻辑
- [x] 0.3 确认依赖 `prepared-insert-template` 提供模板字典（single_prepared / batch_prepared 需要）
- [x] 0.4 确认策略注册表 `STRATEGY_REGISTRY` 查找未知 mode 时抛 `ValueError`

## 1. WriteStrategy 抽象基类

- [x] 1.1 创建 `src/write_strategies/__init__.py`
- [x] 1.2 创建 `src/write_strategies/base.py` 定义 `WriteStrategy` 抽象基类
- [x] 1.3 定义抽象方法：`mode_name`、`requires_prepared_insert_template()`、`generate_query()`、`get_sampler_type()`、`get_sampler_config()`、`requires_param_setup()`、`get_preprocessor_code()`、`get_sampler_script()`
- [x] 1.4 基类提供 `get_config(key, default=None)` 辅助方法（处理 key 缺失）
- [x] 1.5 添加 `@since` 版本标记（v0.1.0 在模块 docstring + base.py 中标注）

## 2. 策略注册表

- [x] 2.1 创建 `src/write_strategies/registry.py`
- [x] 2.2 定义 `STRATEGY_REGISTRY` 字典映射 mode → 策略类
- [x] 2.3 实现 `get_strategy(mode)` 函数，mode 不存在时抛 `ValueError` 并说明支持的 mode 列表
- [x] 2.4 注册 5 种策略：`single_insert`、`batch_insert`、`single_prepared`、`batch_prepared`、`schemaless`

## 3. SingleInsertStrategy 实现

- [x] 3.1 创建 `src/write_strategies/single_insert_strategy.py`
- [x] 3.2 `mode_name` 返回 `"single_insert"`
- [x] 3.3 `requires_prepared_insert_template()` 返回 `False`
- [x] 3.4 `get_sampler_type()` 返回 `"JDBCSampler"`
- [x] 3.5 `get_sampler_config()` 返回 `{"usePrepared": False}`
- [x] 3.6 `requires_param_setup()` 返回 `True`
- [x] 3.7 `get_sampler_script()` 返回 `None`
- [x] 3.8 实现 TDD：先写测试，再实现（`tests/write_strategies/test_single_insert_strategy.py`）

## 4. BatchInsertStrategy 实现

- [x] 4.1 创建 `src/write_strategies/batch_insert_strategy.py`
- [x] 4.2 `mode_name` 返回 `"batch_insert"`
- [x] 4.3 其他方法同 SingleInsertStrategy，`get_sampler_config()` 仍返回 `{"usePrepared": False}`
- [x] 4.4 实现 TDD：先写测试，再实现（`tests/write_strategies/test_batch_insert_strategy.py`）

## 5. SinglePreparedStatementStrategy 实现

- [x] 5.1 创建 `src/write_strategies/single_prepared_strategy.py`
- [x] 5.2 `requires_prepared_insert_template()` 返回 `True`
- [x] 5.3 `generate_query()` 从注入的模板字典返回预编译语句模板
- [x] 5.4 `get_sampler_type()` 返回 `"JDBCSampler"`
- [x] 5.5 `get_sampler_config()` 返回 `{"usePrepared": True}`
- [x] 5.6 实现 TDD：先写测试，再实现（`tests/write_strategies/test_single_prepared_strategy.py`）

## 6. BatchPreparedStatementStrategy 实现

- [x] 6.1 创建 `src/write_strategies/batch_prepared_strategy.py`
- [x] 6.2 `requires_prepared_insert_template()` 返回 `True`
- [x] 6.3 `get_sampler_type()` 返回 `"JSR223Sampler"`
- [x] 6.4 `get_sampler_config()` 返回 `{"scriptLanguage": "groovy"}`
- [x] 6.5 `get_sampler_script()` 返回 Groovy batch 执行代码（带 batch size 上限、连接超时、异常回滚）
- [x] 6.6 补充 batch size 上限边界规格（`DEFAULT_BATCH_SIZE_MAX=1000`、`DEFAULT_CONNECTION_TIMEOUT_MS=30_000`；构造时校验）
- [x] 6.7 实现 TDD：先写测试，再实现（`tests/write_strategies/test_batch_prepared_strategy.py`）

## 7. SchemalessWriteStrategy 实现

- [x] 7.1 创建 `src/write_strategies/schemaless_strategy.py`
- [x] 7.2 `mode_name` 返回 `"schemaless"`
- [x] 7.3 `generate_query()` 返回空字符串
- [x] 7.4 `get_sampler_type()` 返回 `"JSR223Sampler"`
- [x] 7.5 `get_sampler_script()` 抛 `NotImplementedError("Schemaless write strategy is not yet implemented (T2)")`
- [x] 7.6 实现 TDD：测试异常路径（`tests/write_strategies/test_schemaless_strategy.py::TestSchemalessSamplerScript`）
- [x] 7.7 `config_parser` 校验阶段拦截 `mode: schemaless`（R-PAR-017，`WriteConfig.reject_schemaless` validator，报 "not yet implemented"）；策略层 `NotImplementedError` 为二次兜底
- [x] 7.8 回归测试：`tests/config_parser/test_parser.py::test_schemaless_mode_rejected` 断言 `ConfigParserError` 匹配 "not yet implemented"

## 8. 重构 direct-insert-write

- [x] 8.1 提取 `single_insert` SQL 生成逻辑到 `SingleInsertStrategy.generate_query()`
- [x] 8.2 提取 `batch_insert` SQL 生成逻辑到 `BatchInsertStrategy.generate_query()`
- [x] 8.3 提取 JDBCSampler 配置到 `get_sampler_config()`（`{"usePrepared": False}`）
- [x] 8.4 提取 JSR223PreProcessor 代码生成到 `get_preprocessor_code()`（委托 `direct_insert_write.preprocessor_generator.generate_preprocessor_script`）
- [x] 8.5 定义重构前后输出等价性验证标准：`tests/write_strategies/test_equivalence.py` 比较策略与 legacy 模块输出 byte-by-byte
- [x] 8.6 保留旧实现分支至少一个迭代周期（`direct_insert_write` 模块公共 API 未变更；策略层是 additive；旧函数仍可直接调用且测试仍绿）

## 9. 单元测试（每策略）

- [x] 9.1 测试 `get_strategy("unknown_mode")` 抛 `ValueError`（`tests/write_strategies/test_registry.py::TestGetStrategy::test_unknown_mode_raises_value_error`）
- [x] 9.2 测试 `STRATEGY_REGISTRY` 包含全部 5 种策略（`tests/write_strategies/test_registry.py::TestRegistryContents::test_all_five_modes_registered`）
- [x] 9.3 测试 SingleInsertStrategy 各方法返回值符合 spec（`test_single_insert_strategy.py`）
- [x] 9.4 测试 BatchInsertStrategy 各方法返回值符合 spec（`test_batch_insert_strategy.py`）
- [x] 9.5 测试 SinglePreparedStatementStrategy 模板使用（`test_single_prepared_strategy.py`）
- [x] 9.6 测试 BatchPreparedStatementStrategy Groovy 脚本结构（`test_batch_prepared_strategy.py::TestBatchPreparedSamplerScript`）
- [x] 9.7 测试 SchemalessWriteStrategy 抛 `NotImplementedError`（`test_schemaless_strategy.py::TestSchemalessSamplerScript`）
- [x] 9.8 测试 `get_config(key)` key 缺失时返回默认值（`test_base.py::TestGetConfigHelper`）
- [x] 9.9 运行全部单元测试并通过（100/100 `tests/write_strategies/`；486/486 全量套件）

## 10. 重构等价性验证

- [x] 10.1 重构前后的 JMX XML 片段关键配置字典对比测试（`test_equivalence.py::TestSingleInsertEquivalence::test_sampler_metadata_matches_jdbc_sampler_contract` + 同 `TestBatchInsertEquivalence`）
- [x] 10.2 回归测试套件验证新旧实现等价（`test_equivalence.py` 全部 12 个用例断言 strategy 输出与 legacy 输出 byte-identical）
- [x] 10.3 CI 中增加"策略模式关闭"路径的冒烟测试（`test_equivalence.py::TestStrategySmoke` + `test_registry.py::TestGetStrategy::test_known_modes_produce_write_strategy`）
- [x] 10.4 registry-driven 路径下 JMX 形态与合并前字节相同（`tests/jmx_skeleton_generator/` 78 个用例 + `tests/write_strategies/test_equivalence.py` 12 个用例；合并重构走 `write_strategies.get_strategy()` 主路径，无运行时分叉）

## 11. Review 修复验证

- [x] 11.1 确认 `BatchPreparedStatementStrategy` 的 batch size 上限、连接超时、异常回滚等边界规格已补充（`DEFAULT_BATCH_SIZE_MAX`、`DEFAULT_CONNECTION_TIMEOUT_MS` + 构造时校验；Groovy 含 `executeBatch`、`rollback`）
- [x] 11.2 确认 `STRATEGY_REGISTRY` 未知 mode 防御行为已明确（抛 `UnknownWriteModeError`，继承 `WriteStrategyError` 与 `ValueError`；message 列出全部 supported modes）
- [x] 11.3 确认 `get_config(key, default)` 辅助方法已在基类提供（`base.py::WriteStrategy.get_config`）
- [x] 11.4 确认 `direct-insert-write` 重构兼容性清单已文档化（`src/write_strategies/base.py` docstring + `tasks.md` §8.6 备注）
- [x] 11.5 确认重构前后输出等价性有自动化验证（`test_equivalence.py`）
- [x] 11.6 write_groups.py 合并到注册表分发 + `usePrepared` xml 序列化槽位 + 迁移指南 `docs/migration-write-strategies.md`

## 12. 代码审查

- [x] 12.1 提交代码审查
- [ ] 12.2 确认 review.md findings §2/§3/§4 全部解决后方可合并

## 13. 接口签名回归设计（2026-07-10 核对决议）

- [x] 13.1 新增 `write_strategies/models.py`：`ResolvedTable`（fqn/columns/table_config）与 `WriteRuntime`（device_per_thread/ms_step/device_start/batch_seq_init）frozen dataclass
- [x] 13.2 `WriteStrategy` ABC 由 `**context` 改为显式参数：`generate_query(table, batch_lines, insert_template)`、`get_preprocessor_code(table, batch_lines, runtime)`、`get_sampler_script(table, batch_lines)`
- [x] 13.3 5 个策略同步改签名；`single_prepared` / `batch_prepared` 恢复无状态（模板经 `insert_template` 形参，`batch_prepared` 仅保留 batch_size_max/connection_timeout_ms 构造配置）
- [x] 13.4 `tests/write_strategies/` 全部调用点改用 `ResolvedTable` / `WriteRuntime`；删除仅测旧构造器状态的用例
- [x] 13.5 回填原始设计文档 §3.7（值对象 + 接口签名 + 各策略示例 + schemaless 块）；全量套件 481 passed