# KWDB SVT 测试计划生成器设计文档 Review 记录

Review 日期：2026-06-11
Review 对象：[docs/designs/kwdb-svt-test-plan-generator-design.md](docs/designs/kwdb-svt-test-plan-generator-design.md)  
参照规格：[docs/specs/kwdb-svt-test-plan-generator-spec.md](docs/specs/kwdb-svt-test-plan-generator-spec.md)  
历史 Review：[docs/specs/spec_review-2026-06-02.md](docs/specs/spec_review-2026-06-02.md)

---

## 严重矛盾（与规格书直接冲突，必须修正）

### 1. 查询模式强制使用 `prepared_statement`，完全忽略 `statement` 模式（已解决）

- **规格书 §2.0**：`query_config.mode` 支持 `statement`（将参数拼接到 SQL 语句中直接查询）和 `prepared_statement`（使用 PreparedStatement 查询）两种模式。
- **设计文档 §3.6**："所有查询统一使用 `Prepared Select Statement`，不走直接 SQL"；§5.3 关键设计要点也重申此约定。
- **问题**：设计文档将 `statement` 模式从架构层面彻底排除，与规格书直接矛盾。`statement` 模式不需要 `queryArgumentsTypes`，参数直接拼接到 SQL 字符串中，其 JMX 结构和 Groovy 预处理脚本与 `prepared_statement` 完全不同。
- **修正建议**：
  - `QueryConfigItem` 保留 `mode` 字段（设计文档 §3.1 已保留）。
  - `QuerySamplerGenerator` 需根据 `mode` 分支生成不同的 JMX 结构和预处理脚本：
    - `statement` 模式：Groovy 脚本直接将参数值替换到 SQL 字符串中，JDBCSampler 使用纯 SQL（无 `?`）。
    - `prepared_statement` 模式：保持当前设计（SQL 保留 `?`，`queryArguments` 引用变量）。
- **修复措施**：经 2026-06-15 回溯修改，规格书直接删除 `query_config` 的 `mode` 属性，`query_config` 不再支持 `statement`（将参数拼接到 SQL 语句中直接查询）模式，查询统一固定为 `prepared_statement` 执行；同时在 §2.0 查询配置说明中增加备注，明确 `?` 占位符绑定规则及无法绑定到具体列时的报错行为。设计文档无需再支持 `statement` 模式，双方实现口径保持一致。

---

### 2. 查询参数无法绑定时采用轮询 fallback，规格书要求报错（已解决）

- **规格书 §2.0 / spec_review 第 7 点**：如果 `?` 出现在无法关联到具体列的位置（如 `LIMIT ?`），生成器在生成阶段**报错**，拒绝生成测试计划。
- **设计文档 §5.3（修订后）**：`bind_query_params()` 删除轮询 fallback 逻辑；当 `extract_column_context()` 返回 `None` 或列名无法关联到查询涉及表的已知列时，直接抛出 `ValidationError`，拒绝生成测试计划。
- **问题**：轮询 fallback 会掩盖配置错误，导致查询参数绑定到不相关的列上，运行时产生无意义甚至错误的查询结果。这与规格书"报错"的要求直接冲突。
- **修正建议**：删除 fallback 逻辑，`extract_column_context()` 返回 `None` 且无法通过别名映射解析时，直接抛出 `ValidationError`，拒绝生成。
- **修复措施**：设计文档 §5.3 已删除 `ParamBinding.fallback` 字段、`bind_query_params()` 的轮询 fallback 分支以及 `generate_query_param_script()` 的 `[fallback]` 标记；关键设计要点表中将"轮询 fallback"改为"无法绑定报错"，明确生成阶段校验失败即抛出 `ValidationError`。

---

### 3. 时序表 DDL 中 `TAGS` 子句缺少列类型定义（已解决）

