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
- [ ] 2.7 处理双引号字符串、`''` 转义（design 决策 1）；SQL 模板**不允许** `--` / `/* */` 注释——遇到即抛 `QueryGenerationError`
- [ ] 2.8 引入 `QueryGenerationError` 自定义异常（在 `src/query_functionality/errors.py` 或与 `query_groups.py` 同模块），异常消息含原 SQL 与占位符位置；不细分异常子类（design 决策 15）
- [ ] 2.9 抽取 `_scan_sql_tokens(sql) -> List[Token]` 单源状态机；`_extract_placeholders` 与 `_replace_placeholders_with_vars` 改为消费此函数（design 决策 16 / spec §"Parse SQL placeholders" 单源子场景）

## 3. 列绑定上下文提取

- [ ] 3.1 支持表限定列名（如 `t.col_int8_1`）
- [ ] 3.2 支持裸列名（如 `col_int8_1`）
- [ ] 3.3 无法绑定时**移除 param.csv 兜底降级**，改为抛 `QueryGenerationError`，消息含原 SQL 与占位符位置（design 决策 7）
- [ ] 3.4 正则支持的二元操作符列表移除 `IN`（decision 2 + design 决策 4 一致）
- [ ] 3.5 无法绑定的操作符（如 `BETWEEN ? AND ?` / `IS NULL`）也走 `QueryGenerationError` 硬失败路径

## 4. Groovy 参数绑定脚本生成

- [ ] 4.1 实现 `generate_param_binding_script(column_bindings, seed_base_path)` 返回 Groovy 脚本
- [ ] 4.2 脚本从对应种子文件随机采样，使用 `Math.random() * seedLines.size()`，每线程每次迭代重读文件（无缓存，design 决策 10）
- [ ] 4.3 设置 JMeter 变量 `param_0`、`param_1` 等
- [ ] 4.4 处理 CSV `"null"` 字符串：采样到时设置变量为空字符串 `""`
- [ ] 4.5 非 `"null"` 值直接设置变量
- [ ] 4.6 种子文件缺失或空时回退到 `"null"` 字面量；该字面量同样经 `"null".equalsIgnoreCase(raw) ? "" : raw` 归一（spec §"Handle seed file cache and concurrency"）；种子文件**缺失**与**空**走同一路径
- [ ] 4.7 命名 `generate_param_binding_script` 与 spec 一致（替换 `_build_query_param_script`）
- [ ] 4.8 `tableDir.listFiles().filter { name.endsWith("_${col}.csv") }` 命中数 ≠ 1 时：
  - 空集 → 走 §4.6 fallback
  - 多匹配 → 抛 `QueryGenerationError`，消息含冲突文件列表与列名（design 决策 17 / spec §"Resolve seed file by unique column"）

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
- [ ] 7.5 `generate_query_thread_groups` 调用 `throughput_control.generate_query_timer(qc.throughput)`，传字面 float；`qc.throughput` 直接嵌入 timer（design 决策 18 改写 / spec §"Query timer takes the per-query literal throughput value"）

## 8. 拒绝场景处理

- [ ] 8.1 `LIMIT ?` 拒绝：抛 `QueryGenerationError`，消息含原始 SQL + 占位符字符位置
- [ ] 8.2 `IN (?, ?, ?)` 拒绝：同上（消息明确 "placeholders in IN clauses are not supported"）
- [ ] 8.3 种子文件为空：PreProcessor 设置 `"null"` fallback 变量，不阻塞执行（spec §"Handle seed file cache and concurrency"）
- [ ] 8.4 列名指向不存在的种子文件：当前实现走 tasks §4.6 的 `"null"` fallback，不抛错（与 8.3 一致）
- [ ] 8.5 字符串字面量内 `?` 严禁抛错，必须静默忽略（spec §1 `Ignore placeholders in string literals` 场景）
- [ ] 8.6 SQL 模板内 `--` / `/* */` 注释**整体拒绝**：状态机遇到即抛 `QueryGenerationError("comment not allowed at sql[N]")`，N 为注释起始位置
- [ ] 8.7 EOF 时若状态机 `state != NORMAL`，抛 `QueryGenerationError`，消息含未闭合类型（`SQ_STRING` / `DQ_STRING`）与最后字符位置；注释状态在此检查之前已被 §8.6 拦截
- [ ] 8.8 `IN (?)` 单占位符允许（等价 `=`）；`IN (?, ?, ...)` ≥ 2 占位符拒绝（design 决策 13）

