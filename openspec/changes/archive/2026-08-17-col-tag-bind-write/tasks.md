# Tasks: col-tag-bind-write

> **Plan 索引**：[docs/superpowers/plans/2026-08-05-col-tag-bind-write.md](docs/superpowers/plans/2026-08-05-col-tag-bind-write.md)
> **Design 索引**：[docs/superpowers/specs/2026-08-05-col-tag-bind-write-design.md](docs/superpowers/specs/2026-08-05-col-tag-bind-write-design.md)
> **节奏**：每阶段 1 commit，commit 前 pytest 全绿，commit 后跑 smoke 一次。
> **commit hash 占位**：落地后回填（`commit_N_pending` → 真实 hash）。

## §1. 配置 schema（每表独立）— Plan §阶段 1 → commit 1

- [x] 1.1 在 `WriteConfig`（[src/config_parser/models.py:344](src/config_parser/models.py#L344)）新增字段：
  - `col_tag_bind_mode: bool = False`
  - `col_num_per_tag: int = 0`
- [x] 1.2 Pydantic `model_validator(mode="after")`：
  - `col_tag_bind_mode=true` 时 `col_num_per_tag > 0`，否则 `ValueError("col_num_per_tag must be > 0 when col_tag_bind_mode=true; got {value}")`
  - **5 种 mode 全允许**（含 `schemaless`），无 mode 限制
- [x] 1.3 新增 `tests/config_parser/test_col_tag_bind_config.py`（6 case）：
  - `test_default_mode_false_and_zero_per_tag`
  - `test_explicit_false_accepted`
  - `test_true_with_positive_per_tag_accepted`
  - `test_true_with_zero_per_tag_rejected`
  - `test_true_with_negative_per_tag_rejected`
  - `test_all_five_modes_accepted_when_bind_enabled`
- [x] **verification**: `pytest tests/config_parser/test_col_tag_bind_config.py -v` → 6 pass；`pytest tests/config_parser/` → 0 regress
- [x] **commit 1**: `commit_1_pending` → `feat(col-tag-bind-write): per-table col_tag_bind_mode + col_num_per_tag in WriteConfig`

## §2. Orchestrator 跳过行种子文件生成 — Plan §阶段 2 → commit 2

- [x] 2.1 修改 `src/seed_data_generator/orchestrator.py::_generate_table_seeds`：
  - 新增关键字参数 `skip_row_aggregate: bool = False`
  - `True` 时跳过 `build_row_aggregate` + `write_row_aggregate` + `generated.append(aggregate_path)`
  - 列种子文件**照常生成**（不依赖 `skip_row_aggregate`）
- [x] 2.2 `generate_seeds` 顶层循环增加查 `test_cfg.write_configs` + 设 `skip_row_aggregate=True` 当 `col_tag_bind_mode=True`
- [x] 2.3 新增工具函数 `_find_write_config_for_table(test_cfg, db_name, table_name) -> Optional[WriteConfig]`（放 `src/kwjdbc_svt/main.py`）
- [x] 2.4 新增 `tests/seed_data_generator/test_orchestrator_col_bind.py`（4 case）：
  - `test_skip_row_aggregate_skips_aggregate_csv`
  - `test_skip_row_aggregate_keeps_column_seeds`
  - `test_default_skip_false_keeps_aggregate`
  - `test_mixed_table_skip_only_for_bind`
- [x] **verification**: `pytest tests/seed_data_generator/test_orchestrator_col_bind.py -v` → 4 pass；`pytest tests/seed_data_generator/` → 0 regress
- [x] **commit 2**: `commit_2_pending` → `feat(orchestrator): skip row aggregate generation when col_tag_bind_mode=true`

## §3. SetupTG 追加 Bind sampler — Plan §阶段 3（合并原 §3 + §4）→ commit 3

> **修订 (2026-08-05)**：原 §3 "SetupTG 现有 sampler if 分支" 在 commit 2 fix 已于 main.py 装配层 `seed_csv_paths` 过滤实现（物理等价），删除原 §3 的 if 分支实现。原 §4 "追加 Bind sampler" 升位为新 §3。

- [x] 3.1 新增函数 `generate_bind_setup_thread_group(write_configs: List[WriteConfig], seed_root: Path | str, *, num_threads: int = 1, name: str = "Bind Setup") -> List`（放 `src/jmx_skeleton_generator/generators/shared_memory_setup.py`，与现有 `generate_shared_memory_setup_thread_group` 同文件更内聚；commit 3 实际落地位置）
  - 遍历 `write_configs`，过滤 `col_tag_bind_mode=True` 的表；无则返回 `[]`
  - 对每张 col_tag_bind 表生成 1 个 JSR223 Sampler 子节点（**Sampler 不是 PreProcessor**：SetupTG 无其他 sampler 时 PreProcessor 不触发，与 `SharedMemoryInitializer` 一致用 Sampler；Groovy 模板见 Design Doc §4.3）
  - 返回 `[SetupThreadGroup, hashTree]`，按现有 SetupTG 模式（num_threads=1, scheduler, duration=60, loops=1）
- [x] 3.2 Groovy Sampler 行为（每张 col_tag_bind 表一份）：
  - 读 `{seed_root}/{db}/{table}/*.csv` 列种子文件
  - 拼 `ptag_tuple`（commit 3 简化实现：`device_<rowIdx % 2 + 1>`，无 model 依赖；commit 4 write TG 侧接 device_start / device_per_thread 注入）
  - `group_id = Math.abs(ptagTuple.hashCode()) % numThreads`
  - 每组 `col_names` = 前 `col_num_per_tag` 列（按字母排序取前 N）；每组 `row_values` = `seed_num` 行循环填
  - 写 `props.__SHARED_MEM_{db}_{table}_bind`（通过 `JMeterUtils.getJMeterProperties().put`）
- [x] 3.3 skeleton.py 装配（`src/jmx_skeleton_generator/generators/skeleton.py`）：
  - 两条路径（schemaless + JDBC）都在 `generate_shared_memory_setup_thread_group` 之后追加 `generate_bind_setup_thread_group(...)` 调用
  - Bind sampler 写到**独立** SetupThreadGroup（与现有 SharedMemory SetupTG 并列）
  - 新增 `_write_num_threads()` helper（拿 `cfg.write_config[0].num_threads` 作为 Groovy 注入的 hash mod base）
- [x] 3.4 新增 `tests/jmx_skeleton_generator/test_setup_bind_sampler.py`（**4 case**）：
  - `test_bind_sampler_emits_per_bind_table`：2 张 col_tag_bind 表 → 2 个 Bind Sampler + 2 个 `_bind` props key
  - `test_no_bind_sampler_when_all_full_row`：全行配置 → 返回 `[]`
  - `test_bind_sampler_preserves_mixed_table_setup`：mixed（bind + 全行）→ 只 bind 表有 `_bind` key
  - `test_bind_sampler_writes_hash_grouped_groups`：断言 Groovy 脚本含 `hashCode()` + `% numThreads` 模式
- [x] 3.5 **反退化 §8.7**：`tests/jmx_skeleton_generator/test_hash_distribution.py::test_hash_distribution_no_degeneracy`
  - 16 个不同 ptag tuple（4 device × 4 tag 笛卡尔积）+ parametrize `num_threads ∈ {1, 2, 4, 8}` → **4 case**（pytest 把每个 parametrize 值当独立 case）
  - `num_threads=1` 断言唯一 group_id；`num_threads≥2` 断言至少 2 个不同 `group_id`
- [x] **verification**: `pytest tests/jmx_skeleton_generator/test_setup_bind_sampler.py tests/jmx_skeleton_generator/test_hash_distribution.py -v` → 全 pass；`pytest tests/jmx_skeleton_generator/` → 0 regress
- [x] **commit 3**: `commit_3_done` (90f7dee + 6455cab + c078431) → `feat(setup-tg): append bind sampler for col_tag_bind tables`

## §4. 写入 TG 列子集选择（_build_inline_sql_preprocessor_script）— Plan §阶段 4 → commit 4

- [x] 5.1 `_build_inline_sql_preprocessor_script` 扩展入参（仅关键字参数）：
  - `col_tag_bind_mode: bool = False`
  - `col_num_per_tag: int = 0`
  - `num_threads: int = 1`
  - `not_null_data_cols: Optional[List[str]] = None`
- [x] 5.2 `col_tag_bind_mode=False`：行为零改动（全行 INSERT，回归测试保证）
- [x] 5.3 `col_tag_bind_mode=True` Groovy 分支：
  - `rows_key = f"__SHARED_MEM_{db}_{table}_bind"`
  - `group_id = Math.abs(ptagValues.hashCode()) % numThreads`
  - 取 `groups[group_id].col_names` + `row_values[random]`
  - INSERT 列名 = LinkedHashSet：ts + ptagNames + colNames + notNullDataCols（保序去重）
  - INSERT 值 = `[ts_fmt] + ptag_runtime_values + row_values_subset` + NULL 兜底
  - deviceIdentifier(calculateDeviceNumber(...)) 与 SetupTG bind sampler 对齐 hash 分组
  - empty groups / no group → `SELECT 1`（safe SQL 不让 JDBC sampler syntax error）
- [x] 5.4 NOT NULL 列强制列入（spec 约束）：LinkedHashSet 保序去重 + caller 负责保证 NOT NULL col 列入每组 subset（fallback NULL 是 dead code）
- [x] 5.5 新增 `tests/jmx_skeleton_generator/test_inline_sql_bind.py`（5 case）：
  - `test_bind_mode_emits_subset_columns`
  - `test_bind_mode_emits_correct_group_id_lookup`
  - `test_bind_mode_includes_not_null_data_cols`
  - `test_bind_mode_no_group_returns_safe_default`
  - `test_default_mode_unchanged`（回归）
- [x] **verification**: `pytest tests/jmx_skeleton_generator/test_inline_sql_bind.py -v` → 5 pass；`pytest tests/jmx_skeleton_generator/` → 0 regress
- [x] **commit 4**: `commit_4_done` (801ed46) → `feat(write-tg): _build_inline_sql_preprocessor_script col_tag_bind_mode branch`

## §5. schemaless 路径集成 — Plan §阶段 5 → commit 5

> **修订 (2026-08-10)**：原 6.1 描述 `write_configs: Optional[Dict[str, WriteConfig]]` 不准确——
> 实际是 `Optional[List[WriteConfig]]`，函数内索引为 `{db}.{table}`。`Dict` 描述未实现。

- [x] 6.1 修改 `src/jmx_skeleton_generator/generators/rest_write_groups.py::generate_rest_write_thread_group`：
  - 扩展入参 `write_configs: Optional[List[WriteConfig]] = None`
- [x] 6.2 对每张 col_tag_bind 表，Groovy PreProcessor 改为读 `__SHARED_MEM_{db}_{table}_bind`
- [x] 6.3 按 group_id 取子集列名 + 值，**只填 InfluxDB Line `field_set` 部分**；`tag_set` 部分仍按所有 ptag + regular_tag 填
- [x] 6.4 InfluxDB Line body 构造保持一致（`buildLine` 复用，零改动）
- [x] 6.5 新增 `tests/jmx_skeleton_generator/test_rest_write_bind.py`（4 case）：
  - `test_bind_mode_emits_subset_fields_in_line`
  - `test_bind_mode_keeps_all_tags_in_line`
  - `test_default_mode_unchanged`（回归）
  - `test_bind_mode_no_group_returns_safe_default`
- [x] **verification**: `pytest tests/jmx_skeleton_generator/test_rest_write_bind.py -v` → 4 pass；`pytest tests/jmx_skeleton_generator/` → 0 regress
- [x] **commit 5**: `commit_5_done` (389dc56) → `feat(rest-write): schemaless mode col_tag_bind branch (InfluxDB Line subset fields)`
- [x] **commit 5 fix**: `commit_5_fix_done` (76cb16a) → `fix(col-tag-bind-write): commit 5 wiring fix — write_configs routing`
  - 补 generate_rest_write_thread_group write_configs 入参 + write_cfg_by_table 索引 + 4 参数透传
  - device_per_thread 从 UDV props.get 改为生成时 bake（与 SetupTG bind sampler 对齐 hash 分组）
  - **未触及 skeleton.py 调用点**：那是 commit 6 范围，本次仅修函数签名 + 默认 None
- [x] **commit 5 fix-2**: `commit_5_fix_2_done` (4e3791c) → `fix(col-tag-bind-write): commit 5 fix-2 — simplify wiring + doc baked 语义`
  - 修 review m1: `int(write_cfg_by_table.get(fqn, wc).num_threads)` 冗余 → `int(wc.num_threads)`（与 3 行对齐）
  - 修 review m2: docstring 补一句明示 bind-mode 下 num_threads / device_per_thread baked（UDV 不 override）
  - **M1 测试缺口 + M2 Plan/Design drift** 推迟到 commit 6 一并修

## §6. main 入口校验 + 端到端 fixture + IT — Plan §阶段 6 → commit 6

> **修订 (2026-08-10)**：原 7.3 描述 `4000 data_cols` 改为 10 列（缩短 smoke 跑时；10 列已足够覆盖 bind mode 的子集列选取 + hash 分组验证）。
> 原 7.4 描述 `mode: batch_prepared` 改为 `mode: schemaless`（commit 6 wiring 主要面向 schemaless 路径，与 commit 5 落地一致）。
> `test_model_col_bind.yaml` 第 2 张表从"备用 mixed 场景"改为必须配 `iot_monitor.t_full`（与 cfg 对应）。

- [x] 7.1 `src/kwjdbc_svt/main.py` 顶层校验（生成 seed 文件前）：
  - `col_tag_bind_mode=true` 时 `col_num_per_tag ≤ data_col_count`，否则 `ValueError` 含 `{db}.{table}`
  - `col_tag_bind_mode=true` 时该表 ≥ 1 `primary_tag`（`TsTableConfig.primary_tag_count ≥ 1`）
  - `map_exception_to_exit_code` 把 `ValueError` 映射到 `EXIT_VALIDATION=1`（之前只 map 了 `ConfigParserError`）
- [x] 7.2 main 入口装配 `write_cfg_by_table` 传给 Orchestrator + SetupTG 生成器 + 写入 TG 生成器
  - skeleton.py schemaless 路径 line 68: `generate_rest_write_thread_group(self.model, rest, write_configs=self.test_config.write_config)` 接通
- [x] 7.3 新增 `tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml`：
  - 2 张 sparse ts 表 `iot_monitor.meters` (10 data_cols + 1 ptag, bind) + `iot_monitor.t_full` (10 data_cols + 1 ptag, full-row)
- [x] 7.4 新增 `tests/kwjdbc_svt/fixtures/test_cfg_col_bind.yaml`：
  - `write_configs[0]: {tbl_name: iot_monitor.meters, mode: schemaless, col_tag_bind_mode: true, col_num_per_tag: 5}`
  - `write_configs[1]: {tbl_name: iot_monitor.t_full, mode: schemaless}` (mixed 场景)
- [x] 7.5 追加 4 case 到 `tests/kwjdbc_svt/test_main_col_bind.py`：
  - `test_end_to_end_col_bind_emits_subset_jmx` — wiring 断言（review M1 覆盖）
  - `test_mixed_table_end_to_end` — bind + full-row 共存 XML 断言
  - `test_main_validates_col_num_per_tag_exceeds_data_col_count` — ValueError → EXIT_VALIDATION
  - `test_main_validates_zero_primary_tag` — ValueError → EXIT_VALIDATION
- [x] **verification**: `pytest tests/kwjdbc_svt/test_main_col_bind.py -v` → 6 pass（2 commit 2 旧 + 4 新）；**`pytest tests/` → 739 passed，0 regress（baseline 735 + 4 新增）**
- [x] **commit 6**: `commit_6_done` → `feat(main): col_tag_bind_mode validation + write_configs routing + mixed-table fixture`
- [x] **同步 review M2**：Plan.md §3.1/§6.1 + Design Doc §4.5/§4.6/§4.6 5 处 `Dict[(db, table), WriteConfig]` → `List[WriteConfig]`（内部索引成 Dict），与 commit 5 fix (76cb16a) + commit 5 fix-2 (4e3791c) 一致

## §7. 文档 — Plan §阶段 7 → commit 7

- [x] 8.1 `docs/specs/kwdb-svt-test-plan-generator-spec.md`：
  - §131-136 增补 `col_tag_bind_mode` 段（每表独立 / 5 mode 适用 / NOT NULL 列入 / hash 分组语义）
  - 新增 requirement 段：`col_tag_bind_mode` 必须 ≥ 1 ptag，`col_num_per_tag` 校验范围
- [x] 8.2 `docs/refs/kaiwudb-schemaless-write-reference.md`：
  - 增补 § "col_tag_bind + schemaless" 段（InfluxDB Line `field_set` 子集语义）
- [x] 8.3 `todolist.md`：
  - "已完成"段压缩条目：DCR proposal (b9301c6) + Design Doc + Plan + 7 个 feat commit（待落地后回填 hash）
  - "遗留真问题"段删除
- [x] **verification**: 文档 diff 人工 review；`pytest tests/` → 仍 745 pass（739 + 6 D-9 新增）
- [x] **commit 7**: `commit_7_done` (3e65a37) → `docs(col-tag-bind-write): spec + reference + todolist update`

## §8. Smoke 验收 — Plan §阶段 8（commit 8 可选）

- [x] 9.1 起 `kaiwudb-smoke` 容器（已 TLS 重建 + root/root123）
- [x] 9.2 跑 sparse col_bind smoke：
  ```bash
  source .venv/bin/activate
  rm -rf /tmp/jmeter-col-bind-out && mkdir -p /tmp/jmeter-col-bind-out
  python -m kwjdbc_svt.main \
      tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml \
      tests/kwjdbc_svt/fixtures/test_cfg_col_bind.yaml \
      -o /tmp/jmeter-col-bind-out
  cd /tmp/jmeter-col-bind-out
  timeout 30 jmeter -n -t test_plan.jmx \
      -Jtest_duration=10 -Jnum_threads=4 -Jdevice_start=1 -Jdevice_per_thread=2 \
      -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
      -Jrest_api.hostname=127.0.0.1 -Jrest_api.http_port=8081 \
      -Jrest_api.ca_cert_path=$PWD/../tests/kwjdbc_svt/fixtures/ca.crt \
      -Jwrite_throughput=60 \
      -l /tmp/jmeter-col-bind.jtl -j /tmp/jmeter-col-bind.log 2>&1 | tail -5
  ```
- [x] 9.3 验证：
  - SetupTG 3/3 (Login + DDL-1 + DDL-2) + Write 10/10 + Query 1/1
  - `iot_monitor.meters` `count(*) = num_threads × device_per_thread × iterations = 4 × 2 × 5 = 40`
  - ptag 列 `device_id` 非 NULL
  - INSERT 列数 = `ts + 1 ptag + col_num_per_tag (5) = 7`（断言 JTL 中 `insert_sql` 列名部分）
- [x] 9.4 **反退化 §8.8**：JTL 中至少 2 个不同 `insert_sql` 列名片段（多个 ptag → 不同 group_id → 不同列子集）
- [x] 9.5 schemaless col_bind smoke 同 9.2-9.4，验证 InfluxDB Line `field_set` 子集语义
- [x] **verification**: Smoke v1 + v2 全绿；DB 行数 + 列数 + 反退化断言通过
- [x] **commit 8** (optional): `commit_8_pending` → `chore(smoke): col_tag_bind smoke v1 + v2 record`

## §10. 反退化测试加固（已并入 §4.6 + §9.4）

- [x] §8.7 单元测试：在 §4.6 已落地 `test_hash_distribution_no_degeneracy`
- [x] §8.8 冒烟测试：通过 §9.4 JTL 列名片段断言覆盖
- [x] 不再单独立 commit；与 commit 4 + commit 9 一起验证

---

## 全局验收（9 个 commit 全落 + smoke 全绿后）

- [x] 全量 `pytest tests/` 通过（baseline 701+ + 新增 ~25 case = ~726 pass）
- [x] sparse col_bind smoke：SetupTG 3/3 + Write 10/10 + Query 1/1，DB 行数 = 40
- [x] schemaless col_bind smoke：SetupTG 3/3 + Write 10/10 + Query 1/1
- [x] 反退化测试 §8.7（单元）+ §8.8（冒烟）通过
- [x] docs/specs/kwdb-svt-test-plan-generator-spec.md 已增补 §col_tag_bind_mode
- [x] docs/refs/kaiwudb-schemaless-write-reference.md 已增补 §col_tag_bind + schemaless
- [x] todolist.md 已更新 DCR 进度（8 commits 落 hash）
- [x] working tree clean，无遗留 fix
- [x] 分支 `col-tag-bind-write` 已 ahead origin 8 commits，未 push

## commit 节奏总览

| 阶段 | commit | 主题 | 验证 |
|------|--------|------|------|
| 1 | commit 1 | `feat(col-tag-bind-write): per-table col_tag_bind_mode + col_num_per_tag in WriteConfig` | 10 config_parser pytest pass |
| 2 | commit 2 | `feat(orchestrator): skip row aggregate generation when col_tag_bind_mode=true` + fix | 4 orchestrator + 2 main_col_bind IT pass |
| 3 | commit 3 | `feat(setup-tg): append bind sampler for col_tag_bind tables` | 3 setup_bind + 1 hash_distribution pytest pass |
| 4 | commit 4 | `feat(write-tg): _build_inline_sql_preprocessor_script col_tag_bind_mode branch` | 5 inline_sql_bind pytest pass |
| 5 | commit 5 | `feat(rest-write): schemaless mode col_tag_bind branch (InfluxDB Line subset fields)` | 4 rest_write_bind pytest pass |
| 6 | commit 6 | `feat(main): col_tag_bind_mode validation + write_configs routing + mixed-table fixture` | 4 main_col_bind pytest pass + 全量 736+ pass |
| 7 | commit 7 | `docs(col-tag-bind-write): spec + reference + todolist update` | 文档 review + pytest 仍 pass |
| 8 | commit 8 (optional) | `chore(smoke): col_tag_bind smoke v1 + v2 record` | smoke 全绿 + 反退化断言 |

> **修订 (2026-08-05)**：原节奏 9 个 commit 合并为 8 个。原 commit 3 "SetupTG if 分支" 已在 commit 2 fix 在 main.py 装配层实现（物理等价），删除。commit 3-8 顺位往前。