- **规格书附录 8.2**：KaiwuDB 时序表 `TAGS` 子句语法为 `TAGS (sensor_id INT NOT NULL, ...)`，需要包含列名和类型定义。
- **设计文档 §3.5**：时序表建表语句模板为 `TAGS ({ptag_names})`，仅列出列名，**完全缺少类型定义**。
- **问题**：按此模板生成的 DDL 在 KaiwuDB 中执行会直接报错。Primary Tag 列的类型信息在 `primary_tags` 配置中已完整定义，设计文档遗漏了将其映射到 `TAGS` 子句。
- **修正建议**：模板修正为 `TAGS ({ptag_column_defs})`，其中 `ptag_column_defs` 的格式与列定义一致（如 `ptag_varchar_1 VARCHAR(64) NOT NULL`）。
- **修复措施**：设计文档 §3.5 已修正时序表建表语句模板，`TAGS` 子句由 `{ptag_names}` 改为 `{ptag_column_defs}`，Primary Tag 列按 `列名 类型 [NOT NULL]` 格式输出，与规格书附录 8.2 语法保持一致。

---

### 4. `type_proportion` 分配算法 §3.3 与 §5.1 前后矛盾（已解决）

- **设计文档 §3.3**："按 `ceil(count × proportion)` 分配，最后一项用总数减去已分配数量兜底"。
- **设计文档 §5.1**：实际算法为 `floor` + 按余数贪心分配。
- **问题**：两种算法结果可能完全不同。例如 `count=4, proportions=[0.33, 0.33, 0.33, 0.01]`：
  - ceil 法 → `[1, 1, 2, 0]`
  - floor+贪心 → `[2, 1, 1, 0]`
- **修正建议**：统一采用 §5.1 的 `floor+贪心` 算法（更公平），删除 §3.3 中关于 `ceil` 的描述。
- **修复措施**：设计文档 §3.3 已删除 `ceil` 描述，改为明确引用 §5.1 的 `floor + 贪心` 算法；列名生成器与 `type_proportion` 分配算法章节实现口径一致。

---

### 5. `ConstantThroughputTimer` XML 示例遗漏关键 `calcMode` 属性（已解决）

- **规格书 §2.2**：`calcMode` 固定为 `0`（This thread only），且必须在 XML 中显式配置。`throughput = ${write_throughput} / ${num_threads}`。
- **设计文档 §3.6**：`ConstantThroughputTimer` 的 XML 示例中缺少 `<intProp name="calcMode">0</intProp>`。
- **问题**：JMeter 默认 `calcMode` 可能不是 0，遗漏该属性会导致吞吐量计算口径错误，实际压力与配置不符。
- **修正建议**：XML 示例补充 `<intProp name="calcMode">0</intProp>`；明确 `throughput` 属性值为 `${__BeanShell(${write_throughput} / ${num_threads},)}`（注意变量名用 `write_throughput` 而非 `throughput`，避免与查询吞吐量混淆）。
- **修复措施**：设计文档 §3.6 已补充 `<intProp name="calcMode">0</intProp>`；`throughput` 属性已修正为 `${__BeanShell(${write_throughput} / ${num_threads},)}`，变量名与参考文档 [docs/refs/jmx-components-references.md](docs/refs/jmx-components-references.md) 保持一致。

---

### 6. 查询采样器 `queryArguments` 设计与"SQL 替换"说法自相矛盾（已解决）

- **设计文档 §3.6**：查询采样器模板中 `queryArguments` 填入了 `${param_0},${param_1},...`。
- **设计文档 §5.3 关键设计要点**："原始 SQL 中的 `?` 被替换为 `${param_N}` 形式的 JMeter 变量引用；JDBCSampler 的 `queryArguments` 留空"。
- **问题**：这两处直接矛盾。JMeter `Prepared Select Statement` 的正确行为是：
  1. `query` 字段**保留** `?` 占位符（不由生成器替换为 `${param_N}`）。
  2. `queryArguments` 字段填入 `${param_0},${param_1},...`（由 `JSR223PreProcessor` 在运行时刷新变量值）。
  3. `queryArgumentsTypes` 按占位符顺序提供 JDBC 类型。