## 9. 单元测试

- [ ] 9.1 测试简单查询占位符提取（3 个 `?`）
- [ ] 9.2 测试字符串字面量内占位符被忽略（单引号）
- [ ] 9.3 测试双引号字符串内占位符被忽略
- [ ] 9.4 测试 `LIMIT ?` 拒绝抛 `QueryGenerationError`（消息含 SQL 片段）
- [ ] 9.5 测试 `IN (?, ?, ?)` 拒绝抛 `QueryGenerationError`（消息含 "IN clauses"）
- [ ] 9.6 测试表限定列名绑定
- [ ] 9.7 测试裸列名绑定
- [ ] 9.8 测试 NULL 字符串采样返回空字符串
- [ ] 9.9 测试 JDBCSampler 配置结构正确
- [ ] 9.10 测试线程组默认 num_threads=1
- [ ] 9.11 测试 `''` 转义空字符串（KaiwuDB `O''Brien` 不应破坏占位符提取）
- [ ] 9.12 测试 SQL 含 `--` 行注释抛 `QueryGenerationError("comment not allowed")`（tasks §8.6）
- [ ] 9.13 测试 SQL 含 `/* */` 块注释抛 `QueryGenerationError("comment not allowed")`（tasks §8.6）
- [ ] 9.14 测试单条种子行文件采样确定性（`(int)(Math.random() * 1) == 0`）
- [ ] 9.15 测试种子文件缺失或空时回退到 `"null"` 字面量
- [ ] 9.16 测试 `BETWEEN ? AND ?` 与 `IS NULL` 拒绝抛 `QueryGenerationError`（tasks §3.5）
- [ ] 9.17 测试拒绝场景的异常消息含原始 SQL 片段与占位符字符位置（tasks §2.8）
- [ ] 9.18 测试 EOF 时未闭合单引号字符串抛 `QueryGenerationError` 含 `SQ_STRING`（tasks §8.7）
- [ ] 9.19 测试 EOF 时未闭合双引号标识符抛 `QueryGenerationError` 含 `DQ_STRING`（tasks §8.7）
- [ ] 9.20 测试 `WHERE col IN (?)` 走普通列名绑定（不被拒，design 决策 13）
- [ ] 9.21 测试 `WHERE col IN (?, ?)` 拒绝抛 `QueryGenerationError`（design 决策 13）
- [ ] 9.22 测试错误类型单一：所有拒绝场景都是 `QueryGenerationError` 实例，无子类（design 决策 15）
- [ ] 9.23 测试 `_scan_sql_tokens` 与 `_extract_placeholders` / `_replace_placeholders_with_vars` 共享：占位符计数与替换计数 byte-equal（design 决策 16）
- [ ] 9.24 测试种子文件多匹配抛 `QueryGenerationError`（design 决策 17）
- [ ] 9.25 测试种子文件无匹配走 `"null"` fallback（design 决策 17 / spec §"No matching seed file"）
- [ ] 9.26 测试 `throughput_var` 参数透传：`generate_query_thread_groups(..., throughput_var="${q0_throughput}")` 生成定时器含该引用
- [ ] 9.27 测试 `throughput_var` 默认值 `${read_throughput}` 与既有行为兼容
- [ ] 9.28 运行全部单元测试并通过

## 10. 集成测试

- [ ] 10.1 端到端：生成含查询线程组的 JMX
- [ ] 10.2 验证 `Prepared Select Statement` 类型正确
- [ ] 10.3 验证 JMX 为合法 XML
- [ ] 10.4 混合场景（写入+查询）JMX 合法性

## 11. Review 修复验证

- [ ] 11.1 确认 spec 中已补充双引号转义、`''` 空字符串测试场景
- [ ] 11.2 确认 spec 中已统一 `IN` 子句拒绝与正则支持的语义冲突描述
- [ ] 11.3 确认种子文件为空时有明确处理策略
- [ ] 11.4 路径拆分子任务（`src/query_functionality/{sql_parser,query_generator}.py`）已记录但本次迭代**不实施**（方向 A 延后；本迭代采用 CLAUDE.md #3 主张"不动可工作代码"），仅在代码层做接口隔离注释引导

## 12. 代码审查

- [ ] 12.1 提交代码审查
- [ ] 12.2 确认 review.md findings 全部解决后方可合并

