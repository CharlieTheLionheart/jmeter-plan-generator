---
change: conditional-relational-setup
design-doc: docs/superpowers/specs/2026-07-22-conditional-relational-setup-design.md
base-ref: c14969f381451543b214335957bef283823d9d84
---

# 实施计划 — 条件关系表初始化

## 目标

在 OpenSpec change `conditional-relational-setup` 范围内，补齐条件关系表初始化的 JMX 集成测试，并完成 build 阶段验收。

## 任务

### 1. 条件关系初始化集成测试

- 1.1 在 `tests/jmx_skeleton_generator/test_generators.py::TestGenerateDDLSetupThreadGroup` 增加：
  - `test_rel_init_specs_empty_emits_no_loop_controller`
  - `test_rel_init_specs_produces_rel_subtree`
  - `test_rel_init_specs_appended_after_ddl`
- 1.2 在 `tests/jmx_skeleton_generator/test_assembler.py::TestJMXSkeletonGenerator` 增加：
  - `test_rel_init_specs_appears_in_jmx`
  - `test_empty_rel_init_specs_emits_no_rel_subtree`
  - `test_rel_init_loop_count_matches_spec`
- 1.3 在 `tests/kwjdbc_svt/test_main.py::TestEndToEnd` 增加：
  - `test_ts_only_model_does_not_emit_rel_init`
  - `test_rel_model_emits_loop_controller_per_table`

### 2. 验证

- 2.1 跑新增单元测试，全部通过。
- 2.2 跑全量 `python -m pytest tests/`，通过。
- 2.3 跑 5 分钟 sparse smoke（不强制每次；本计划确认历史证据仍有效）。
- 2.4 跑 shig canonical smoke（从 `/tmp/jmeter-shig-canonical` 输出目录运行）。

### 3. tasks.md 勾选与提交

- 3.1 勾选 `tasks.md` 中 §2 全部子任务。
- 3.2 追加本计划提交：`test: conditional relational setup integration coverage`。
- 3.3 跑 `comet-guard build --apply` 推进到 verify。

## 风险

- 新增断言依赖 JMX XML 序列化属性顺序；用字符串 marker 锁住而非 DOM 结构。
- 端到端 `_run_pipeline` 测试需要真实 KWDDB 连接，仅做 CLI 解析层面的检查，避免在 CI 中拉起容器。
