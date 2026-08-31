# Tasks: write-batch-mode-semantics — 5 mode × batch_lines × dpt 统一

> **已合并 ptag-runtime-derived**：原 `ptag-runtime-derived` DCR（commit 1 `16a66a1` 落地，仅文档；tasks.md 未勾）已合并入本 DCR，目录已删除。ptag 第 1 列 runtime 派生 + SetupTG 双层 for + deviceIndex 与 device_start 绑定等核心规则全部归入本 DCR。

## Phase 1 — DCR artifacts + WriteConfig 校验扩 single_prepared（commit 1）

- [ ] 1.1 创建 `openspec/changes/write-batch-mode-semantics/` 5 件套（proposal.md / design.md / tasks.md / specs/write-batch-mode-semantics/spec.md / .openspec.yaml）
- [ ] 1.2 主 spec `docs/specs/kwdb-svt-test-plan-generator-spec.md` §2.0 L130-149 字段表调整 5 行（mode 业务语义 / batch_lines / device_per_thread / ms_step / col_tag_bind_mode）
- [ ] 1.3 主 spec §2.2 L320-340 吞吐量定义更新落库行数公式 + sampler 内 for 循环 dpt 描述
- [ ] 1.4 `src/config_parser/models.py::WriteConfig.check_single_insert_batch_lines`（`line 381-389`）改名为 `check_single_modes_batch_lines_one`，覆盖 `single_insert ∪ single_prepared`
- [ ] 1.5 新增 pytest `tests/config_parser/test_write_config.py` 4 case：`single_prepared + batch_lines=1` OK、`single_prepared + batch_lines>1` ValueError、`single_insert + batch_lines=1` 兼容、`batch_* + batch_lines>1` 兼容

## Phase 2 — SetupTG bind sampler 烤齐 numThreads × devicePerThread 个 entry（commit 2）

- [ ] 2.1 `src/jmx_skeleton_generator/generators/shared_memory_setup.py::_build_bind_sampler_groovy`（`line 106-297`）：单层 `for (int t = 0; t < numThreads; t++)`（`line 232`）改双层 `for (int t = 0; t < numThreads; t++) { for (int b = 0; b < devicePerThread; b++) { ... } }`
- [ ] 2.2 双层 for 内 `deviceIndex = deviceStart + b`，`deviceCode = "${t}_${deviceIndex}"`（内联 GString 拼接），烤到 `__SHARED_MEM_{db}_{table}_bind[deviceCode]`（与 D-25 一致：每 device 烤 batchLines 行）
- [ ] 2.3 `tests/jmx_skeleton_generator/test_setup_bind_sampler.py`：更新 4 case 期望 `numThreads × dpt` 个 group；新增 `test_bind_sampler_emits_per_device_index` 验 deviceIndex 格式
- [ ] 2.4 `tests/kwjdbc_svt/test_main_col_bind.py` 期望值同步：`__SHARED_MEM_*_bind` size 从 2 改 4（dpt=2 fixture）
- [ ] 2.5 pytest 全量不 regress：`source .venv/bin/activate && python -m pytest tests/`

## Phase 3 — _build_inline_sql_preprocessor_script 加 dpt for 循环 + bind 分支 ts 递增（commit 3）

- [ ] 3.1 `src/jmx_skeleton_generator/generators/write_groups.py::_build_inline_sql_preprocessor_script`（`line 50-310`）主路径：`INSERT SQL` 外层套 `for (int d = deviceStart; d < deviceStart + devicePerThread; d++)`，每 cycle 用内联 GString `"${threadNum}_${d}"` 派生第一 ptag，循环内 rows 段写 batch_lines 行
- [ ] 3.2 主路径 ts 列按 **`msStep`** 间隔（**整步语义**，非 `msStep / max(1, batchLines)` 分摊语义）递增生成 batchLines 个（gap #5 + **gap #6** 部分修复 — 非 bind）
- [ ] 3.3 bind 分支（`line 124-209`）：同 3.1 + 3.2；INSERT VALUES 内 ts 段按 **`msStep`** 间隔递增生成 batchLines 个（gap #5 + **gap #6** 部分修复 — bind）
- [ ] 3.4 `tests/jmx_skeleton_generator/test_inline_sql_preprocessor.py` 新增 4 case：dpt=1/2 × batch_lines=1/>1 × bind=false/true
- [ ] 3.5 pytest 全量不 regress

## Phase 4 — _build_batch_prepared_*_preprocessor_body 加 dpt for 循环（commit 4）

- [ ] 4.1 `src/jmx_skeleton_generator/generators/write_groups.py::_build_batch_prepared_preprocessor_body`（`line 704-820`）：外层 `for (int d = deviceStart; d < deviceStart + devicePerThread; d++)`；每 cycle `addBatch × batchLines` → `executeBatch`（dpt 次/cycle 共享 1 throughput tick）
- [ ] 4.2 `_build_batch_prepared_bind_preprocessor_body`（`line 556-701`）：外层 `for (int d = deviceStart; d < deviceStart + devicePerThread; d++)`；每 cycle 查 `bindGroups["${t}_${d}"]`，写 batch_lines 行
- [ ] 4.3 ts 列按 **`msStep`** 间隔（**整步语义**，修复 D-24 分摊语义 bug）递增生成 batchLines 个（gap #5 + **gap #6** 修复）
- [ ] 4.4 `tests/jmx_skeleton_generator/test_batch_prepared_bind.py` 新增 3 case：dpt=1/2 × bind=true/false
- [ ] 4.5 pytest 全量不 regress

## Phase 5 — _build_rest_write_preprocessor_script 加 dpt for + bind tag_set 补 regular_tag（commit 5）

