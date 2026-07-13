## Context

查询功能模块负责生成查询线程组和查询采样器。查询 SQL 中的 `?` 占位符需要在生成阶段解析并绑定到列种子文件，运行时从种子文件随机采样。

## Goals / Non-Goals

**Goals:**
- 解析 SQL 中的 `?` 占位符（排除字符串字面量）
- 通过上下文分析将占位符绑定到具体列
- 生成 JSR223PreProcessor Groovy 脚本
- 生成 JDBCSampler（使用 `Prepared Select Statement`）
- 生成独立的查询线程组
- 无法绑定时报错（如 `LIMIT ?`）

**Non-Goals:**
- 不支持复杂 SQL 解析（如子查询、CTE）
- 不支持非列参数（如 `LIMIT ?`）
- 不支持自定义参数绑定策略

## Decisions

### 使用状态机解析 SQL 占位符

**Decision:** 使用状态机遍历 SQL 字符，识别单/双引号字符串字面量边界与字符串内转义引号（`''` / `""`），跳过其内的 `?`。SQL 中**禁止**任何 `--` 行注释与 `/* */` 块注释——扫描到即抛 `QueryGenerationError`。字符串字面量**不支持**嵌套：同种引号出现第二次即关闭（或 `''` 转义跳过），不维护 `string_depth` 计数器。

**Rationale:**
- 简单高效，无需完整 SQL 解析器
- 支持单引号和双引号字符串
- 处理转义字符：`''` 视为空字符串内的转义单引号（KaiwuDB / ANSI SQL 约定），不当作"开 + 立关"
- **不支持嵌套字符串**：PG 不支持 `'` 字面量字面嵌套，状态机把每次 `'` 当关闭或转义足够覆盖全部合法 SQL
- **不支持 SQL 注释**：注释内 `?` 的"忽略"语义在静态分析中容易制造静默错误（用户忘补参数 → 运行时类型错）。查询模板应是干净的 SQL，注释由配置 YAML 的 `description` 字段承担

**Alternatives considered:**
- **正则表达式**: 难以正确处理字符串字面量
- **完整 SQL 解析器**: 过于复杂，引入额外依赖
- **支持注释 + 静态推导**（之前 design 决策 8 / 决策 12 的方案）: 运行时错误延迟暴露，2026-07-13 经决策翻转作废
- **嵌套字符串（`string_depth` 计数）**: 与 PG 行为不符，SVT 场景不触发

### 通过正则提取列名上下文

**Decision:** 使用正则表达式从 `?` 前的 SQL 片段中提取列名，仅支持**单占位符绑定到单列**的比较操作符；多占位符场景（`IN (?, ?, ?)`）由 `IN` 子句整体拒绝逻辑承担。

**Rationale:**
- 支持常见模式：`表名.列名` 或 `列名`
- 支持的二元比较操作符：`=`, `<>`, `!=`, `<=`, `>=`, `<`, `>`, `LIKE`
- **不支持** `IN` 操作符（即使单 `WHERE col IN (?)` 形式也拒绝，因为 `IN` 子句整体被禁止，见决策 4）
- 简单直接，无需复杂语法分析

**Alternatives considered:**
- **完整 SQL 语法树**: 过于复杂
- **硬编码模式匹配**: 难以扩展

### SQL 标识符和关键字统一使用小写

**Decision:** 处理的用户配置查询 SQL 语句中，所有 SQL 标识符（包括表名、列名）和 SQL 关键字（如 SELECT、FROM、WHERE、INSERT、VALUES 等）统一使用小写，与整个测试计划的其他模块保持一致。

**Rationale:**
- 与整个测试计划的其他模块统一 SQL 规范
- 虽然 KaiwuDB 对未加引号标识符的大小写不敏感，但统一使用小写可以提高测试计划的可读性和一致性
- 便于维护和调试
- 简化大小写转换逻辑，避免不同模块使用不同大小写规范

**Alternatives considered:**
- **支持任意大小写**: 增加不必要的复杂性
- **关键字大写标识符小写**: 与其他模块不一致

**示例:**
```sql
-- 正确：所有标识符和关键字统一小写
select col_int8_1 from iot_monitor.t_cnc where ptag_int8_1 = ?
select pk_int8_1, col_varchar_1 from iot_metadata.t_workshop where pk_int8_1 = ?

-- 错误：使用了大写（虽然 KaiwuDB 支持，但不规范）
SELECT COL_INT8_1 FROM iot_monitor.t_cnc WHERE ptag_int8_1 = ?
```

