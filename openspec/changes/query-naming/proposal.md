## Why

JMeter ThreadGroup 当前用截断 SQL 文本作为 testname（`[Query] SELECT rtag_varchar_1, count(*...`），沟通失败查询时不便定位（如 `[Query] SELECT rtag_varchar_1...` 实际是 12 条 query 中的第几条？哪条业务查询？）。

## What Changes

- `QueryConfig` 加可选字段 `name: Optional[str]`
- `generate_query_thread_groups` 命名规则：
  - `qc.name` 存在 → ThreadGroup `name="Query-{qc.name}"` + `testname="[Query] {qc.name}"`
  - 否则 → 按模板顺序命名为 `query{N}`（N 从 1 起）
- 不改 SQL 内容、不改 `?` 占位符语义、不改 queryArgumentsTypes 数量
- test_cfg fixture 可选地用 `name:` 字段显式命名

## Capabilities

### New Capabilities
- `query-naming`: query SQL 命名约定（默认按模板顺序）

### Modified Capabilities
- `query-functionality`: `QueryConfig` 模型加 `name` 字段；`generate_query_thread_groups` 用 `qc.name`/`query{N}` 生成 ThreadGroup testname
- `jmx-skeleton-generator`: query ThreadGroup 命名（name/testname 来源）

## Impact

- 受影响模块：`config-parser`（模型字段）、`jmx-skeleton-generator`（query_groups 命名）
- 已有 fixture（`tests/kwjdbc_svt/fixtures/test_cfg*.yaml`）未设 `name`，默认走 `query{N}` 命名
- 回归测试：`tests/jmx_skeleton_generator/test_generators.py` 加 3 个断言（默认模板顺序、显式 name 覆盖、字段 round-trip）
- 不破坏现有 schema（DCR 只加可选字段）