- **修正建议**：删除 §5.3 中"SQL 替换"和"queryArguments 留空"的错误说法。`query` 始终保留原始 SQL（含 `?`），`queryArguments` 填入变量引用，`queryArgumentsTypes` 填入类型映射。
- **修复措施**：规格书 §2.0 已统一明确查询使用 PreparedStatement 执行，参数通过 `?` 占位符绑定，运行时由 `JSR223 PreProcessor` 从列种子缓存随机采样并注入 `queryArguments`，同时按占位符顺序提供 `queryArgumentsTypes`。设计文档需按此口径删除 §5.3 中"SQL 替换"及"`queryArguments` 留空"的描述，确保 `query` 保留原始 SQL、`queryArguments` 填变量引用。

---

### 7. 枚举类型 `seed_num < 枚举值数量` 时的处理规则缺失（已解决）

- **规格书 §2.0**："当 `seed_num` 小于枚举值数量时，取前 `seed_num` 个值"。
- **设计文档 §3.4 / §5.2**：原仅说明"顺序循环选取枚举值"，未体现该截断逻辑。
- **修正建议**：`generate_column_seed()` 中 `enum_cycle()` 之前增加判断：`if seed_num < len(enum_values): seeds.extend(enum_values[:seed_num])`，否则才循环填充。
- **修复措施**：设计文档 §3.4 枚举值生成策略已补充"当 `seed_num`（扣除 NULL 后的剩余数量）小于枚举值数量时，仅取前 `seed_num` 个枚举值"的说明；§5.2 `generate_column_seed()` 算法已改为：先获取 `enum_values()`，若 `remain < len(enum_values)` 则截取前 `remain` 个值，否则调用 `enum_cycle(remain)` 循环填充，与规格书截断逻辑保持一致。

---

### 8. `SetupThreadGroup: 初始化共享内存种子区` 线程数与规格不符（已解决）

- **规格书 §2.2**（重构前）：明确说明"该线程组线程数等于数据生成线程组线程数（也等于写入线程组线程数）"。
- **设计文档 §3.6 / §5.2**（重构前）：`SetupThreadGroup` 仅创建空的共享内存区，单线程执行一次即可。
- **问题**：如果线程数强制等于写入线程数（如 20），每个线程都会执行同样的初始化代码（向 `props` 放入相同的键），虽然最终效果一样，但设计上显得多余，且与"全局 `props`"方案冲突。
- **修复措施**：2026-06-16 共享内存种子机制重构后：
  - 移除独立的"实时数据生成线程组"。
  - `SetupThreadGroup: 初始化共享内存种子区` 改为**单线程执行一次**，负责从列种子文件拼接完整的**行种子数据总集**并放入全局共享内存。
  - 所有写入线程共享同一块 `ArrayList<Object[]>`，不再按线程拆分。
  - 规格书 §2.2 已同步删除"线程数等于数据生成/写入线程组线程数"的描述，明确该 `SetupThreadGroup` 为单线程。

---

## 关键设计缺失（实现时会发现阻塞或重大返工）

### 9. 关系表初始化 INSERT 语句的生成机制完全缺失（已解决）

- **规格书 §2.0 / §2.2**：关系表（`rel_dbs`）作为元数据表，在 `SetupThreadGroup (DDL 执行)` 中"初始化写入一次"（预生成全部种子后批量写入）。
- **设计文档 §3.6**：仅提到"JDBCSampler: 初始化关系库下的元数据表"，**完全没有说明**：
  - INSERT 语句如何生成（单条 INSERT / 批量 INSERT / PreparedStatement？）。
  - 关系表的行数据如何组装（`primary_keys` 和 `data_cols` 的种子如何绑定为行）。
  - `seed_num` 如何决定插入行数（各列 `seed_num` 可能不同，行数取哪个？还是笛卡尔积？）。
  - 关系表是否也走"共享内存种子区"机制，还是直接在 SetupThreadGroup 的 JSR223Sampler 中生成并执行？
- **风险**：关系表的初始化写入是测试前置条件，缺失设计会导致实现阶段返工。
- **修复措施**：设计文档已补充关系表初始化写入机制：
  - 关系表的列种子生成方式与时序库表相同，行种子数据总集在 `SetupThreadGroup (DDL 执行)` 中装配。
  - 行种子总集行数 = 该表所有列 `seed_num` 的最大值；`seed_num` 较小的列按自身种子顺序循环复用，不进行笛卡尔积对齐。
  - 数据装配由挂载在 `JDBCSampler` 前的 `JSR223PreProcessor` 完成，JDBC 执行仍由 `JDBCSampler` 负责，使用 `batch_insert` 策略一次性批量写入关系表。
  - 当总行数超过 `batch_lines` 时，生成器在 `JDBCSampler` 外生成 `Loop Controller`（或 `While Controller`）分批次写入，每次循环装配并写入一个批次。

