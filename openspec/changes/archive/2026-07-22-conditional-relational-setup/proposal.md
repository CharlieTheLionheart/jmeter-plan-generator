## Why

当前实现已在模型不包含关系库表时返回空 `rel_init_specs`，但原始规格、设计文档和 OpenSpec 契约未明确这一条件行为，也没有 JMX 集成测试防止后续回归。稀疏 4000 列纯时序模型 smoke 暴露了该文档缺口，并容易让维护者误以为关系表初始化缺失属于失败。

## What Changes

- 明确规则：`TestModelConfig` 未声明 `rel_dbs`，或 `rel_dbs` 中不存在任何关系表时，不生成任何关系表初始化 `LoopController`、`JSR223PreProcessor` 或 `JDBCSampler`。
- 明确纯时序模型仍生成时序库 DDL、共享内存、写入和查询所需测试计划元素；缺少关系初始化不是错误。
- 保持有关系表时现有行为：每张关系表继续生成对应初始化子树。
- 同步原始规格、原始设计文档和 OpenSpec delta spec。
- 增加 pipeline 与 JMX 集成回归测试，并使用纯时序稀疏 4000 列 fixture 验证。
- 纳入本次调试已发现的 `batch_prepared` NULL `setObject(index, null)` 绑定及超长 Groovy SQL 分块修复，作为纯时序稀疏宽表 smoke 的必要前置。

## Capabilities

### New Capabilities

- `conditional-relational-setup`: 定义关系表初始化元素按模型中实际关系表存在性生成的规则。

### Modified Capabilities

无。仓库当前没有已归档的 `openspec/specs/` 主能力目录；本次以独立 capability 建立契约。

## Impact

- 文档：`docs/specs/kwdb-svt-test-plan-generator-spec.md`、`docs/designs/kwdb-svt-test-plan-generator-design.md`。
- OpenSpec：本 change 的 delta spec、design、review、tasks。
- 实现与测试：JMX skeleton/pipeline 条件生成测试、`batch_prepared` NULL 绑定、超长 SQL 分块、稀疏宽表 fixture。
- API、YAML schema、数据库 schema 和依赖均不变。