### 无法绑定时报错

**Decision:** 当 `?` 无法关联到具体列时（如 `LIMIT ?`），在生成阶段抛出异常，拒绝生成测试计划。

**Rationale:**
- 尽早发现问题，避免运行时错误
- 明确告知用户配置问题

**Alternatives considered:**
- **使用默认值**: 不符合测试场景
- **跳过该参数**: 影响查询语义

### NULL 值处理

**Decision:** 种子文件中的字符串 `"null"` 在 Groovy 脚本中映射为空字符串 `""`，避免 JDBC 驱动误当作数据库 NULL。

**Rationale:**
- JDBC 驱动会将字符串 `"null"` 当作字面值，而非 SQL NULL
- 空字符串在多数场景下等效于 SQL NULL
- 保持简单，避免复杂的类型判断

**Alternatives considered:**
- **使用 JDBC setNull()**: 需要在 JDBCSampler 中处理，增加复杂度
- **保留 "null" 字符串**: 不符合测试场景

### 查询线程组独立配置

**Decision:** 每个查询配置生成独立的查询线程组，各自挂载 ConstantThroughputTimer。

**Rationale:**
- 不同查询可能有不同的目标吞吐量
- 独立线程组便于监控和调试
- 符合规格书要求

**Alternatives considered:**
- **共用线程组**: 难以区分不同查询的吞吐量
- **查询串行执行**: 不符合性能测试场景

### 硬失败语义：无法绑定时移除兜底降级

**Decision:** 当占位符无法绑定到具体列（包括 `LIMIT ?` 与 `IN` 子句拒绝、列名上下文正则未匹配、列名指向未生成的种子列等情形）时，模块**硬失败**抛 `QueryGenerationError`，**不再**降级到 `seedDir + '/param.csv'` 这种隐式兜底路径。

**Rationale:**
- 兜底降级违反设计文档决策 4 的"无法绑定时报错"，让配置问题在运行时才暴露为"参数值总是 'null'" 或类似的难诊断行为
- 硬失败让用户立即看到 `QueryGenerationError: cannot bind placeholder at sql[:38] (LIMIT ?)` 这类可定位消息
- 设计行为与实现行为一致，便于后续 query-result-validator 之类的下游模块基于"参数已绑定"这一不变量做断言

**Alternatives considered:**
- **保留 param.csv 兜底**: 隐藏配置错误；改运行时再发现成本更高
- **发出 warning 但继续生成**: 用户体验模糊，运维侧更难追踪

### SQL 模板内注释整体拒绝

**Decision:** 状态机仅识别单/双引号字符串字面量；扫描到 `--` 行注释起始或 `/*` 块注释起始，**任何**非字符串字面量内的位置都立即抛 `QueryGenerationError("SQL template must not contain comments; remove -- / /* ... */ before submitting")`，错误消息含首字符位置。块注释首个 `*/` 即关闭（D14 仍生效）；状态机不维护 `LINE_COMMENT` / `BLOCK_COMMENT` 双态——遇到注释前缀直接错误退出。

**Rationale:**
- 一旦支持注释，"注释内 `?` 是否计入" / "跨多行块注释与字符串嵌套" 等边界细节组合爆炸
- SVT 查询模板由 yaml 配置生成，配置字段已有 `description` 承载注释；SQL 主体应保持干净
- 拒绝策略 fail-fast：用户在生成阶段立刻看到 `comment not allowed at sql[42]`，无需调试运行时类型错
- 状态机简化：仅维护 `SQ_STRING` / `DQ_STRING` / `NORMAL` 三态，去掉注释状态

**Alternatives considered:**
- **静默忽略注释内 `?`**: 设计决策 8 + 决策 12 的旧方案；运行时错误延迟暴露，2026-07-13 经决策翻转作废
- **配置项允许注释**: 增加 yaml 配置面，价值低
- **剥离注释保留 query skeleton**: 实现复杂，与"SQL 干净化"目标相反

### 字符串字面量识别：`''` 转义空字符串

**Decision:** 在状态机里把 `''` 视作 KAIWUDB/ANSI SQL 约定的"嵌入式转义单引号"，不关闭字符串；同理 `"` 表示双引号字符串内嵌转义双引号。