## 13. B+C 修订捕获（2026-07-13 explore 模式）

本次 explore 不动 `src/` 代码，只把 B+C 决策落到 proposal / design / spec / tasks：

- [x] 13.1 spec.md 新增 4 个字符串字面量场景（双引号、`''` 转义、`--` 行注释、`/* */` 块注释）
- [x] 13.2 spec.md 新增"Handle seed file cache and concurrency" Requirement（含 3 个场景）
- [x] 13.3 design.md 决策 1 扩展（注释忽略 + `''` 转义空字符串）
- [x] 13.4 design.md 决策 2 调整（IN 操作符移出支持列表）
- [x] 13.5 design.md 新增决策 7（硬失败语义 + 移除 param.csv 兜底）
- [x] 13.6 design.md 新增决策 8（SQL 注释中 `?` 忽略）
- [x] 13.7 design.md 新增决策 9（字符串字面量 `''` 转义）
- [x] 13.8 design.md 新增决策 10（种子文件每次重读、无缓存）
- [x] 13.9 tasks.md §2.8 新增 `QueryGenerationError` 自定义异常任务
- [x] 13.10 tasks.md §3 调整：移除 param.csv 兜底；3.4 / 3.5 增 IN / BETWEEN / IS NULL 拒绝
- [x] 13.11 tasks.md §4.6 / §4.7 增 fallback 字符串与函数命名统一
- [x] 13.12 tasks.md §8.4 / §8.5 补错误兜底与注释场景
- [x] 13.13 tasks.md §9 增 7 个新单测（9.11-9.17）

后续实施闸门：
- [x] 13.14 design.md 决策 11（EOF hard-fail）+ 决策 12（注释 warn）+ 决策 13（IN 区分）+ 决策 14（块注释不嵌套）
- [x] 13.15 spec.md "First `*/` closes" + "Accept single-element IN" + "Emit comment-placeholder warnings" 三节
- [x] 13.14 design.md 决策 11（EOF hard-fail）+ 决策 12（注释 warn）+ 决策 13（IN 区分）+ 决策 14（块注释不嵌套）
- [x] 13.15 spec.md "First `*/` closes" + "Accept single-element IN" + "Emit comment-placeholder warnings" 三节
- [x] 13.16 tasks.md §8.7 / §8.8 / §9.22-9.25 新增 7 checkbox（IN 单/多 + 注释 warn + 块注释嵌套）
- [x] 13.17 决策翻转：注释整体拒绝（design 决策 8 重写 + 决策 12 作废）+ 错误类型单一（新增决策 15）+ D6 嵌套字符串不支持（合并到决策 1）
- [x] 13.18 spec.md 删除"Emit comment-placeholder warnings"节，"Reject SQL comments in query templates"新增 4 场景（行注释 / 块注释 / 双引号内单引号 / 单引号内 `''` 转义）
- [x] 13.19 tasks.md §8.5-8.8 重写（注释拒绝 / EOF 不可达注释）、§9.12-9.25 重排为 9.12-9.22 共 11 checkbox（含 IN 单 / 多 / 类型单一）
- [x] 13.20 design.md 决策 16（`_scan_sql_tokens` 单源）+ 决策 17（种子文件命名约定 + 多匹配硬失败）+ 决策 18（`throughput_var` 接口契约）
- [x] 13.21 spec.md "Parse SQL placeholders" §"Single-source state machine" 2 子场景 + "Resolve seed file by unique column" §"Multiple matching seed files (naming conflict)" + §"Throughput variable reference is caller-controlled" 2 场景
- [x] 13.22 tasks.md §2.9（`_scan_sql_tokens`）+ §4.6（合并缺失/空）+ §4.8（多匹配抛错）+ §7.5（throughput_var 参数）+ §9.23-9.27 共 5 新测试
- [x] 13.23 取消决策 18 旧方案（`throughput_var` 参数 / `${read_throughput}` 默认）；改用 throughput-control 决策 18 方案（`qc.throughput` 字面数值直接喂 `throughput-control.generate_query_timer`）；spec §"Throughput variable reference is caller-controlled" 删除、改为 "Query timer takes the per-query literal throughput value"；代码 + 测试同步待实施（含 `src/jmx_skeleton_generator/generators/query_groups.py` 改动 + `seed-data-generator` 命名约定对齐 + 测试扩展 + review §1/§3 翻转）
