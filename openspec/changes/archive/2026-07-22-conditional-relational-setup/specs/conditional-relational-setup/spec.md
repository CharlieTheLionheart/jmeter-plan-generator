## ADDED Requirements

### Requirement: 关系表初始化按实际关系表存在性生成
测试计划生成器 MUST 仅为模型中实际声明的关系表生成关系表初始化子树。关系表初始化子树由该表对应的 `LoopController`、`JSR223PreProcessor` 和 Prepared Update `JDBCSampler` 组成，并附加在 DDL `SetupThreadGroup` 内。

#### Scenario: 未声明关系库
- **WHEN** `TestModelConfig.rel_dbs` 缺省或为空，且模型包含至少一个时序库表
- **THEN** 生成的 JMX MUST 不包含任何 `RelInit_` sampler、`relprep` preprocessor 或关系表初始化 `LoopController`
- **AND** 时序库 DDL、共享内存和写入相关测试计划元素 MUST 正常生成

#### Scenario: 关系库节点不含表
- **WHEN** `TestModelConfig.rel_dbs` 存在，但所有关系库节点的 `tables` 均为空
- **THEN** 生成的 JMX MUST 不包含任何关系表初始化子树
- **AND** 该情况 MUST 被视为合法模型，不得因缺少关系表初始化而报错

#### Scenario: 模型包含关系表
- **WHEN** `TestModelConfig.rel_dbs` 中包含一张或多张关系表
- **THEN** 生成器 MUST 为每张关系表生成且仅生成一个对应关系表初始化子树
- **AND** 初始化 SQL、列类型、种子文件和循环次数 MUST 继续使用该表的关系初始化规格

### Requirement: 纯时序稀疏宽表支持 NULL PreparedStatement 绑定
生成器 MUST 支持纯时序模型中 nullable 数据列的 `batch_prepared` 写入。Groovy `null` 单元 MUST 通过 `PreparedStatement.setObject(index, null)` 绑定为 SQL NULL；非 NULL 数值仍 MUST 使用对应 typed setter。

#### Scenario: 99% NULL 的宽表写入
- **WHEN** 纯时序模型包含 4000 个 nullable 数据列且 `null_rate=0.99`
- **THEN** 生成的种子中每个列类型组 MUST 按 `floor(seed_num * 0.99)` 生成 NULL
- **AND** 真实 KaiwuDB smoke MUST 无 NULL 参数绑定错误

### Requirement: 超长 Prepared SQL 可被 Groovy 编译
生成器 MUST 避免把超过 Groovy/JVM class-file 字符串常量限制的 INSERT SQL 生成为单一字符串常量。

#### Scenario: 4000 列 INSERT SQL
- **WHEN** `batch_prepared` INSERT SQL 因 4000 列而超过单一字符串常量限制
- **THEN** 生成器 MUST 将 SQL 拆分为安全长度的多个 Groovy 字符串常量并在运行时拼接
- **AND** JSR223 sampler MUST 成功编译和执行
