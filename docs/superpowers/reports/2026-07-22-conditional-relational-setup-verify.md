# 验证报告 — conditional-relational-setup

- Change: conditional-relational-setup
- Date: 2026-07-22
- 验证模式: full（13 tasks / 1 capability / 8 changed files,均达阈值）
- 验证人: Claude (executing-plans 阶段已通过 standard review)

## 摘要

| 维度 | 状态 |
|------|------|
| Completeness | 13/13 tasks 完成；3 个 delta requirement 全部实现 |
| Correctness | 3/3 requirements 覆盖；8 个新集成测试 + 1 NULL setObject 锁定 + 1 SQL 拆分锁定 |
| Coherence | proposal/design/delta spec 与实现一致；design doc 实施过程未漂移 |

## 任务完成

13/13 tasks 已勾选（含 1.1 原始规格补节、1.2 原始设计补节、1.3 三件套一致性、2.1-2.3 条件关系初始化集成测试、3.1-3.3 稀疏宽表前置修复、4.1-4.4 验证与维护清单）。

## Spec 覆盖

delta spec 三个 requirement 与实现映射：

### 关系表初始化按实际关系表存在性生成
- 入口：`_build_relational_init_specs` 保持现状（已正确）
- 集成测试：
  - `tests/jmx_skeleton_generator/test_generators.py::TestGenerateDDLSetupThreadGroup::test_rel_init_specs_empty_emits_no_loop_controller`
  - `tests/jmx_skeleton_generator/test_generators.py::TestGenerateDDLSetupThreadGroup::test_rel_init_specs_produces_rel_subtree`
  - `tests/jmx_skeleton_generator/test_generators.py::TestGenerateDDLSetupThreadGroup::test_rel_init_specs_appended_after_ddl`
  - `tests/jmx_skeleton_generator/test_assembler.py::TestJMXSkeletonGenerator::test_rel_init_specs_appears_in_jmx`
  - `tests/jmx_skeleton_generator/test_assembler.py::TestJMXSkeletonGenerator::test_empty_rel_init_specs_emits_no_rel_subtree`
  - `tests/jmx_skeleton_generator/test_assembler.py::TestJMXSkeletonGenerator::test_rel_init_loop_count_matches_spec`
  - `tests/kwjdbc_svt/test_main.py::TestEndToEnd::test_ts_only_model_does_not_emit_rel_init`
  - `tests/kwjdbc_svt/test_main.py::TestEndToEnd::test_rel_model_emits_loop_controller_per_table`
- 原始 spec/design 增补：spec §2.0/§2.2/§写入范围说明；design §1 决策 3/§3.6/线程组编排节

### 纯时序稀疏宽表支持 NULL PreparedStatement 绑定
- 实现：`src/jmx_skeleton_generator/generators/write_groups.py:585` `pstmt.setObject(colIdx+1, null)` 替代 `setNull(idx, java.sql.Types.NULL)`
- 单元测试：
  - `tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py::TestBatchPreparedSamplerScriptStructure::test_null_uses_set_object`
  - `tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py::TestBatchPreparedSamplerScriptStructure::test_does_not_call_set_object_for_non_null_values`

### 超长 Prepared SQL 可被 Groovy 编译
- 实现：`src/jmx_skeleton_generator/generators/write_groups.py` `_build_batch_prepared_sampler_body` 把 `insert_sql` 按 16KB 切片为多个 Groovy 字符串常量并 `[..].join('')`
- 单元测试：`test_batch_prepared_typed_binding.py::test_large_insert_sql_is_split_into_safe_literals`（4000 列 varchar(2000) 验证最大行 < 60KB）

## Smoke 证据

### 稀疏 4000 列 99% NULL fixture（test_model_shig_sparse.yaml + test_cfg_shig_sparse.yaml）
- JMX 加载：pass
- DDL Setup：pass
- SharedMemory Setup：pass
- Write sampler：603 samples / 0 errors（5 分 1 秒）
- 写入行数：600
- NULL 种子比例：
  - col_smallint_1: 99/100 = 99.00%
  - col_int_1: 99/100 = 99.00%
  - col_float4_1: 99/100 = 99.00%
- DB 非 NULL 行数符合随机分布（5/600, 7/600, 6/600）

### 原 shig canonical smoke
- 必须在 `/tmp/jmeter-shig-canonical-verify/` 输出目录运行（`seed_dir` 是相对路径，JMeter UDV 不会自动写绝对路径）
- 184 samples / 0 errors（11 秒）
- 填行数：sub_company=4, factory=20, workshop=100, t_cnc=3900, t_electmeter=3900
- FK 完整性：workshop_orphans=0

## 全量测试

`venv/bin/python -m pytest tests/ -q` → 643 passed（之前 635 +8 个新测试）

## 提交链路

| commit | 说明 |
|---|---|
| c14969f | feat: conditional relational setup + sparse nullable + large SQL split |
| 9333117 | test: conditional relational setup integration coverage |
| 9694689 | docs: mark conditional-relational-setup #3 done in todolist and tasks |
| f8fc21b | chore: project-level build_command and verify_command for comet guard |

## WARNING（不属于本 DCR 引入的回归）

- shig canonical smoke 必须从 JMX 输出目录运行；仓库根目录运行会因为 `seed_dir` UDV 默认 fallback 到相对 `seeds/` 路径而失败。该行为在 DCR 之前的实现中已存在（属 Pre-Conditional-Relational-Setup 时代的运行前提），与本 DCR 无关；canonical 0-errors 验证在从输出目录运行时已确认。

## WARNING（与本 DCR 间接相关）

- shig canonical smoke 中 `factory=20, workshop=100` 已正常填行（与本 DCR 行为一致）。`LoopController.loops=1` 的限制是关系表 init 批次控制已存在事实，不在本 DCR 范围。
- `_build_rel_init_subtree` 之前被我改为 `loop_ctrl.append(inner)`，build 阶段测试通过，但 shig canonical smoke 暴露 JMeter XStream 解析器拒绝 `GenericController` 直接挂 `hashTree` 子节点。已回退为 sibling 关系 `[loop_ctrl, inner]`，shig canonical 184 samples / 0 errors 验证通过。Build 阶段测试不需要改（marker 仍命中）。

## 最终结论

无 CRITICAL 问题。无与本 DCR 直接相关的回归。所有 3 个 requirement 已实现、测试覆盖、smoke 通过。准备归档。