---

### 10. `batch_prepared` 策略在 JMeter 中的实际实现方式未设计（已解决）

- **规格书 §2.0**：支持 `batch_prepared` 模式（批量 PreparedStatement 写入）。
- **设计文档 §3.7**：`BatchPreparedStatementStrategy` 仅返回 `{"usePrepared": True}`，未说明批量如何实现。
- **问题**：JMeter 的 `JDBCSampler`（`Prepared Update Statement` 类型）**不支持一次绑定多组参数的 batch 写入**。它每次只执行一条 SQL、绑定一组参数。要实现真正的 batch prepared statement（如 JDBC `addBatch()` / `executeBatch()`），必须在 `JSR223Sampler` 中手写 Groovy JDBC 代码，绕过 JMeter 原生的 JDBCSampler。
- **风险**：如果按设计文档直接套用 `JDBCSampler`，`batch_prepared` 实际上会退化为逐条单条执行，性能与 `single_prepared` 无异，严重违背规格书意图。
- **建议补充**：
  - 方案 A（推荐）：`batch_prepared` 模式下，写入线程组使用 `JSR223Sampler`（而非 `JDBCSampler`），在 Groovy 中直接操作 JDBC Connection 的 `PreparedStatement.addBatch()` / `executeBatch()`。
  - 方案 B：`batch_prepared` 退化为 `batch_insert`（参数值拼接到 SQL 中），但失去 prepared statement 的防注入和预编译优势。
- **修复措施**：**已采用方案 A**。设计文档 §3.6 明确 `batch_prepared` 写入线程组使用 `JSR223Sampler`，并新增「JSR223Sampler（batch_prepared）」小节，给出 `JSR223Sampler` XML 模板、PreProcessor 数据准备脚本与 Sampler batch 执行脚本；脚本通过 `DataSourceElement.getConnection("jdbcConfig")` 复用 `JDBCDataSource` 定义的连接池，调用 `PreparedStatement.addBatch()` / `executeBatch()` 实现真正的批量 prepared statement 写入。§3.7 扩展 `WriteStrategy` 接口，新增 `get_sampler_type()` 与 `get_sampler_script()`，`BatchPreparedStatementStrategy` 返回 `JSR223Sampler` 类型与对应 Groovy 脚本，`jmx_builder` 据此生成正确的采样器节点。`JSR223PreProcessor` 仍负责准备当前批次数据（行拷贝、时间戳装配、首个 Primary Tag 设备号替换），并通过线程变量 `__BATCH_ROWS_${tableName}` 将数据传递给 `JSR223Sampler`。

---

### 11. 共享内存种子区的并发读写缺乏同步控制设计（已解决）

- **设计文档 §5.2**（重构前）：共享内存区使用 `props`（`JMeterProperties`）存储 `ArrayList<Map<String, Object>>`，由"生成实时数据"线程组持续写、写入线程组持续读。
- **问题**：`ArrayList` 和 `HashMap` 均非线程安全，并发读写可能导致 `ConcurrentModificationException`、读取到半完成 Map 或扩容问题。
- **修复措施**：2026-06-16 共享内存种子机制重构后：
  - 移除"生成实时数据"线程组，行种子数据总集在 `SetupThreadGroup` 中**一次性装配完成**。
  - 装配完成后，共享内存区对所有写入线程**只读**，写入线程仅执行 `sharedRows.get(...)` 和 `Object[].clone()`，不再发生写-写或读-写并发。
  - 因此无需额外同步控制（如 `CopyOnWriteArrayList`、双缓冲等），并发安全风险消除。

---

### 12. JDBC 参数类型映射表缺失（中等风险）

