## Context

关系表初始化不是独立线程组，而是附加在 DDL `SetupThreadGroup` 内的每表 `LoopController + JSR223PreProcessor + JDBCSampler` 子树。当前 pipeline 通过 `_build_relational_init_specs(model)` 从 `model.rel_dbs` 构造初始化规格；空 `rel_dbs` 或零关系表自然得到空列表，JMX 生成器也不会创建关系初始化子树。现有行为正确，但规格与集成测试未锁定该条件，纯时序模型 smoke 容易被误判为缺失关系初始化。

## Goals / Non-Goals

**Goals:**

- 将“仅实际存在关系表时生成关系初始化子树”定义为规范行为。
- 在 pipeline、DDL Setup JMX 结构和端到端生成层增加正反场景测试。
- 保持纯时序模型仍生成时序 DDL、共享内存和写入元素。
- 用 4000 列、99% NULL 的纯时序 fixture 完成真实 KaiwuDB smoke。
- 同步原始规格、原始设计和 OpenSpec 过程文档。

**Non-Goals:**

- 不改变 `TestModelConfig` YAML schema。
- 不把关系初始化拆成独立 `SetupThreadGroup`。
- 不重构关系表初始化批次、FK 顺序或采样器实现。
- 不改变有关系表模型的 JMX 结构。

## Decisions

1. **以实际关系表数量作为唯一条件。** `_build_relational_init_specs` 遍历 `model.rel_dbs[*].tables`；结果为空时向 skeleton 传空列表。相比检查 `rel_dbs` 字段是否显式出现，此方式同时覆盖字段缺省、空列表和仅含空数据库节点三种情况。
2. **保留 DDL SetupThreadGroup。** 纯时序模型仍有时序库和表 DDL，因此只跳过 `RelInit_*` 子树，不跳过整个 DDL SetupThreadGroup。
3. **测试结构标记而非内部实现。** 反向场景断言生成 JMX 不含 `RelInit_`、`relprep` 和关系初始化 `LoopController`；正向场景断言每张关系表仍产生对应子树。避免把测试绑定到私有函数细节。
4. **当前正确实现不做无意义重写。** 若测试证明现有条件链已满足 delta spec，仅补文档和回归测试；当前 `batch_prepared` NULL 绑定与超长 SQL 分块修复作为 sparse smoke 必要前置独立保留。

## Risks / Trade-offs

- **风险：字符串断言误伤普通 LoopController。** 使用 `RelInit_`/`relprep` 专属标记，并在结构测试中按 sampler 名称定位。
- **风险：纯时序 smoke 只证明反向场景。** 增加含关系表模型的正向集成测试，并继续运行原 shig canonical smoke。
- **风险：4000 列放大 Groovy class 常量限制。** INSERT SQL 按安全长度拆分成多个字符串常量后运行时拼接，并由单元测试锁定。
- **权衡：当前 change 同时承接 nullable 调试前置。** 在任务和提交中区分条件 Setup 契约、NULL 绑定、大 SQL 分块和 fixture，保持证据可追踪。
