# Quality Review

## 1. Boundary Conditions

**Status**: ❌ Fail

**Findings**:
- 多个边界条件未在 Spec 或 Design 中明确：
  - 空配置或缺失必填字段（如数据库名、表名）时是否抛异常；
  - 数据库名/表名/列名中包含关键字或特殊字符时是否需要转义或加引号；
  - `nullable` 字段缺失时默认值为 `false`（生成 `NOT NULL`），但 Design 中未明确说明这一默认值策略是否由 `config-parser` 保证；
  - ~~时序表 `partition_interval` 的语法位置未明确，Design 的 Open Question 第 4 点已提出~~ ✅ **已解决**: 已对照 KaiwuDB 官方文档修正，时序库建库语法为 `CREATE TS DATABASE name [RETENTIONS keep_duration] [PARTITION INTERVAL interval] [COMMENT [=] comment_text];`，其中 `RETENTIONS` 和 `PARTITION INTERVAL` 不需要 `WITH` 关键字，参数值不需要加单引号。已在 Spec 中修正示例：`CREATE TS DATABASE iot_monitor PARTITION INTERVAL 1d;`；
  - ~~DDL 语句分隔符是否使用分号，以及 KaiwuDB 是否支持多条语句一次执行，Design 的 Open Question 第 1 点已提出~~ ✅ **已解决**: 确认支持分号分隔多语句一次执行，已在 Spec 中添加 `Requirement: Support multi-statement execution`；
  - ~~表名和列名大小写敏感性假设未验证，Design 的 Open Question 第 2 点已提出~~ ✅ **已解决**: 虽然KaiwuDB对未加引号标识符的大小写不敏感，但为规范易读，统一所有SQL标识符和关键字使用小写，已在 Design 中添加决策说明；
  - ~~DDL 生成失败时是否继续生成其他表的 DDL，Design 的 Open Question 第 3 点已提出~~ ✅ **已解决**: 该问题不成立。DDL 生成器是文本生成任务，真正的失败（如格式化错误）会导致 Python 异常退出，无法继续；SQL 语法错误只在执行时才发现，超出生成器职责范围。正确的处理方式是在配置解析阶段验证输入，生成器内部任何异常应立即抛出终止。
  - ~~表名是否使用限定名（database.table）格式~~ ✅ **已解决**: 明确要求所有表名必须使用限定名格式，已在 Design 中添加决策说明，Spec 中添加 `Requirement: Use qualified table names`。

**Recommendations**:
- ~~在实现前确认以下边界条件，并在 Spec 中补充：~~
  - ~~1. **DDL 语句分隔符**：确认 KaiwuDB 对分号分隔的多语句支持情况；若不支持，考虑每条语句单独输出或在 JMX 中分批执行；~~ ✅ **已确认**: 支持分号分隔多语句一次执行，已在 Spec 中添加对应需求。
  - ~~2. **大小写策略**：确认 KaiwuDB 对未加引号的标识符是否区分大小写，并在列名生成器中固化规则；~~ ✅ **已确认**: 虽然KaiwuDB对未加引号标识符的大小写不敏感，但为规范易读，统一所有SQL标识符和关键字使用小写，已在 Design 中添加决策说明。
  - ~~4. **`partition_interval` 语法位置**：对照 KaiwuDB 官方文档确认，避免生成的 DDL 语法错误；~~ ✅ **已解决**: 已在 docs/specs/kwdb-svt-test-plan-generator-spec.md 8.2 章节补充完整语法说明，并在 Spec 中修正示例。
- 在实现前确认以下边界条件，并在 Spec 中补充：
  ~~3. **错误处理策略**：明确单表生成失败时是终止整个生成流程还是记录错误并继续；建议默认继续生成其他表，但收集错误列表供调用方处理；~~ ✅ **结论**: 该问题不成立。DDL 生成器是文本生成任务，真正的失败（如格式化错误）会导致 Python 异常退出，无法继续；SQL 语法错误只在执行时才发现，超出生成器职责范围。正确的处理方式是在配置解析阶段验证输入，生成器内部任何异常应立即抛出终止。
  5. **表名限定名规范**：✅ **已明确**: 所有表名必须使用 `database.table` 限定名格式，无需再确认。
- 将以上边界条件处理作为独立任务写入 `tasks.md`。

## 2. Rollback Plan

**Status**: ✅ Pass

**Findings**:
- `ddl-generator` 是新增模块，不修改现有代码，回滚操作仅为删除新增文件；
- 该模块的下游依赖是 JMX 生成阶段的 SetupThreadGroup，当前尚未接入；
- Design 中已明确不支持 DDL 执行，仅生成脚本，因此回滚不会影响数据库状态。

**Recommendations**:
- 在 `tasks.md` 中保留一条任务：确认 `config-parser` 输出格式稳定后再让 `ddl-generator` 强依赖其结构，避免接口变更导致联动修改；
- 若生成的 SQL 脚本被其他变更提前使用，应单独提交脚本生成逻辑，便于回滚时区分生成器与消费方。

## 3. Test Coverage

**Status**: ⚠️ Warning

**Findings**:
- Spec 中已覆盖关系库和时序库的主要 DDL 场景，以及列名生成、NOT NULL 约束、数据类型等；
- 但缺少以下测试要求：
  - 多数据库、多表的分组输出测试；
  - 空配置、缺失字段、非法数据类型等错误输入测试；
  - 生成的 SQL 脚本能否被 KaiwuDB 直接执行的语法验证（至少关键语句）；
  - 列名生成器中多列同类型的序号递增逻辑；
  - `IF NOT EXISTS`、`WITH ENCODING`、`COMMENT` 等可选子句的组合测试。

