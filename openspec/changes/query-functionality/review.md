# Quality Review

## 1. Boundary Conditions
**Status**: ⚠️ Warning
**Findings**: 状态机解析字符串字面量时仅处理了单引号、双引号和转义字符 `\'`，未明确处理 `"`（双引号转义）和连续引号（如 `''`）场景；正则提取列名上下文依赖常见操作符（`=`, `<>`, `!=`, `LIKE`, `IN`），但 `BETWEEN ? AND ?`、`IS ?` 等边界模式未覆盖；`IN` 子句整体被标记为不支持（`WHERE col IN (?, ?, ?)` 直接拒绝），但 `IN` 操作符本身却在正则支持列表中，存在语义冲突；种子文件为空或仅含 `"null"` 时，Groovy 脚本将始终采样到空字符串，未定义最小采样池大小阈值。
**Open Questions**:
1. 参数类型映射：是否需要更精确的 JDBC 类型映射（当前使用基本类型名）？
**Recommendations**: 在 spec 中补充 `"` 转义和 `''` 空字符串的测试场景；明确 `IN` 子句的拒绝逻辑与正则支持列表的互斥关系，统一文档描述；为空种子文件或采样池过小时增加前置校验，避免生成无意义的查询参数；针对参数类型映射问题，在 spec 中明确当前仅使用基本类型名（如 `VARCHAR`、`INTEGER`），若后续需要精确映射（如 `TIMESTAMP` 带时区、`DECIMAL` 精度），应单独提变更。

## 2. Rollback Plan
**Status**: ✅ Pass
**Findings**: 该模块为纯新增功能，无存量 JMX 或配置依赖；生成失败时（如占位符无法绑定）在生成阶段即抛出异常，不会产出半成品 JMX；各查询线程组独立生成，单个查询配置错误不影响其他查询线程组的生成。
**Recommendations**: 保持当前“生成阶段硬失败”策略，无需额外回滚机制；建议在异常信息中附带原始 SQL 片段和占位符位置，便于用户定位配置问题。

## 3. Test Coverage
**Status**: ⚠️ Warning
**Findings**: spec 已覆盖简单查询、字符串字面量过滤、表限定列名、裸列名、NULL 值处理、JDBCSampler 配置、JSR223PreProcessor 挂载、线程组并发数默认/指定值、LIMIT 拒绝、IN 子句拒绝等场景；但缺失以下边界测试：双引号转义字符串中的 `?`、SQL 注释中的 `?`、多字节字符与引号相邻、种子文件仅有一行时的随机采样行为、并发线程独立采样时的种子文件竞争（若种子文件被缓存到内存则无竞争，但设计未明确缓存策略）。
**Open Questions**:
1. IN 子句支持：是否未来支持 `WHERE col IN (?,?,?)` 绑定到同一列多次采样？
2. 查询结果处理：是否需要支持查询结果验证或断言？
**Recommendations**: 补充双引号转义、SQL 注释（`--`, `/* */`）中占位符的测试用例；明确种子文件读取策略（每线程每次重新读取 vs. 全局缓存），并针对该策略补充并发测试；增加单条种子数据的采样确定性验证；针对 IN 子句支持问题，当前设计明确拒绝，若未来支持需重新评估状态机与正则的职责边界；针对查询结果验证，当前仅生成查询执行器，若需断言应作为独立模块（如 query-result-validator）在后续迭代中引入，避免扩大本模块职责。

## 4. Backward Compatibility
**Status**: ✅ Pass
**Findings**: 本模块为全新能力（`query-functionality`），不修改现有 config-parser、seed-data-generator、jmx-skeleton-generator 的接口契约；新增查询线程组以独立形式附加到 JMX，不影响已有的写入线程组； proposal 中“Modified Capabilities”明确标注为“（无）”。
**Recommendations**: 确保 jmx-skeleton-generator 的骨架中查询线程组占位符的命名规则与写入线程组不冲突（如前缀 `query_`）；在集成测试中验证混合场景（写入 + 查询）下 JMX 的合法性。

## 5. Task Granularity
**Status**: ⚠️ Warning
**Findings**: 设计文档将“SQL 占位符解析”、“列名上下文提取”、“Groovy 脚本生成”、“JDBCSampler 生成”、“查询线程组生成”全部耦合在一个模块内，缺乏子任务拆分；状态机解析、正则提取、脚本生成、线程组装配四个子域的技能要求和验证方式差异较大，单模块承载易导致代码膨胀和 review 困难；`IN` 子句拒绝与正则支持列表的冲突（见 Boundary Conditions）也反映出多职责混合带来的设计不一致。
**Open Questions**:
1. 查询线程组 `num_threads` 示例：设计文档线程组编排图未标注查询线程数，是否需要在 JMX 示例中展示 `${q1_num_threads}` 等变量或常量值，并说明其从 `query_config.num_threads` 读取？
**Recommendations**: 将模块拆分为至少两个子任务或子模块：（1）SQL 占位符解析与列绑定（状态机 + 正则）；（2）查询执行 artifacts 生成（Groovy 脚本 + JDBCSampler + 线程组）；若短期内不拆分，应在代码层面通过接口隔离上述职责，并在后续迭代中逐步解耦；针对线程组 `num_threads` 示例问题，应在 jmx-skeleton-generator 的占位符文档或本模块的 spec 中补充具体示例（如 `${q1_num_threads}` 与 `query_config.num_threads` 的映射关系），避免实现歧义。

## Overall Assessment
本模块设计思路清晰，新增功能对现有系统零侵入，生成阶段硬失败的策略合理。主要风险集中在边界条件覆盖不全（双引号转义、SQL 注释、单条种子采样）和任务粒度过粗导致的职责耦合。建议优先补充边界测试用例，并考虑将 SQL 解析绑定与查询 artifacts 生成拆分为独立子模块，以降低后续维护成本。关于参数类型映射、IN 子句支持、查询结果处理、线程组 num_threads 示例等 4 个开放问题，已分别归入对应审查维度，需在后续迭代中逐一闭环。