- **设计文档 §3.6**：查询采样器模板包含 `queryArgumentsTypes`，但未说明 `col_type`（如 `int8`、`float4`、`varchar(10)`）如何映射到 JMeter 的 JDBC 类型字符串（如 `BIGINT`、`REAL`、`VARCHAR`）。
- **风险**：类型映射错误会导致 JDBC 驱动在绑定参数时类型转换失败（如把字符串绑到 `INTEGER` 位置）。
- **建议补充**：在 `ddl_generator.py` 或独立模块中定义 `COL_TYPE_TO_JDBC_TYPE` 映射表，并在设计文档中列出映射规则。例如：
  | col_type | JDBC type |
  |----------|-----------|
  | int8 | BIGINT |
  | int4 | INTEGER |
  | float4 | REAL |
  | float8 | DOUBLE |
  | varchar(N) | VARCHAR |
  | timestamp | TIMESTAMP |

---

### 13. 多张表不同 `num_threads` 时的 JMeter 变量隔离缺失（中等风险 / 已解决）

- **规格书 §2.0 / §2.2**：`write_config` 分条目指定表名时，每张表可独立配置 `num_threads`、`device_per_thread`、`throughput` 等。
- **设计文档 §3.6**：所有线程组的 XML 示例均使用 `${num_threads}`、`${throughput}` 等**全局同名变量**。
- **问题**：如果 `t_cnc` 配置 `num_threads=20`，`t_motor` 配置 `num_threads=10`，两个写入线程组不能共享 `${num_threads}` 变量，否则 JMX 中只有一个值能生效。
- **修正建议**：为每张表生成独立的 JMeter 变量名，如 `${t_cnc_num_threads}`、`${t_motor_num_threads}`，或者在线程组内部直接使用常量值（通过 `stringProp` 直接写入数字，不通过变量引用）。推荐后者，减少变量复杂度。
- **修复措施**：当前版本先限制 `write_config` 分条目指定多表时各表 `num_threads` 必须相同，由生成器在配置校验阶段检查一致性，不一致时生成阶段报错。该约束用于简化每秒写入列数据数的计算与控制，同时避免全局同名变量冲突。规格书 §2.0、§2.2 及设计文档 §3.6 已补充该约束说明；后续版本支持按表独立指定 `num_threads` 时，将在线程组内使用 `stringProp` 常量值或为每张表生成独立变量名。

---

### 14. `ref` 外键延迟填充的具体实现机制缺失（中等风险）

- **设计文档 §3.4 / §5.2**：仅提到"拓扑排序确定生成顺序"和"引用列的种子直接从被引用列种子中采样"，§5.2 列种子生成算法中 `is_ref()` 分支直接 `pass`。
- **问题缺失**：
  - 拓扑排序的实现细节（如何处理循环引用？设计文档校验规则 R-PAR-007 只检测循环，没有说明检测到后的处理）。
  - "直接采样"是指读取被引用列的种子文件，还是在内存中共享同一列表引用？
  - 如果本表 `seed_num` > 被引用表 `seed_num`，采样时是否允许重复（有放回抽样）？
  - 如果引用链跨数据库（`ref:db1.table1.col1` → `ref:db2.table2.col2`），文件路径如何解析？
- **建议补充**：明确实现方案：
  1. 构建有向图，Kahn 算法拓扑排序。
  2. 被引用列先执行 `generate_column_seed()`，结果缓存到内存 `dict[(db, table, col)] -> list[str]`。
  3. 引用列生成时，从缓存列表中**有放回随机抽样** `seed_num` 次，保证本表 `seed_num` 不受被引用表限制。

---

### 15. 实时数据生成线程组的 `ConstantThroughputTimer` 吞吐量来源未定义（已解决 / 不再适用）

- **规格书 §2.2 / 设计文档 §3.6**（重构前）："生成实时数据"线程组独立挂载 `ConstantThroughputTimer`，但其吞吐量来源未定义。
- **问题**：实时数据生成频率需与写入频率匹配，否则共享内存区可能被快速耗尽或长期不刷新。
- **修复措施**：2026-06-16 共享内存种子机制重构后，**移除了独立的实时数据生成线程组**。行种子数据总集在 `SetupThreadGroup` 中一次性装配完成，后续由写入线程组直接拷贝使用，因此该问题不再存在。