**Recommendations**:
- 在 `tasks.md` 中补充以下测试任务：
  1. 关系库 DDL 单元测试：覆盖 `CREATE DATABASE` 与 `CREATE TABLE` 的各种可选子句组合；
  2. 时序库 DDL 单元测试：覆盖 `RETENTIONS`、`PARTITION INTERVAL`、`PRIMARY TAGS`、`WITH HASH` 等；
  3. 列名生成器单元测试：覆盖所有类型前缀（`pk`、`col`、`ptag`、`rtag`）及序号递增；
  4. 错误处理测试：覆盖缺失必填字段、未知数据类型、生成失败时的行为；
  5. SQL 脚本输出测试：验证分号分隔、按库表分组、整体可执行性；
- 建议在 `tests/ddl_generator/` 下组织测试文件。

## 4. Backward Compatibility

**Status**: ⚠️ Warning

**Findings**:
- 本次变更是新增模块，不修改现有接口；
- 但列名生成规则 `{type_prefix}_{data_type}_{sequence}` 将被种子数据生成器、JMX 生成器等下游模块依赖，一旦确定后变更成本高；
- 当前假设 KaiwuDB 对标识符大小写不敏感，若该假设错误，可能影响后续模块对列名的引用一致性。

**Recommendations**:
- 在 Open Questions 解决之前，将列名生成器视为实验性 API，不对外承诺稳定；
- 在 `__init__.py` 中显式导出公共 API，隐藏内部实现模块；
- 建议列名生成器将标识符统一为同一种大小写格式（如全小写或全大写），并在文档中说明，确保下游模块引用一致；
- 若后续需要调整列名规则，应提供版本化生成器或别名机制，避免一次性破坏所有依赖模块。

## 5. Task Granularity

**Status**: ❌ Fail

**Findings**:
- 当前 `tasks.md` 尚未创建，缺少可执行的任务清单；
- `ddl-generator` 涉及多个独立能力：关系库 DDL、时序库 DDL、列名生成、数据类型映射、SQL 脚本组织，如果任务粒度过粗，将难以并行开发和评审。

**Recommendations**:
- 将实现拆分为以下最小可验证任务：
  1. 创建 `src/ddl_generator/__init__.py` 并导出公共 API；
  2. 实现数据类型映射器（配置小写类型 → KaiwuDB 大写语法）；
  3. 实现 `ColumnNameGenerator` 类及所有前缀/序号规则；
  4. 实现关系库 `CREATE DATABASE` 生成（含 `IF NOT EXISTS`、`WITH ENCODING`、`COMMENT`）；
  5. 实现关系库 `CREATE TABLE` 生成（含列定义、NOT NULL、PRIMARY KEY、COMMENT）；
  6. 实现时序库 `CREATE DATABASE` 生成（含 `RETENTIONS`、`PARTITION INTERVAL`）；
  7. 实现时序库 `CREATE TABLE` 生成（含 `TAGS`、`PRIMARY TAGS`、`WITH HASH`、`WITH RETENTIONS`）；
  8. 实现按库/表分组的 SQL 脚本输出；
  9. 实现错误处理策略（失败继续并收集错误，或按配置决定）；
  10. 编写 `ColumnNameGenerator` 单元测试；
  11. 编写关系库 DDL 单元测试；
  12. 编写时序库 DDL 单元测试；
  13. 编写脚本输出与错误处理测试；
  14. 运行全部测试并确保通过。
- 每条任务应附带验收标准和预估输入/输出示例。

## Overall Assessment

`ddl-generator` 的提案、Spec 和设计整体方向合理，能够支撑测试计划生成器的初始化需求。所有关键问题已解决：
- ✅ **DDL 语句分隔符**: 确认支持分号分隔多语句一次执行，已在 Spec 中添加 `Requirement: Support multi-statement execution`。
- ✅ **表名限定名**: 明确要求所有表名使用 `database.table` 限定名格式，已在 Design 中添加决策说明，Spec 中添加 `Requirement: Use qualified table names`。
- ✅ **SQL标识符和关键字大小写策略**: 虽然KaiwuDB对未加引号标识符的大小写不敏感，但为规范易读，统一所有SQL标识符和关键字使用小写，已在 Design 中添加决策说明。
- ✅ **错误处理策略**: DDL 生成器是文本生成任务，真正的失败会导致 Python 异常退出；SQL 语法错误只在执行时才发现，超出生成器职责范围。正确的处理方式是在配置解析阶段验证输入，生成器内部任何异常应立即抛出终止。
- ✅ **partition_interval 语法位置**: 已在 docs/specs/kwdb-svt-test-plan-generator-spec.md 8.2 章节补充完整语法，并在 Spec 中修正示例。

剩余 `tasks.md` 尚未细化。建议在创建 `tasks.md` 时：

1. 补充错误输入和边界条件的测试任务；
2. 将关系库 DDL、时序库 DDL、列名生成、脚本输出拆分为独立任务；
3. 明确测试文件位置和执行策略；
4. 新增任务：确保所有生成的 DDL 语句使用表名限定名格式，并在测试中验证多数据库场景下的正确性。
5. 新增任务：确保所有生成的 DDL 语句中标识符和关键字统一使用小写，并在测试中验证。

在补齐上述内容后，本变更可以进入实现阶段。
