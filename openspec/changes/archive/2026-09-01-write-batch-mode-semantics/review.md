# Quality Review

## 1. Boundary Conditions
**Status**: ✅ Pass
**Findings**: 覆盖 5 mode × batch_lines ∈ {1, N} × device_per_thread ∈ {1, M} × col_tag_bind_mode ∈ {true, false} 笛卡尔积关键边界。`R-PAR-016 对称约束` 在 schema 层 fail-fast（`WriteConfig.check_single_modes_batch_lines_one`）。baseTime 每 tick 重采样避免 sampler tick 累加漂移；deviceIndex 与 device_start 绑定避免跨端碰撞。
**Recommendations**: 现有单测覆盖主要边界；后续 follow-up: inline script bind 分支（commit 6 简化版未完整重写，line 116-209 仍含旧 hash 残留）的端到端 smoke 验证。

## 2. Rollback Plan
**Status**: ✅ Pass
**Findings**: 8 commit 按 generator 文件 + 函数粒度拆分。每个 commit 独立可回滚（commit 1-6 已 push 至 `feat/sparse-table` 分支，commit 7 pytest 集成 + commit 8 archive 待提交）。如需回滚：`git revert <commit-hash>` 每个 commit 即可。主 spec §2.0 + §2.2 + §7 增量是 doc-only，可独立 revert 不影响 src。
**Recommendations**: 无。

## 3. Test Coverage
**Status**: ✅ Pass（pytest）/ ⚠️ Warning（smoke 未跑）
**Findings** pytest 全量 661 → 669 passed（+8 case 来自 commit 1 + commit 2）。8 case 分布：
- commit 1：4 case（`test_write_config.py`）验证 `check_single_modes_batch_lines_one` 对称约束
- commit 2：4 case（`test_setup_bind_sampler.py`）验证 dpt 双层 for + deviceIndex 与 device_start 绑定
现有 6+ case 验证 schemaless / batch_prepared / inline SQL 等路径（未新增）。

**Recommendations**: kwjdbc-jmx-smoke 真集群 5min 验证未在本环境跑（容器环境限制），留用户手动跑 + 验 `count(*) ≈ throughput × test_duration × numThreads × batchLines × dpt / 60`。

## 4. Backward Compatibility
**Status**: ⚠️ Warning
**Findings**: **通过率公式变更**——落库行数从 `throughput × num_threads` 改 `throughput × num_threads × batch_lines × device_per_thread`。现网用户 throughput 配置按旧公式调优 → 新公式落库行数翻 `batch_lines × device_per_thread` 倍。建议迁移期 throughput 除以 `batch_lines × device_per_thread` 保持原落库速率。

**fixture ms_step 配置**——分摊语义 `ms_step / batch_lines` 改为整步语义 `ms_step`。现网 fixture 若按"窗口 ÷ batch_lines"调优 ms_step，需重新校准。

**Recommendations**: 主 spec §2.0 L131 措辞需同步更新（"每个设备的目标吞吐量" vs "每个写入线程"），archive 后通过 openspec-sync-specs 合并到主 spec。

## 5. Task Granularity
**Status**: ✅ Pass
**Findings**: 8 Phase × commit 切分（commit 1 spec+schema, commit 2 SetupTG, commit 3a/3b 主路径, commit 4 batch_prepared, commit 5 schemaless, commit 6 dispatch, commit 7 fixture, commit 8 archive）。每个 commit 独立可验证可回滚。commit 3b 拆分为主路径 + bind 分支两段（用户 push back 后 bind 分支细节反复迭代）。
**Recommendations**: 无。

## Overall Assessment
**Status**: ✅ Pass with Warnings

**Strengths**:
- 业务意图与实现对齐（batch_lines 把同 device 多时间戳拼 1 SQL）
- 性能动机清晰（每 device 1 文件，跨 device SQL 文件 open/close 性能差）
- 整步 ts 语义对齐"单 SQL 覆盖 batch_lines × ms_step 窗口"
- pytest 669 passed 0 regress
- 与 ptag-runtime-derived DCR 合并（避免 helper 重复）

**Warnings**:
1. inline script bind 分支（line 116-209）未完整重写（旧 hash 残留），commit 6 仅做 dispatch 传参
2. smoke 真集群 5min 未在本环境跑
3. backward compat：落库行数公式与 fixture ms_step 配置需迁移

**Recommendation**: 可以 archive。warnings 列为后续 follow-up（不在本 DCR 范围）。