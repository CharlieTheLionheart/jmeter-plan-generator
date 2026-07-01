# Tasks: write-strategies

## 0. 范围与依赖确认

- [ ] 0.1 确认范围：策略模式抽象 + 5 种策略实现 + direct-insert-write 重构
- [ ] 0.2 确认依赖 `utils/preprocessor_helpers` 提供公共 PreProcessor 逻辑
- [ ] 0.3 确认依赖 `prepared-insert-template` 提供模板字典（single_prepared / batch_prepared 需要）
- [ ] 0.4 确认策略注册表 `STRATEGY_REGISTRY` 查找未知 mode 时抛 `ValueError`

## 1. WriteStrategy 抽象基类

- [ ] 1.1 创建 `src/write_strategies/__init__.py`
- [ ] 1.2 创建 `src/write_strategies/base.py` 定义 `WriteStrategy` 抽象基类
- [ ] 1.3 定义抽象方法：`mode_name`、`requires_prepared_insert_template()`、`generate_query()`、`get_sampler_type()`、`get_sampler_config()`、`requires_param_setup()`、`get_preprocessor_code()`、`get_sampler_script()`
- [ ] 1.4 基类提供 `get_config(key, default=None)` 辅助方法（处理 key 缺失）
- [ ] 1.5 添加 `@since` 版本标记

## 2. 策略注册表

- [ ] 2.1 创建 `src/write_strategies/registry.py`
- [ ] 2.2 定义 `STRATEGY_REGISTRY` 字典映射 mode → 策略类
- [ ] 2.3 实现 `get_strategy(mode)` 函数，mode 不存在时抛 `ValueError` 并说明支持的 mode 列表
- [ ] 2.4 注册 5 种策略：`single_insert`、`batch_insert`、`single_prepared`、`batch_prepared`、`schemaless`

## 3. SingleInsertStrategy 实现

- [ ] 3.1 创建 `src/write_strategies/single_insert_strategy.py`
- [ ] 3.2 `mode_name` 返回 `"single_insert"`
- [ ] 3.3 `requires_prepared_insert_template()` 返回 `False`
- [ ] 3.4 `get_sampler_type()` 返回 `"JDBCSampler"`
- [ ] 3.5 `get_sampler_config()` 返回 `{"usePrepared": False}`
- [ ] 3.6 `requires_param_setup()` 返回 `True`
- [ ] 3.7 `get_sampler_script()` 返回 `None`
- [ ] 3.8 实现 TDD：先写测试，再实现

## 4. BatchInsertStrategy 实现

- [ ] 4.1 创建 `src/write_strategies/batch_insert_strategy.py`
- [ ] 4.2 `mode_name` 返回 `"batch_insert"`
- [ ] 4.3 其他方法同 SingleInsertStrategy，`get_sampler_config()` 仍返回 `{"usePrepared": False}`
- [ ] 4.4 实现 TDD：先写测试，再实现

## 5. SinglePreparedStatementStrategy 实现

- [ ] 5.1 创建 `src/write_strategies/single_prepared_strategy.py`
- [ ] 5.2 `requires_prepared_insert_template()` 返回 `True`
- [ ] 5.3 `generate_query()` 从注入的模板字典返回预编译语句模板
- [ ] 5.4 `get_sampler_type()` 返回 `"JDBCSampler"`
- [ ] 5.5 `get_sampler_config()` 返回 `{"usePrepared": True}`
- [ ] 5.6 实现 TDD：先写测试，再实现

## 6. BatchPreparedStatementStrategy 实现

- [ ] 6.1 创建 `src/write_strategies/batch_prepared_strategy.py`
- [ ] 6.2 `requires_prepared_insert_template()` 返回 `True`
- [ ] 6.3 `get_sampler_type()` 返回 `"JSR223Sampler"`
- [ ] 6.4 `get_sampler_config()` 返回 `{"scriptLanguage": "groovy"}`
- [ ] 6.5 `get_sampler_script()` 返回 Groovy batch 执行代码（带 batch size 上限、连接超时、异常回滚）
- [ ] 6.6 补充 batch size 上限边界规格
- [ ] 6.7 实现 TDD：先写测试，再实现

## 7. SchemalessWriteStrategy 实现

- [ ] 7.1 创建 `src/write_strategies/schemaless_strategy.py`
- [ ] 7.2 `mode_name` 返回 `"schemaless"`
- [ ] 7.3 `generate_query()` 返回空字符串
- [ ] 7.4 `get_sampler_type()` 返回 `"JSR223Sampler"`
- [ ] 7.5 `get_sampler_script()` 抛 `NotImplementedError("Schemaless write strategy is not yet implemented (T2)")`
- [ ] 7.6 实现 TDD：测试异常路径

## 8. 重构 direct-insert-write

- [ ] 8.1 提取 `single_insert` SQL 生成逻辑到 `SingleInsertStrategy.generate_query()`
- [ ] 8.2 提取 `batch_insert` SQL 生成逻辑到 `BatchInsertStrategy.generate_query()`
- [ ] 8.3 提取 JDBCSampler 配置到 `get_sampler_config()`
- [ ] 8.4 提取 JSR223PreProcessor 代码生成到 `get_preprocessor_code()`
- [ ] 8.5 定义重构前后输出等价性验证标准
- [ ] 8.6 保留旧实现分支至少一个迭代周期，或通过配置切换

## 9. 单元测试（每策略）

- [ ] 9.1 测试 `get_strategy("unknown_mode")` 抛 `ValueError`
- [ ] 9.2 测试 `STRATEGY_REGISTRY` 包含全部 5 种策略
- [ ] 9.3 测试 SingleInsertStrategy 各方法返回值符合 spec
- [ ] 9.4 测试 BatchInsertStrategy 各方法返回值符合 spec
- [ ] 9.5 测试 SinglePreparedStatementStrategy 模板使用
- [ ] 9.6 测试 BatchPreparedStatementStrategy Groovy 脚本结构
- [ ] 9.7 测试 SchemalessWriteStrategy 抛 `NotImplementedError`
- [ ] 9.8 测试 `get_config(key)` key 缺失时返回默认值
- [ ] 9.9 运行全部单元测试并通过

## 10. 重构等价性验证

- [ ] 10.1 重构前后的 JMX XML 片段关键配置字典对比测试
- [ ] 10.2 回归测试套件验证新旧实现等价
- [ ] 10.3 CI 中增加"策略模式关闭"路径的冒烟测试

## 11. Review 修复验证

- [ ] 11.1 确认 `BatchPreparedStatementStrategy` 的 batch size 上限、连接超时、异常回滚等边界规格已补充
- [ ] 11.2 确认 `STRATEGY_REGISTRY` 未知 mode 防御行为已明确（抛 `ValueError`）
- [ ] 11.3 确认 `get_config(key, default)` 辅助方法已在基类提供
- [ ] 11.4 确认 `direct-insert-write` 重构兼容性清单已文档化
- [ ] 11.5 确认重构前后输出等价性有自动化验证

## 12. 代码审查

- [ ] 12.1 提交代码审查
- [ ] 12.2 确认 review.md findings 全部解决后方可合并
