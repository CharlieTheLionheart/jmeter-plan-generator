# Tasks: query-functionality

## 0. 范围与依赖确认

- [ ] 0.1 确认范围：SQL 占位符解析 → Groovy 参数绑定脚本 → JDBCSampler → 查询线程组
- [ ] 0.2 确认依赖 `seed-data-generator` 输出的种子文件格式
- [ ] 0.3 确认依赖 `utils/xml_helpers` 生成 JSR223PreProcessor XML
- [ ] 0.4 确认 `IN` 子句和 `LIMIT ?` 属于拒绝场景（spec 明确）
- [ ] 0.5 确认线程组 `num_threads` 从 `query_config.num_threads` 读取，默认 1

## 1. 模块骨架

- [ ] 1.1 创建 `src/query_functionality/__init__.py` 导出 `QueryGenerator`
- [ ] 1.2 创建 `src/query_functionality/sql_parser.py`（SQL 占位符解析）
- [ ] 1.3 创建 `src/query_functionality/query_generator.py`（主生成器）
- [ ] 1.4 添加模块 docstring 说明职责边界

## 2. SQL 占位符解析（sql_parser.py）

- [ ] 2.1 实现 `extract_placeholders(sql)` 返回占位符位置列表
- [ ] 2.2 实现 `is_in_string_literal(sql, position)` 判断 `?` 是否在字符串字面量内（支持单引号、双引号）
- [ ] 2.3 实现 `extract_column_context(sql, placeholder_position)` 提取占位符前的列名上下文
- [ ] 2.4 支持操作符：`=`、`<>`、`!=`、`LIKE`、裸列名
- [ ] 2.5 拒绝 `LIMIT ?`（占位符无法绑定列）
- [ ] 2.6 拒绝 `IN (?, ?, ?)`（多占位符绑定同一列，状态机不支持）
- [ ] 2.7 边界：处理双引号字符串、`''` 转义、`--` 和 `/* */` 注释中的占位符（应忽略）

## 3. 列绑定上下文提取

- [ ] 3.1 支持表限定列名（如 `t.col_int8_1`）
- [ ] 3.2 支持裸列名（如 `col_int8_1`）
- [ ] 3.3 无法绑定时抛 `QueryGenerationError`，说明具体 SQL 和位置

## 4. Groovy 参数绑定脚本生成

- [ ] 4.1 实现 `generate_param_binding_script(column_bindings, seed_base_path)` 返回 Groovy 脚本
- [ ] 4.2 脚本从对应种子文件随机采样，使用 `Math.random() * seedLines.size()`
- [ ] 4.3 设置 JMeter 变量 `param_0`、`param_1` 等
- [ ] 4.4 处理 CSV `"null"` 字符串：采样到时设置变量为空字符串 `""`
- [ ] 4.5 非 `"null"` 值直接设置变量

## 5. JDBCSampler 生成

- [ ] 5.1 实现 `generate_jdbc_sampler(sql, param_count)` 返回 XML Element
- [ ] 5.2 `queryType` 设为 `Prepared Select Statement`
- [ ] 5.3 `query` 保留原始 `?` 占位符
- [ ] 5.4 `queryArguments` 引用 `${param_0},${param_1},...`
- [ ] 5.5 `queryArgumentsTypes` 使用基本 JDBC 类型名（如 `VARCHAR,INTEGER`）

## 6. JSR223PreProcessor 附加

- [ ] 6.1 在 JDBCSampler 前附加 JSR223PreProcessor（Groovy）
- [ ] 6.2 PreProcessor 执行参数绑定脚本
- [ ] 6.3 使用 `utils/xml_helpers` 生成 XML

## 7. 查询线程组生成

- [ ] 7.1 实现 `generate_query_thread_group(query_config)` 返回 ThreadGroup XML Element
- [ ] 7.2 `num_threads` 从 `query_config.num_threads` 读取，默认 1
- [ ] 7.3 线程组下挂载 JDBCSampler 和 JSR223PreProcessor
- [ ] 7.4 多查询配置生成多个独立线程组

## 8. 拒绝场景处理

- [ ] 8.1 `LIMIT ?` 拒绝：抛 `QueryGenerationError`，消息含原始 SQL
- [ ] 8.2 `IN (?, ?, ?)` 拒绝：同上
- [ ] 8.3 种子文件为空：PreProcessor 设置空字符串变量，不阻塞执行

## 9. 单元测试

- [ ] 9.1 测试简单查询占位符提取（3 个 `?`）
- [ ] 9.2 测试字符串字面量内占位符被忽略
- [ ] 9.3 测试双引号字符串内占位符被忽略
- [ ] 9.4 测试 `LIMIT ?` 拒绝抛异常
- [ ] 9.5 测试 `IN` 子句拒绝抛异常
- [ ] 9.6 测试表限定列名绑定
- [ ] 9.7 测试裸列名绑定
- [ ] 9.8 测试 `NULL` 字符串采样返回空字符串
- [ ] 9.9 测试 JDBCSampler 配置结构正确
- [ ] 9.10 测试线程组默认 num_threads=1
- [ ] 9.11 运行全部单元测试并通过

## 10. 集成测试

- [ ] 10.1 端到端：生成含查询线程组的 JMX
- [ ] 10.2 验证 `Prepared Select Statement` 类型正确
- [ ] 10.3 验证 JMX 为合法 XML
- [ ] 10.4 混合场景（写入+查询）JMX 合法性

## 11. Review 修复验证

- [ ] 11.1 确认 spec 中已补充双引号转义、`''` 空字符串测试场景
- [ ] 11.2 确认 spec 中已统一 `IN` 子句拒绝与正则支持的语义冲突描述
- [ ] 11.3 确认种子文件为空时有明确处理策略
- [ ] 11.4 确认已拆分 SQL 解析与查询 artifacts 生成为独立子域（代码层面接口隔离）

## 12. 代码审查

- [ ] 12.1 提交代码审查
- [ ] 12.2 确认 review.md findings 全部解决后方可合并
