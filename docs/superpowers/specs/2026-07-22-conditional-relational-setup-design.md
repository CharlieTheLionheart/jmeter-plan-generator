---
comet_change: conditional-relational-setup
role: technical-design
canonical_spec: openspec
---

# 条件关系表初始化 — 深度技术设计

## 1. Context

关系表初始化不是独立 `SetupThreadGroup`，而是附加在 DDL `SetupThreadGroup` 内的每表 `LoopController + JSR223PreProcessor + JDBCSampler` 子树。`kwjdbc_svt.main._build_relational_init_specs(model)` 按 `model.rel_dbs[*].tables` 实际遍历，结果列表经 `JMXSkeletonGenerator(rel_init_specs=...)` 传入 `generate_ddl_setup_thread_group`。当模型没有 `rel_dbs` 或不含任何关系表时，结果列表为空，骨架生成器不会创建 `RelInit_*` 子树。

当前实现已满足"无关系表不生成关系初始化"的契约，但：

- 原始规格与设计文档未显式记录此条件分支。
- `tests/jmx_skeleton_generator/test_generators.py` 和 `test_assembler.py` 现有 `rel_init_specs=` 参数路径被绕过；端到端 `_run_pipeline` 测试从未断言该 marker。
- 4000 列稀疏纯时序模型 smoke 暴露了文档缺口：维护者可能误把"无 `RelInit_`"当作生成器缺陷。
- `batch_prepared` 在大宽表下两处生成器缺陷：`setNull` 路径与超长 Groovy 字符串常量，会被 sparse smoke 复现。

本 DCR 目标是把"条件生成"提升为可强制规范与可回归的契约。

## 2. Goals / Non-Goals

**Goals**

- 显式规范：模型无实际关系表时不生成关系表初始化子树；纯时序模型合法。
- 在 jmx_skeleton_generator 集成测试中新增正反断言锁住 marker。
- 修复 sparse smoke 暴露的 `setNull` 路径与大 SQL 拆分。
- 同步原始 spec/design 文档三处对应节。
- 用 4000 列 99% NULL 稀疏宽表 fixture + 真实 KaiwuDB smoke 验证。

**Non-Goals**

- 不改 `TestModelConfig` YAML schema。
- 不把关系初始化拆为独立 `SetupThreadGroup`。
- 不重构关系表初始化批次、FK 顺序或采样器实现。
- 不改变有关系表模型的 JMX 结构。
- 不在 main 流水线每次都跑 5 分钟 sparse smoke；sparse smoke 作为本 DCR 验证输入而非周期性合约。

## 3. 关键决策

1. **判定入口不变**。`_build_relational_init_specs` 保持现状，依赖 `model.rel_dbs[*].tables` 实际遍历；同时校验"至少一个库非空"（`src/config_parser/models.py:280-283` 已实现）保证纯时序模型合法。
2. **JMX 集成测试以 marker 断言**。`RelInit_` 前缀的 sampler name 和 `relprep` 后缀的 preprocessor name 是私有实现产物，但比直接断言私有函数更稳定；保留对 `LoopController.loops` 的数值断言作为正向证据。
3. **`setNull` → `setObject`**。`pstmt.setObject(colIdx+1, null)` 走 driver 推断路径，与 typed setter 分派互补，不影响非 NULL 单元。`setObject(value)` 形态仍禁止——该路径是 F-1 修复点。
4. **大 SQL 拆分阈值**：每段不超过 16 KB UTF-8 字节（约 8 字节/字符 × 2K 字符），运行时 `[...].join('')`。对 4000 列 varchar(2000) ≈ 73 KB SQL 拆为 5 段；与 Groovy 编译 class 文件 64 KB 单字符串常量上限留 4× 余量。
5. **sparse fixture 视作验证输入**。`tests/kwjdbc_svt/fixtures/test_model_shig_sparse.yaml` + `test_cfg_shig_sparse.yaml` 写好后，本 DCR 阶段跑一次 5 分钟 sparse smoke 留痕，但不要求 main 流水线每次都跑。

## 4. 架构与数据流

```
TestModelConfig
  └─ _build_relational_init_specs(model)        # 已有：遍历 rel_dbs[*].tables
        │
        ├─ []                       # 条件分支 A：无关系表
        │   └─ JMXSkeletonGenerator(rel_init_specs=[])
        │        └─ generate_ddl_setup_thread_group(ddl_statements, rel_init_specs=[])
        │             └─ for spec in rel_init_specs or []: 不进入
        │             └─ 输出: 仅 DDL sampler，无 RelInit_* 子树
        │
        └─ [spec_1, ..., spec_N]    # 条件分支 B：有关表
            └─ JMXSkeletonGenerator(rel_init_specs=[...])
                 └─ generate_ddl_setup_thread_group(ddl_statements, rel_init_specs=[...])
                      └─ for spec in rel_init_specs:
                           └─ LoopController(loops=total_rows // batch_lines)
                                └─ JSR223PreProcessor: 列种子装配 + param_N
                                └─ JDBCSampler: Prepared Update Statement
```