---

### 16. 字符串种子值含换行符时的文件格式处理缺失（低风险）

- **设计文档 §3.4**：种子文件格式为"一行一个值的纯文本"。
- **问题**：`val_range` 为正则表达式时，生成的字符串值可能包含换行符（虽然当前字符集限制为 `[一-鿿a-zA-Z0-9-_]`，暂不含换行，但未来扩展其他类型时可能遇到）。
- **建议补充**：明确种子文件格式约束——生成的值必须经过转义，确保不含换行符；或在格式定义中说明采用 JSON Lines 等可安全承载任意字符串的格式。

---

### 17. `device_start` 参数通过 JMeter 命令行注入的机制未设计（低风险）

- **规格书 §2.0**：`device_start` 支持使用多个 JMeter 端进程横向扩展，各端以此为基准计算设备范围。
- **设计文档 §3.6**：多端设备号计算示例代码中使用了 `Integer.parseInt("${device_start}")`，但没有说明 `device_start` 如何从命令行传入。
- **问题**：JMeter 非 GUI 模式下，用户自定义变量通常通过 `-Jdevice_start=100` 传入，在 JMX 中通过 `${__P(device_start,1)}` 读取。设计文档 §3.6 的"JMX 可变参数暴露"小节提到了 `__P` 函数，但用户自定义参数配置的 XML 示例中用的是普通 `${device_start}`。
- **建议补充**：明确 `device_start` 使用 `__P` 函数暴露，如 `${__P(device_start,1)}`，并在 CLI 启动命令示例中说明 `-Jdevice_start=N` 的用法。

---

### 18. 写入线程组设备号计算中 `JMETER_THREAD_NAME` 的 parseInt 会失败（低风险）

- **设计文档 §3.6**：多端设备号计算示例代码：
  ```java
  int myIndex = Integer.parseInt(vars.get("JMETER_THREAD_NAME"));
  ```
- **问题**：JMeter 的 `JMETER_THREAD_NAME` 格式为 `"Thread Group Name 1-1"`（或类似字符串），包含字母和空格，无法直接 `parseInt`。
- **建议修正**：使用 `${__threadNum}` 函数或 JMeter 内置属性获取线程索引。Groovy 中可通过 `ctx.getThreadNum()` 获取从 0 开始的线程索引。

---

### 19. `conn_config` 扩展参数的通用 XML 生成机制缺失（低风险）

- **规格书 §2.0**：`conn_config` 不限于 `db_url`、`conn_pool_size`、`device_start`、`test_duration`，可根据需要扩展其他自定义配置属性。
- **设计文档 §3.6**：用户自定义参数配置的 XML 示例只列出了固定的 7 个参数（db_url, db_username, db_password, conn_pool_size, throughput, num_threads, test_duration），且 `main.py` 和 `jmx_builder.py` 的设计中未体现动态遍历 `conn_config` 列表生成 `<elementProp>` 的能力。
- **建议补充**：`jmx_builder.py` 的 Arguments 生成逻辑应遍历 `TestConfig.conn_config` 列表，为每个 `ConnConfigItem` 动态生成 `<elementProp>`，而非硬编码固定参数。

---

## 建议补充的细节

### 20. 时序表 DDL 中 `partition_interval` 的语法位置建议明确

- **规格书 §2.0**：`partition_interval` 为时序库/表级字段，但在附录 8.2 的 DDL 语法参考中未出现。
- **设计文档 §3.5**：将 `partition_interval` 放在 `PRIMARY TAGS` 之后，但 KaiwuDB 的实际语法位置需要确认。
- **建议**：对照 KaiwuDB 官方文档确认 `PARTITION INTERVAL` 的语法位置，或将其与 `RETENTIONS` 一并处理。

---

### 21. `primary_tags` 中 `nullable` 属性的处理建议与规格书语义对齐