- [ ] 5.1 `src/jmx_skeleton_generator/generators/rest_write_groups.py::_build_rest_write_preprocessor_script`（`line 129-355`）bind 分支（`line 184-258`）：外层 `for (int d = deviceStart; d < deviceStart + devicePerThread; d++)`；deviceCode = `"${t}_${d}"`；ts 列按 **`msStep`** 整步语义递增（修复 gap #6，line 253 改 `+ b * msStep`）
- [ ] 5.2 bind 分支 tag_set = 所有 ptag + regular_tag（gap #2 修复；非 bind 分支已全填，对齐）
- [ ] 5.3 schemaless 主路径（`line 275-355`）：外层 `for (int d = deviceStart; d < deviceStart + devicePerThread; d++)`；deviceCode = `"${t}_${d}"`；ts 列按 **`msStep`** 整步语义递增（修复 gap #6，line 330-339 改 `+ b * msStep`）
- [ ] 5.4 `tests/jmx_skeleton_generator/test_rest_write_bind.py` 新增 4 case：dpt=1/2 × bind=true/false × regular_tag present/absent
- [ ] 5.5 pytest 全量不 regress

## Phase 6 — generate_write_thread_groups 让三 mode 走 bind 分支（commit 6）

- [ ] 6.1 `src/jmx_skeleton_generator/generators/write_groups.py::generate_write_thread_groups`（`line 957-1201`）：`single_insert` / `batch_insert` 在 `bind_mode=True` 时给 `_build_inline_sql_preprocessor_script` 传 `col_tag_bind_mode=True`（gap #3 修复）
- [ ] 6.2 `single_prepared` 在 `bind_mode=True` 时调用 `_build_batch_prepared_bind_preprocessor_body`（gap #3 修复；首次生成 prep body）
- [ ] 6.3 `single_prepared` + `bind_mode=True` + `batch_lines>1` → ValueError（schema R-PAR-016 兜底）
- [ ] 6.4 `tests/jmx_skeleton_generator/test_write_thread_groups.py` 新增 6 case：3 mode × bind=false/true × batch_lines=1/>1
- [ ] 6.5 pytest 全量不 regress

## Phase 7 — fixture + pytest 集成 + smoke 真集群（commit 7）

- [ ] 7.1 `tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml`：device_per_thread=2 现状暴露 gap #1，**不改 fixture**，验证 commit 2 修复后能正常生成
- [ ] 7.2 `tests/kwjdbc_svt/fixtures/test_cfg_*.yaml`：新增 1 case 覆盖 `single_insert + bind=true + dpt=2 + batch_lines=1`（gap #3 集成验）
- [ ] 7.3 `tests/kwjdbc_svt/test_main.py` 新增 8 case：5 mode × bind=false/true 关键场景
- [ ] 7.4 pytest 全量：`source .venv/bin/activate && python -m pytest tests/` 期望 ≥ 691 passed
- [ ] 7.5 kwjdbc-jmx-smoke 真集群 5min：fixture 选 `test_model_col_bind.yaml` + `test_cfg.yaml` 跑 `batch_insert + dpt=2 + bind=true`：
  - 容器：`docker rm -f kaiwudb-smoke && docker run -d --name kaiwudb-smoke -p 26257:26257 -p 8081:8080 --ulimit nofile=65536 --privileged kaiwudb-x86_64-ent-0824dev30:3.3.0 tail -f /dev/null`
  - 启动：`docker exec kaiwudb-smoke /kaiwudb/bin/kwbase start-single-node --insecure --background`
  - 生成：`python -m kwjdbc_svt.main tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml tests/kwjdbc_svt/fixtures/test_cfg.yaml -o /tmp/col-bind-out`
  - 跑 jmeter：`timeout 320 jmeter -n -t test_plan.jmx -Jtest_duration=300 -Jnum_threads=2 -Jdevice_per_thread=2 -Jwrite_throughput=60 -Jbatch_lines=10`
  - 断言：`docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --insecure -e "select count(*) as rows, count(distinct ptag_varchar_1) as distinct_devices from iot_monitor.meters"`
- [ ] 7.6 断言：`rows ≈ throughput × test_duration × numThreads × batchLines × dpt / 60`（误差 ±10%）；`distinct_devices = numThreads × dpt = 4`；B1 body code:0 100%。**业务意图校验**：`write_throughput=60/min + batch_lines=10 + ms_step=1000ms` → 每设备入库速率 = `60 × 10 / 60 = 10 行/秒/设备`（= 业务意图"每设备每秒钟入库 10 行"）
- [ ] 7.7 反退化断言：B1 body-code + rows_per_sec_cluster 偏差 + distinct ptag + NOT NULL 列 + bind tag_set

## Phase 8 — archive（commit 8，文档归档）

- [ ] 8.1 7 代码 commit + 1 docs 归档 commit（顺序敏感，按 Phase 1-7 顺序提交）
- [ ] 8.2 `openspec/changes/write-batch-mode-semantics/.openspec.yaml` 加 `archived: YYYY-MM-DD` 字段（archive 时填）
- [ ] 8.3 `openspec-verify-change` 通过
- [ ] 8.4 `openspec-archive-change` 归档到 `openspec/changes/archive/`
- [ ] 8.5 `todolist.md` 新增 write-batch-mode-semantics 段落（commit 数 + 5 gap 修复 + smoke 落库行数验）
- [ ] 8.6 主 spec sync-specs：把本 DCR spec delta 合并到主 spec §2.0 + §2.2（替换原 `ptag #1 runtime 派生` 段对已删 `ptag-runtime-derived` DCR 的引用）
- [ ] 8.7 push `feat/write-batch-mode-semantics` 分支