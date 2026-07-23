# rest-schemaless-write — Quality Review

## 1. Boundary Conditions
**Status**: ✅ Pass
**Findings**：参考文档 `docs/refs/kaiwudb-schemaless-write-reference.md` §0 P0 范围表已显式划定协议 / 认证 / HTTPS / 模式边界；§9.4 三条边界澄清（primary_tag hash、限流、token 续期）均已给出处理策略。`pre_create_tables=true`（P0 默认）与 `pre_create_tables=false`（对照 fixture 复现无 ptag 场景）双路径覆盖。spec 6 条 Requirement 共 11 个 Scenario 命中关键边界（pre_create 开关、https_mode 切换、ca_cert_path 缺失 fail-fast、Query 不读黑盒列、mode 路由分流）。
**Recommendations**：build 阶段在 `test_http_request_sampler_element.py` 里加一组「`https_mode=tls` + `ca_cert_path` 缺失 → 抛 `RestConfigError`」的参数化用例；`test_ddl_setup_http_thread_group.py` 加一组「`pre_create_tables=false` → 不生成 DDL sampler」用例。

## 2. Rollback Plan
**Status**: ✅ Pass
**Findings**：design §「Migration Plan」明确列出回滚步骤（删除 4 个新增模块 + mode 路由分支 + 测试）。`DDLGenerator` 与现有 `setup_thread_group_element(...)` 零修改；JDBC 路径不受影响。`pre_create_tables=false` 是回滚的软路径（不引入新能力）。
**Recommendations**：合并 PR 时 squash；revert 单个 commit 即回滚整个 change。

## 3. Test Coverage
**Status**: ✅ Pass
**Findings**：spec 6 条 Requirement → 11 个 Scenario → 对应 11+ 个 pytest 用例。`tests/jmx_skeleton_generator/` 新增 4 个测试文件（`test_http_request_sampler_element.py` / `test_ddl_setup_http_thread_group.py` / `test_rest_write_groups.py` / `test_rest_query_groups.py`）+ `tests/kwjdbc_svt/` mode 路由用例。端到端走 `kwjdbc-jmx-smoke` skill。
**Recommendations**：build 阶段补一组对照 fixture（`pre_create_tables=false` 跑一次）作为 `tests/kwjdbc_svt/fixtures/test_model_schemaless_noptag.yaml`；smoke 跑两次（insecure + tls）覆盖 §9.3 行 #9。

## 4. Backward Compatibility
**Status**: ✅ Pass
**Findings**：mode 路由新增分支，不修改既有 `batch_prepared` / `single_insert` / `single_prepared` / `schemaless`（占位报错）的行为。`test_cfg.yaml` 新增 `rest_api` 段是 additive 改动；现有 fixture 不含该段时，mode ≠ `schemaless_influxdb`，生成器跳过校验。JDBC SetupTG 与 DDLGenerator 输出完全不动。
**Recommendations**：在 `tests/kwjdbc_svt/test_main_routes.py` 加一条「`mode: batch_prepared` + 无 `rest_api` 段 → 不报错」的回归用例，验证 additive 兼容。

## 5. Task Granularity
**Status**: ✅ Pass
**Findings**：tasks.md 待生成；按 design 决策拆分，预计 7-9 个 task，每 task 对应单一模块或单一测试组，单 PR 可独立 commit + smoke 通过。粒度匹配现有 change（参考 `ddl-generator` / `direct-insert-write` 任务规模）。
**Recommendations**：每个 task 配 commit hash + pytest 行数断言（参考 `ddl-generator` change 的 task 模板）；避免把 `http_request_sampler_element` + DDL pre-create + 写入 TG 装配合并到同一 task。

## Overall Assessment
**Status**: ✅ Pass

边界、回滚、测试、向后兼容、任务粒度五维均通过。P0 范围明确（仅 InfluxDB Line + Token 认证 + insecure / TLS 二选一 + DDL pre-create 默认 true + Query round-trip）；显式排除 Basic Auth / token 续期 / OpenTSDB（标 P1+ 或归功能测试）。3 条边界澄清（primary_tag hash、限流、token 续期）已与研发对齐并落入 design 决策与 risk。spec 与 design 一一对应，无悬空 Requirement。可进入 build 阶段。