Sparse 4000 列模型走分支 A；现有 shig 走分支 B，行为不变。

## 5. 实现分解

### 5.1 条件生成集成测试

- `tests/jmx_skeleton_generator/test_generators.py::TestGenerateDDLSetupThreadGroup` 增加：
  - `test_rel_init_specs_empty_emits_no_loop_controller` — 传入 `rel_init_specs=[]` 与 DDL sampler，断言输出不含 `RelInit_`、`relprep` 或 `LoopController for db_*`。
  - `test_rel_init_specs_produces_rel_subtree` — 传入一张关系表 spec，断言出现且仅出现一个 `RelInit_` 元素、`LoopController.loops == total_rows // batch_lines`。
  - `test_rel_init_specs_appended_after_ddl` — DDL 与 rel init 混合时，DDL sampler 仍出现在关系初始化子树之前。
- `tests/jmx_skeleton_generator/test_assembler.py::TestJMXSkeletonGenerator` 增加：
  - `test_rel_init_specs_appears_in_jmx`
  - `test_empty_rel_init_specs_emits_no_rel_subtree`
  - `test_rel_init_loop_count_matches_spec`
- `tests/kwjdbc_svt/test_main.py::TestEndToEnd` 增加：
  - `test_ts_only_model_does_not_emit_rel_init`
  - `test_rel_model_emits_loop_controller_per_table`

### 5.2 batch_prepared NULL 绑定

- [src/jmx_skeleton_generator/generators/write_groups.py:582-587](src/jmx_skeleton_generator/generators/write_groups.py) 替换为 `pstmt.setObject(colIdx + 1, null)`。
- 在 `tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py::TestBatchPreparedSamplerScriptStructure` 增加两条断言：含 `setObject(colIdx + 1, null)`；不含 `setObject(colIdx + 1, value)`。

### 5.3 超长 Groovy SQL 拆分

- `_build_batch_prepared_sampler_body` 在生成 `insert_sql` 字面量时按每段 ≤ 16 KB 切片为多个 Groovy 字符串常量，运行时 `[...].join('')`。
- 新增 `test_large_insert_sql_is_split_into_safe_literals`：4000 列 varchar(2000) 时输出脚本最大行长度 < 60 KB。
- 已通过 5 分钟 sparse smoke：603 samples、0 errors、t_cnc 写入 600 行、99% NULL 种子已落 DB。

### 5.4 sparse fixture 与 smoke

- 新增 [test_model_shig_sparse.yaml](tests/kwjdbc_svt/fixtures/test_model_shig_sparse.yaml) + [test_cfg_shig_sparse.yaml](tests/kwjdbc_svt/fixtures/test_cfg_shig_sparse.yaml)。
- smoke：5 min 真实 KaiwuDB，已落地 603 samples、0 errors、600 行、NULL 比例正确。

## 6. 测试策略

| 层级 | 覆盖 | 文件 |
|------|------|------|
| 单元 | JMX 结构、sampler 行为、SQL 分块 | `tests/jmx_skeleton_generator/test_generators.py`、`test_assembler.py`、`test_batch_prepared_typed_binding.py` |
| 集成 | `_run_pipeline` 端到端 marker 断言 | `tests/kwjdbc_svt/test_main.py` |
| Smoke | sparse 5min + shig canonical 10s | `/tmp/jmeter-shig-sparse`、`/tmp/jmeter-shig-canonical` |

不重复造覆盖：保留现有 `tests/direct_insert_write/test_sampler_generator.py::TestRelationalInit` 与 `test_preprocessor_generator.py` 的子测试作为下游稳定器。

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| marker 断言误伤普通 `LoopController` | marker `RelInit_`/`relprep` 唯一；正向场景固定在 `RelInit_*` 名称中 |
| Sparse smoke 必须从 JMX 输出目录运行 | skill 与 runbook 已记录；本次以 `cd /tmp/jmeter-shig-sparse && jmeter ...` 验证 |
| 大 SQL 拆分引入列序错位 | 切片只发生在字面量拼装层；列名与占位符整体不拆分；测试覆盖全列 |
| shig canonical smoke factory=0 | 与本 DCR 无关，由 `LoopController.loops=1` 限制导致；本 DCR 仅校验"条件分支"标记存在性，不修复批次循环 |
| 回滚：当前实现已正确，可仅回滚 NULL 绑定或 SQL 分块提交 | 提交可拆分为多个原子 commit |

## 8. 验收

- 全量 `python -m pytest tests/` 通过（当前 635 passed）。
- Sparse 5min smoke：603 samples、0 errors、600 行、99% NULL 种子。
- shig canonical smoke（从 JMX 输出目录运行）：0 errors，关系/时序表行数符合预期。
- todolist.md 中 spec gap #3 标记为已完成。

## 9. 开放问题

- shig canonical smoke 中 `factory` 与 `workshop` 行数为 0，是否需要在后续 DCR 中调整 `LoopController.loops`？本 DCR 不解决。
- 稀疏 fixture 是否进入主目录成为 fixture 套件？当前仅作为验证输入。