**Rationale:**
- KaiwuDB 文档规定字符串字面量内嵌引号用 `''` 或 `\"` 表示
- 当前实现 `elif string_char == ch: in_string = False` 会把 `''` 误判为"开字符串 → 立关"，导致 `'O''Brien'` 中的 `O` 之后到结尾都被错误视为 SQL，把后面的 `AND col = ?` 误解为字符串内容
- 双引号同样需识别：`"col?"` 内的 `?` 必须被忽略（虽然 SQL 标识符里很少有 `?`，但 spec 要求完整支持）

**Alternatives considered:**
- **强制用户配置时转义 SQL**: 给用户增加心智负担，易出错
- **预处理字符串把 `''` 替换成占位符**: 容易在替换时把 `?` 也替换，引入新 bug

### 种子文件读取策略：每线程每次迭代重读，无缓存

**Decision:** Groovy 脚本在每次采样时通过 `new File(seedDir + '/...').readLines()` 直接读盘，**不**缓存到内存。

**Rationale:**
- 多 JMeter 线程并发采样时，每个线程独立随机采样；如果缓存到内存会丧失"线程间不共享采样序列"的特性
- SVT 工作负载对单文件读取延迟不敏感（秒级 throughput），文件系统读竞争可接受
- 单条种子行的退化场景：`(int)(Math.random() * 1) == 0`，永远采样到同一行 → 确定性行为，方便断言

**Alternatives considered:**
- **JVM 内 props 缓存**: 跨线程共享相同采样序列，破坏独立随机性语义
- **单例线程安全的 lazy 缓存**: 实现复杂，性能收益小

### 未闭合字符串 EOF 硬失败（注释状态不再存在）

**Decision:** 状态机走完整个 SQL 后若 `state != NORMAL`，抛 `QueryGenerationError`，消息含未闭合类型（`SQ_STRING` / `DQ_STRING`）与最后字符位置。注释状态已在前一决策中不允许存在，故 EOF 不再可能出现 `LINE_COMMENT` / `BLOCK_COMMENT` 未闭合。

**Rationale:**
- 未闭合 SQL 字符串通常意味着配置 YAML 转义错误（少写了 `'`）；静默通过会让错误在运行时表现为占位符个数错配、列名绑定缺失
- 硬失败让用户在生成阶段立刻看到 `unterminated single-quoted string at sql[42]`，定位成本低
- 实现 cost 极低：循环结束后单次状态检查
- 与决策 4 的"无法绑定时报错"同精神：配置错误前置失败，不让运行时 / 测试阶段才发现

**Alternatives considered:**
- **静默通过**: 现状，运行时报错难定位
- **warn 但继续生成**: 用户体验模糊，运维侧难以追踪
- **自动补全闭合引号**: 破坏 SQL 语义，更不安全

### IN 子句：单占位符允许，多占位符拒绝

**Decision:** IN 子句按占位符个数分两档：
- 占位符 == 1：`WHERE col IN (?)` 等价 `WHERE col = ?`，走正常列名绑定路径
- 占位符 >= 2：`WHERE col IN (?, ?, ?)` 走 `QueryGenerationError` 拒绝路径

**Rationale:**
- 单元素 IN 是合法且常见的 SQL 写法，等价语义与 `=` 一致
- 多元素 IN 需要"同列多重采样"，当前状态机不支持（设计上 §"占位符有列名"是 1-1 映射）
- 决策与 spec §2.6 "拒绝 IN 子句"加细化条目：拒绝范围限定为 ≥ 2 占位符

**Alternatives considered:**
- **IN 完全拒绝**: 牺牲合法 case
- **IN 完全支持**: 需要状态机升级到"占位符可绑同列多重"，改动面大
- **可配置 IN 支持**: 引入 yaml 配置项，超出本模块职责

### 块注释嵌套：不支持

**Decision:** 第一个 `*/` 立即关闭块注释，不维护嵌套计数器。

**Rationale:**
- PG / KaiwuDB 均不支持 `/* outer /* inner */ outer */` 嵌套语义（标准 SQL 不允许）
- JMX Generator 不需要此能力
- 实现简化：保持 `state == BLOCK_COMMENT` 单布尔，无 `comment_depth` 字段

**Alternatives considered:**
- **支持嵌套（栈式 depth 计数）**: 与 PG 行为不符，且 SVT 用例不触发
- **配置项开关**: 增加配置面，价值低

