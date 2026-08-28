# Tasks: ptag 第一列 runtime 派生 `{threadNum}_{deviceNum}` 格式

## Phase 1：DCR + 主 spec 关联（commit 1，仅文档）

- [ ] 1.1 在 `openspec/changes/ptag-runtime-derived/` 创建 proposal.md、design.md、tasks.md、specs/ptag-runtime-derived/spec.md、`.openspec.yaml`
- [ ] 1.2 主 spec `docs/specs/kwdb-svt-test-plan-generator-spec.md` §col_tag_bind_mode 段（line ~138）插入「ptag #1 runtime 派生约定」+ DCR 关联链接
- [ ] 1.3 同步删除 spec.md 中 Decision 4 `hash(ptag_tuple) mod num_threads` 文字（commit 同段落附说明已废）
- [ ] 1.4 `docs/designs/kwdb-svt-test-plan-generator-design.md` §4.3 bind path 段落同步清 hash 分组描述

## Phase 2：代码 + 测试（commit 2）

- [ ] 2.1 `src/utils/preprocessor_helpers.py`：新增 helper `ptag_runtime_value(thread_num, device_num) -> str` 返回 `{t}_{d}`；同段加 Groovy 等价 `def ptagRuntimeValue(long threadNum, int deviceNum)` 供 JSR223 嵌入
- [ ] 2.2 `src/jmx_skeleton_generator/generators/shared_memory_setup.py::BindSetup`：双层 for-loop（t + b），每 iter 用 ptagRuntimeValue 拼 deviceCode 并覆盖第一 ptag 值
- [ ] 2.3 `src/jmx_skeleton_generator/generators/shared_memory_setup.py`：删 `hash(ptagValues) % numThreads` group 计算；SharedMemory 按 deviceCode 字典直接 lookup（已部分实现，确认完全去 hash）
- [ ] 2.4 `src/jmx_skeleton_generator/generators/write_groups.py`：batch_prepared PreProcessor 改按 deviceIndex 外层循环；每 deviceIndex 写 batchLines 行；第一 ptag 用 ptagRuntimeValue
- [ ] 2.5 `src/jmx_skeleton_generator/generators/write_groups.py`：ThreadGroup LoopController.loops = numThreads × devicePerThread（同步 WriteTG 装配）
- [ ] 2.6 `src/direct_insert_write/preprocessor_generator.py`：第一 ptag 改 ptagRuntimeValue；device_per_thread 展开
- [ ] 2.7 `src/jmx_skeleton_generator/generators/rest_write_groups.py`：schemaless InfluxDB Line tag_set 第一列改 ptagRuntimeValue
- [ ] 2.8 `tests/jmx_skeleton_generator/test_setup_bind_sampler.py`：`test_bind_sampler_writes_per_device_groups`、`test_bind_subset_per_group_offset`、`test_bind_sampler_aligns_with_write_tg_device`、`test_bind_sampler_preserves_mixed_table_setup`、`test_bind_sampler_emits_per_bind_table` 更新期望值（`numThreads × dpt` key）+ 新增 case 验 `{threadNum}_{deviceNum}` 格式
- [ ] 2.9 `tests/jmx_skeleton_generator/test_setup_bind_sampler.py`：新增 `test_bind_ptag_first_runtime_value_format` 验 Groovy 中 `ptagRuntimeValue(0, 1) == "0_1"`、`ptagRuntimeValue(19, 25) == "19_25"`
- [ ] 2.10 `tests/jmx_skeleton_generator/test_inline_sql_bind.py`、`test_rest_write_bind.py`：更新 deviceCode 期望值与新格式
- [ ] 2.11 `tests/kwjdbc_svt/test_main.py` / `test_main_col_bind.py` / `test_main_routes_schemaless_influxdb.py`：现有 fixture 仍可解析（不依赖 val_range 删与否，本阶段不删 fixture 字段）；pytest 期望值同步改
- [ ] 2.12 `tests/utils/test_preprocessor_helpers.py`（如不存在则新建）：helper 单测
- [ ] 2.13 全量 pytest：`source .venv/bin/activate && python -m pytest tests/` 期望 ≥ 766 passed、新覆盖 ≥ 5 case

## Phase 3：fixture 字段清理（commit 3，必须在 smoke 前）

- [ ] 3.1 `tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml`：2 表各 1 ptag → 删 2 处 val_range + seed_num，保留 col_type + type_proportion
- [ ] 3.2 `tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml`：1 ptag → 删 1 处
- [ ] 3.3 `tests/kwjdbc_svt/fixtures/test_model_shig_sparse.yaml`：t_cnc 2 ptag → 只删第一个的 val_range + seed_num，第二个 enum 保留
- [ ] 3.4 `tests/kwjdbc_svt/fixtures/test_model_shig.yaml`：t_cnc 2 ptag 删第 1、t_electmeter 1 ptag → 共删 2 处；同步 review FK 链路（ptag_varchar_1 引用 / data_cols ref: 项），如 FK target 依赖 enum 格式需调整
- [ ] 3.5 `tests/kwjdbc_svt/fixtures/test_model_sparse_10k.yaml`：1 ptag → 删 1 处 val_range（保留历史注释）
- [ ] 3.6 5 fixture 全部重新生成 JMX + 跑 `pytest tests/` 不 regress

## Phase 4：真集群 5min smoke（commit 4）

- [ ] 4.1 容器：`docker rm -f kaiwudb-smoke && docker run -d --name kaiwudb-smoke -p 26257:26257 -p 8081:8080 --ulimit nofile=65536 --privileged 10.110.105.65:5000/svt_images/kaiwudb-x86_64-ent-0824dev30:3.3.0 tail -f /dev/null`
- [ ] 4.2 `docker exec kaiwudb-smoke /kaiwudb/bin/kwbase start-single-node --insecure --background` + 轮询 ready
- [ ] 4.3 `python -m kwjdbc_svt.main tests/kwjdbc_svt/fixtures/test_model_sparse_10k.yaml tests/kwjdbc_svt/fixtures/test_cfg_sparse_10k_jdbc.yaml -o /tmp/sparse-10k-jdbc-out` rc=0
- [ ] 4.4 5min jmeter：`timeout 320 jmeter -n -t test_plan.jmx -Jtest_duration=300 -Jnum_threads=20 -Jdevice_per_thread=25 -Jwrite_throughput=60 -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb`
- [ ] 4.5 断言：`docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --insecure -e "select count(*) as rows, count(distinct ptag_varchar_1) as distinct_devices, min(ptag_varchar_1) as first_dev, max(ptag_varchar_1) as last_dev from db_sparse_svt.t_meters"`
- [ ] 4.6 期望：`rows = 37220 ± 3722` × `batchLines=10`、`distinct_devices = 500`、`first_dev = "0_1"`、`last_dev = "19_25"`

## Phase 5：commit + push（按 4 commit 顺序）

- [ ] 5.1 commit 1：docs only（DCR + spec 关联）
- [ ] 5.2 commit 2：fix(col-tag-bind-ptag-derive): runtime 派生 + dpt 真生效 + 单测
- [ ] 5.3 commit 3：refactor(fixtures): 删 5 fixture 第一 ptag 的 val_range + seed_num
- [ ] 5.4 commit 4：test(col-tag-bind-ptag-derive): 真集群 5min smoke 500 deviceCode 验证
- [ ] 5.5 push `git push origin col-tag-bind-write`
- [ ] 5.6 更新 `todolist.md`：新一段「ptag-runtime-derived (4 commits + 5 fixture 清理)」