- **规格书 §8.1**："所有 Primary Tag 列必须用 `NOT NULL` 约束定义，**不支持 `nullable` 属性**（固定视为 `false`）"。
- **设计文档 §3.1**：`ColTypeConfig` 模型包含 `nullable: bool = False`；§3.2 校验规则 R-PAR-014 要求 `primary_tags` 中 `nullable` 必须为 `false`。
- **建议**：从语义上，"不支持该属性"意味着配置中不应出现 `nullable` 字段。建议 `primary_tags` 中的列类型配置使用一个**独立模型**（不含 `nullable` 字段），或在 Pydantic 中通过 `model_validator` 拒绝 `primary_tags` 条目中出现 `nullable` 键（而非仅校验值为 false）。

---

### 22. 设计文档 §3.6 线程组编排图建议增加查询线程组的 `num_threads` 示例

- **规格书 §2.0**：查询配置 `num_threads` 默认值为 1，但示例中未展示非默认值的场景。
- **设计文档 §3.6**：线程组编排图中查询 Q1/Q2/Q3 没有标注线程数。
- **建议**：在图中标注查询线程组的 `num_threads` 来源（如 `num_threads=1` 或从 `query_config` 读取），并在 XML 示例中展示 `${q1_num_threads}` 或常量值的用法。

---

### 23. 输出目录和文件命名规范建议补充

- **设计文档**：未明确 `.jmx` 文件和 `seeds/` 目录的输出路径和命名规则。
- **建议补充**：
  - `.jmx` 输出路径：`output/{test_name}.jmx` 或命令行参数指定。
  - `seeds/` 输出路径：与 `.jmx` 同级或命令行参数指定，目录结构为 `seeds/{db_name}/{table_name}/{col_name}.seed.txt`（设计文档 §3.4 只写了 `seeds/{table}/`，建议补充数据库层级以避免表名冲突）。

---

## 修订建议汇总表