### 错误类型：单一 QueryGenerationError，不细分

**Decision:** 所有占位符 / 字符串 / 注释 / IN / LIMIT / BETWEEN / EOF 相关拒绝场景统一抛 `QueryGenerationError`，错误消息以可读文本区分（`unterminated SQ_STRING` / `LIMIT ? not supported` / `placeholders in IN clauses not supported` 等）。不再细分 `QueryGenerationErrorKind` 枚举或子类异常。

**Rationale:**
- 当前调用方只需"生成阶段是不是错了"的布尔信号，无需按类型分支处理
- 细分异常类型会让调用方写 `except (LimitError, INError, ...)` 这样的多分支捕获，价值低于维护成本
- 错误消息文本已足够定位，调试时快速 grep 即可

**Alternatives considered:**
- **细分异常类型**: 价值不抵维护成本
- **错误码常量 + dict 映射**: 增加 boilerplate，无实质收益
- **仅布尔返回无异常**: 失去 "在哪里出错" 的位置信息

### SQL 状态机单源（`_scan_sql_tokens`）

**Decision:** 把当前在 `_extract_placeholders` 与 `_replace_placeholders_with_vars` 中复制的字符循环抽成单一函数 `_scan_sql_tokens(sql) -> List[Token]`。Token 类型至少覆盖 `{kind: 'PLACEHOLDER' | 'STRING' | 'COMMENT_LEADER' | 'OTHER', text: str, position: int}`。两个 caller 都消费此函数，规则变更（如新增 `''` 转义）只动一处。

**Rationale:**
- 当前实现两处状态机完全平行（line 36-54 vs 141-163）；一行复制错误会导致"提取 N 个 `?` 但只替换 N-1 个"的潜在不一致 bug
- 后续规则扩展（双引号 ID、`''` 转义、注释拒绝）只在一处实现，不会两边漂移
- 返回的 token list 也能用于未来的 syntax 高亮 / debug 输出

**Alternatives considered:**
- **维持双份**: 历史包袱 + 易漂移
- **生成器函数 yield**: 实现稍优雅但调试时栈追踪较深
- **第三方 lexer 库**: 引入依赖，与现有 4 态机规模不匹配

### 种子文件命名约定与冲突硬失败

**Decision:** 列绑定 script 通过 `tableDir.listFiles().filter { name.endsWith("_${col}.csv") }` 匹配种子文件。若匹配数 ≠ 1（空集 / 多文件）走两条不同路径：
- 空集：script 用 `"null"` literal 作 fallback（spec §"Empty seed file"）
- 多匹配：**硬失败**抛 `QueryGenerationError`，消息含冲突文件列表与列名（避免静默选错文件破坏测试数据）

**Rationale:**
- seed-data-generator 模块约定 `seeds/{db}/{table}/{index}_{col_name}.csv`，`{index}` 是 channel 索引；同一 `{db.table.col}` 通常只有 1 个 index 文件
- 但 seed-data-generator 可能将来按 multi-end 拆出多个 index 文件 → 同一 `{db.table.col}` 多文件
- 当前 `find()` 静默取第一个匹配 → 错误的 index 数据被采样 → 测试数据污染，难诊断
- 唯一性硬失败让配置错误前置暴露

**Alternatives considered:**
- **取首个匹配 (现状)**: 静默错误，难调试
- **聚合多个文件**: 实现复杂，语义模糊（按文件大小加权？随机选？）
- **接受 `{col}.csv` 全局唯一**: 与 seed-data-generator 既有约定冲突

### throughput-control 接口契约：qecutor 进度

`generate_query_thread_groups(query_config, seed_dir="${seed_dir}")` **不**接受 `throughput_var` 参数——直接传 `qc.throughput` 字面数值到 `throughput-control.generate_query_timer(qc.throughput)`。每个 query 的 throughput 独立嵌入 timer，无 JMeter 变量中转。

**Rationale:**
- 写入 vs 查询语义不同：写入 UDV `${write_throughput}` 是"全表打"的全局可覆盖策略；查询每个 query 有独立 throughput，per-query 字面数值比 UDV 索引更直白
- 移除 `throughput_var` 形参降低接口面（OpenSpec decision 16 精神：接口隔离，少一个动点）
- `throughput-control` 模块独立在 `src/throughput_control/`，jmx_skeleton_generator 只调用不实现

