# Tasks: jdbc-datasource

## 0. 范围确认与依赖契约

- [ ] 0.1 确认范围：仅生成单一 JDBCDataSource，固定名称 `jdbcConfig`，驱动 `com.kaiwudb.Driver`
- [ ] 0.2 确认依赖契约：`${db_url}`、`${db_username}`、`${db_password}`、`${conn_pool_size}` 四个变量必须由 `UserDefinedVariablesGenerator` 在本模块之前定义
- [ ] 0.3 确认变量缺失处理策略：生成阶段检测到变量未定义时 fail-fast，抛 `JmxGenerationError`，不生成不完整的 JMX
- [ ] 0.4 确认连接池参数（`connectionAge`/`timeout`/`trimInterval` 等）维持硬编码，不做配置化

## 1. 模块骨架

- [ ] 1.1 创建 `src/jdbc_datasource/__init__.py` 导出 `JDBCDataSourceGenerator`
- [ ] 1.2 创建 `src/jdbc_datasource/jdbc_data_source_generator.py` 模块文件
- [ ] 1.3 添加模块 docstring 说明本模块职责和数据源名称约定（`jdbcConfig`）

## 2. JDBCDataSource 元素生成

- [ ] 2.1 实现 `JDBCDataSourceGenerator.__init__(conn_config)` 接受连接配置字典
- [ ] 2.2 实现 `generate()` 方法返回 `xml.etree.ElementTree.Element`
- [ ] 2.3 生成 `<JDBCDataSource>` 根元素，设置 `testclass="JDBCDataSource"`、`guiclass="TestBeanGUI"`
- [ ] 2.4 设置 `dataSource="jdbcConfig"`
- [ ] 2.5 设置 `autocommit="true"`
- [ ] 2.6 生成连接参数 `<stringProp>`：dbUrl=`${db_url}`、username=`${db_username}`、password=`${db_password}`
- [ ] 2.7 生成驱动 `<stringProp>`：`driver="com.kaiwudb.Driver"`
- [ ] 2.8 生成连接池参数：
  - `poolMax="${conn_pool_size}"`
  - `keepAlive="true"`
  - `connectionAge="5000"`
  - `timeout="10000"`
  - `trimInterval="60000"`
  - `transactionIsolation="DEFAULT"`
- [ ] 2.9 设置 `checkQuery` 为空字符串 `<stringProp name="checkQuery"></stringProp>`
- [ ] 2.10 生成空 `<hashTree/>` 子元素
- [ ] 2.11 生成结果 `xml.etree.ElementTree.Element` 结构符合 JMX 规范

## 3. 变量缺失 Fail-Fast 校验

- [ ] 3.1 在 `generate()` 中检测 `db_url` 变量引用是否有效（输入配置非空即认为有效）
- [ ] 3.2 在 `generate()` 中校验 `conn_pool_size` 非零、正整数（若 <= 0 抛 `JmxGenerationError` 并说明原因）
- [ ] 3.3 明确：用户名、密码为空字符串属于合法配置（允许空密码），不触发校验异常
- [ ] 3.4 文档化契约：变量实际值由 `UserDefinedVariablesGenerator` 保证，本模块仅校验配置存在性

## 4. 元素定位与组装

- [ ] 4.1 `JDBCDataSourceGenerator` 生成的是独立元素，不负责自身在 JMX 中的定位
- [ ] 4.2 由调用方（如 `JmxAssembler`）负责将元素插入正确位置（User Defined Variables 之后、所有 ThreadGroup 之前）
- [ ] 4.3 提供 `position_hint()` 方法返回 `"after_user_defined_variables"` 供组装参考

## 5. 单元测试

- [ ] 5.1 测试 `generate()` 输出的根元素 tag 为 `JDBCDataSource`
- [ ] 5.2 测试 `dataSource="jdbcConfig"` 属性存在
- [ ] 5.3 测试 `autocommit="true"` 属性存在
- [ ] 5.4 测试 `dbUrl="${db_url}"` 的 `<stringProp>` 存在
- [ ] 5.5 测试 `poolMax="${conn_pool_size}"` 的 `<stringProp>` 存在
- [ ] 5.6 测试 `driver="com.kaiwudb.Driver"` 的 `<stringProp>` 存在
- [ ] 5.7 测试所有硬编码连接池参数（connectionAge、timeout、trimInterval）存在
- [ ] 5.8 测试 `checkQuery` 为空字符串
- [ ] 5.9 测试输出元素可被 `xml.etree.ElementTree` 解析（round-trip）
- [ ] 5.10 测试 `conn_pool_size <= 0` 时抛 `JmxGenerationError`
- [ ] 5.11 测试空输入（非 None 但字段缺失）不抛异常，正常生成含变量引用的元素
- [ ] 5.12 运行全部单元测试并通过

## 6. 集成测试（与 jmx-skeleton-generator 协作）

- [ ] 6.1 将 `JDBCDataSourceGenerator` 接入 `jmx-skeleton-generator` 的组装流程
- [ ] 6.2 端到端测试：生成的 JMX 中 JDBCDataSource 出现在正确位置
- [ ] 6.3 端到端测试：生成的 JMX 为合法 XML，可被 JMeter 解析
- [ ] 6.4 确认下游采样器模块（`write-strategies`、`query-functionality`）使用 `dataSource="jdbcConfig"` 引用

## 7. Review 修复验证

- [ ] 7.1 确认"依赖变量缺失处理"作为生成阶段 fail-fast 已在 §3 中实现
- [ ] 7.2 确认"元素定位断言"作为集成测试已在 §6 中覆盖
- [ ] 7.3 确认 `jdbcConfig` 名称约定已文档化，可供下游模块引用
- [ ] 7.4 确认所有 Open Questions 已在 design.md 中决策（连接池硬编码、KaiwuDB 驱动、本期仅 db_url/conn_pool_size 动态参数）

## 8. 代码审查

- [ ] 8.1 提交代码审查
- [ ] 8.2 确认 review.md findings 全部解决后方可合并