| 序号 | 问题 | 严重程度 | 涉及章节 | 建议措施 |
|------|------|---------|---------|---------|
| 1 | 查询 `statement` 模式未设计 | **严重** | §3.6, §5.3 | **已解决**：规格书移除 `query_config` 的 `mode` 属性，统一固定为 `prepared_statement`；§2.0 增加占位符绑定与报错备注 |
| 2 | 查询参数 fallback 轮询 vs 报错 | **严重** | §5.3 | **已解决**：设计文档删除 `ParamBinding.fallback`、fallback 分支及 `[fallback]` 标记，改为无法绑定到具体列时抛出 `ValidationError` |
| 3 | 时序表 `TAGS` 子句缺少类型 | **严重** | §3.5 | **已解决**：设计文档 §3.5 模板改为 `TAGS ({ptag_column_defs})`，Primary Tag 列按 `列名 类型 [NOT NULL]` 格式输出 |
| 4 | `type_proportion` 算法前后矛盾 | **严重** | §3.3, §5.1 | **已解决**：§3.3 删除 `ceil` 描述，统一引用 §5.1 的 `floor + 贪心` 算法，两节实现口径一致 |
| 5 | `ConstantThroughputTimer` 缺少 `calcMode` | **严重** | §3.6 | **已解决**：设计文档 §3.6 补充 `<intProp name="calcMode">0</intProp>`，`throughput` 修正为 `${__BeanShell(${write_throughput} / ${num_threads},)}` |
| 6 | `queryArguments` 与"SQL 替换"矛盾 | **严重** | §3.6, §5.3 | **已解决**：规格书 §2.0 明确 `query` 保留 `?`、`queryArguments` 填变量引用、`queryArgumentsTypes` 按占位符顺序提供；设计文档需删除 §5.3 错误描述 |
| 7 | 枚举 `seed_num < 枚举值数` 未处理 | **严重** | §3.4, §5.2 | **已解决**：设计文档 §3.4 补充枚举值截断说明，§5.2 `generate_column_seed()` 在 `enum_cycle()` 前增加 `remain < len(enum_values)` 判断，不足时取前 `remain` 个值，否则循环填充 |
| 8 | SetupThreadGroup 线程数与规格不符 | 已解决 | §3.6, §5.2 | **已解决**：2026-06-16 重构后移除实时数据生成线程组，`SetupThreadGroup` 改为单线程一次装配行种子总集，所有写入线程共享只读内存；规格书 §2.2 同步删除线程数等于写入线程数的描述 |
| 9 | 关系表 INSERT 机制缺失 | **高风险** | §2.2, §3.6, §5.2 | **已解决**：关系表列种子生成方式与时序库表相同；行种子总集行数取各列 `seed_num` 最大值，不足列循环复用；数据装配在 `JSR223PreProcessor` 中完成，JDBC 执行由 `JDBCSampler` 以 `batch_insert` 策略一次性批量写入；总行数超过 `batch_lines` 时通过 `Loop Controller` 分批次写入 |
| 10 | `batch_prepared` JMeter 实现缺失 | **高风险** | §3.6, §3.7 | **已解决**：`batch_prepared` 模式使用 `JSR223Sampler`，通过 `DataSourceElement.getConnection("jdbcConfig")` 获取连接池连接，手写 `PreparedStatement.addBatch()` / `executeBatch()`；`JSR223PreProcessor` 准备 batch 行数据并通过线程变量 `__BATCH_ROWS_${tableName}` 传递给 Sampler |
| 11 | 共享内存并发安全缺失 | 已解决 | §5.2 | **已解决**：2026-06-16 重构后行种子总集在 `SetupThreadGroup` 中一次性装配，后续只读，不存在并发写操作，无需同步机制 |
| 12 | JDBC 参数类型映射表缺失 | 中风险 | §3.6 | 补充 `COL_TYPE_TO_JDBC_TYPE` 映射 |
| 13 | 多表变量隔离缺失 | 中风险 / 已解决 | §2.0 / §2.2 / §3.6 | 当前版本要求 `write_config` 分条目指定多表时各表 `num_threads` 必须相同，由生成器校验一致性；后续版本支持按表独立 `num_threads` 时，在线程组内使用 `stringProp` 常量值或为每张表生成独立变量名 |
| 14 | `ref` 外键实现细节缺失 | 中风险 | §3.4, §5.2 | 补充拓扑排序和内存采样设计 |
| 15 | 实时数据生成吞吐量来源缺失 | 已解决 / 不再适用 | §3.6 | **已解决**：2026-06-16 重构后移除实时数据生成线程组，行种子总集在 `SetupThreadGroup` 中一次性装配，该问题不再存在 |
| 16 | 种子文件换行符处理 | 低风险 | §3.4 | 明确转义约束或采用 JSON Lines |
| 17 | `device_start` 命令行注入机制 | 低风险 | §3.6 | 补充 `-Jdevice_start` 和 `__P` 用法 |
| 18 | `JMETER_THREAD_NAME` parseInt 错误 | 低风险 | §3.6 | 改用 `ctx.getThreadNum()` |
| 19 | `conn_config` 动态参数生成 | 低风险 | §3.6 | 遍历列表动态生成 XML |
| 20-23 | 语法位置、模型语义、命名规范等 | 建议 | 多处 | 按具体建议补充 |

---

## 总体评价

设计文档整体架构清晰，分层合理，策略模式扩展性设计良好。但在以下方面存在明显不足：

1. **与规格书的直接冲突较多**：查询模式、DDL 语法、算法一致性等 6 处严重矛盾必须在编码前修正（参数 fallback 已按建议改为报错）。
2. **JMeter 运行时机制设计深度不足的风险已降低**：`batch_prepared` 已明确采用 `JSR223Sampler`，通过 `DataSourceElement.getConnection("jdbcConfig")` 获取连接池连接，并调用 `PreparedStatement.addBatch()` / `executeBatch()` 实现真正的批量 prepared statement 写入；共享内存并发安全、多表变量隔离等设计已补充，但仍需在编码阶段严格按文档实现。
3. **关系表初始化写入已补充**：作为测试前置条件，关系表的元数据初始化已明确由 `JSR223PreProcessor` 装配、`JDBCSampler` 以 `batch_insert` 策略执行，阻塞风险解除。

建议：`batch_prepared` 实现方式已补充设计；在进入编码前，优先修正剩余严重矛盾与高风险缺失设计（并发安全、JDBC 类型映射、多表变量隔离、`ref` 外键实现等），并产出更新后的设计文档版本。