**Alternatives considered:**
- **保留 `throughput_var` 形参（query-functionality explore 旧方案）**: 与 throughput-control 新架构不兼容；本决策取代之
- **per-query UDV `${q0_throughput}` 注入**: 增加 UDV 维护面，与 "查询不暴露 UDV" 原则冲突

### 注释内 `?` = 静默忽略 + 警告

**Decision:** 状态机在注释状态（`LINE_COMMENT` / `BLOCK_COMMENT`）内遇到的 `?` 不计入占位符列表，但在返回的 metadata 里累加 `comment_placeholders` 计数；调用方据此发 `QueryGenerationWarning`（非 `Error`）。

**Rationale:**
- 用户经常写 `-- placeholder ?` 当文档示例；强制报错会让合法注释过不去
- 但完全静默会让"忘了补参数"变成哑错误（运行时 SQL 类型错），难追
- 警告处于中间路径：注释内 `?` 合法时不构成错误，但日志留下"曾经在这里有过 `?`"的痕迹

**Alternatives considered:**
- **硬失败**: 阻止 doc-style 注释
- **完全静默**: 失败延迟到运行时
- **环境变量开关**: 增加配置面，过度设计

### IN 子句：单占位符允许，多占位符拒绝

**Decision:** IN 子句按占位符个数分两档：
- 占位符 == 1：`WHERE col IN (?)` 等价 `WHERE col = ?`，走正常列名绑定路径
- 占位符 >= 2：`WHERE col IN (?, ?, ?)` 走 `QueryGenerationError` 拒绝路径

**Rationale:**
- 单元素 IN 是合法且常见的 SQL 写法，等价语义与 `=` 一致
- 多元素 IN 需要"同列多重采样"，当前状态机不支持（设计上 §"占位符有列名"是 1-1 映射）
- 决策与 spec §2.6 "拒绝 IN 子句"加细化条目：拒绝范围限定为 ≥ 2 占位符

**Alternatives considered:**
- **IN 完全拒绝**: 牺牲合法 case
- **IN 完全支持**: 需要状态机升级到"占位符可绑同列多重"，改动面大
- **可配置 IN 支持**: 引入 yaml 配置项，超出本模块职责

### 块注释嵌套：不支持

**Decision:** 第一个 `*/` 立即关闭块注释，不维护嵌套计数器。

**Rationale:**
- PG / KaiwuDB 均不支持 `/* outer /* inner */ outer */` 嵌套语义（标准 SQL 不允许）
- JMX Generator 不需要此能力
- 实现简化：保持 `state == BLOCK_COMMENT` 单布尔，无 `comment_depth` 字段

**Alternatives considered:**
- **支持嵌套（栈式 depth 计数）**: 与 PG 行为不符，且 SVT 用例不触发
- **配置项开关**: 增加配置面，价值低

## Risks / Trade-offs

### Risk: 正则表达式覆盖不全
**Mitigation:** 在文档中说明支持的模式，添加测试用例覆盖常见场景。未来可扩展为 SQL 语法树解析。

### Risk: 列名冲突
**Mitigation:** 通过表完全限定名（`db.table.col`）区分同名列。

### Trade-off: 不支持复杂 SQL
**Rationale:** 性能测试场景通常使用简单查询。如果需要复杂查询，可以手工修改生成的 JMX。

### Trade-off: 种子文件每次重读
**Rationale:** 引入 I/O 开销换取"每线程独立采样"语义；SVT 工作负载秒级 throughput 下开销可忽略。如未来发现 I/O 成为瓶颈，可改用 `JMeterProperty` 全局缓存（共享采样序列）作为后续 trade-off。

## Migration Plan

无需迁移。这是一个新功能模块。

review.md §1（Boundary Conditions）的解决方式：
- IN 操作符移出正则支持列表 → design 决策 2 + spec §2 拒绝 IN 场景
- 双引号 / `''` 转义 / `""` 转义 → design 决策 9 + spec §1 新场景
- 种子文件池最小阈值 → spec §"Handle seed file cache and concurrency" 明确"空文件 → 'null' fallback"

review.md §3（Test Coverage）的解决方式：
- 双引号转义 / SQL 注释场景已加入 spec §1
- 单条种子采样 / 并发线程采样已加入 spec §"Handle seed file cache and concurrency"
- 当前 `_build_query_param_script` 的兜底降级将被 spec/decision 7 取代，配套单测在 tasks §9。