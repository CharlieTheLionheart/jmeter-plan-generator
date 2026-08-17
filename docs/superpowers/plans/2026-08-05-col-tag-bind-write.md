---
comet_change: col-tag-bind-write
design-doc: docs/superpowers/specs/2026-08-05-col-tag-bind-write-design.md
base-ref: baf4c95217f1d0d3e43527e5853f9ab67863b082
role: technical-design
canonical_spec: openspec
---

# 实施计划 — col-tag-bind-write

## 目标

在 OpenSpec change `col-tag-bind-write` 范围内，实现"列-tag 绑定写入模式"：
- 每表独立 `col_tag_bind_mode` 配置（`write_config[].tbl_name` 项下）
- Orchestrator 跳过该表行种子文件生成（复用列种子文件）
- SetupTG 现有 sampler 加 `if` 分支 + 追加新 sampler 加载列种子 + hash 分组
- 写入 TG 列子集 INSERT（适用 5 种 mode 含 schemaless）
- 端到端 sparse 4000 列 + schemaless 双 smoke 通过，pytest 701+ 不 regress

## 文件结构

**新增**（4 工件）：

| 文件 | 职责 |
|------|------|
| `tests/config_parser/test_col_tag_bind_config.py` | WriteConfig 新字段 Pydantic 校验（合法/非法 case） |
| `tests/seed_data_generator/test_orchestrator_col_bind.py` | Orchestrator skip_row_aggregate 行为 |
| `tests/jmx_skeleton_generator/test_setup_bind_sampler.py` | SetupTG [A] if 分支 + [B] 新 sampler 装配 |
| `tests/jmx_skeleton_generator/test_inline_sql_bind.py` | `_build_inline_sql_preprocessor_script` 列绑定分支 Groovy 模板 |
| `tests/jmx_skeleton_generator/test_rest_write_bind.py` | `rest_write_groups.py` 列绑定分支 Groovy 模板 |
| `tests/jmx_skeleton_generator/test_hash_distribution.py` | hash(ptag_tuple) mod num_threads 多对一分布（反退化 §8.7） |
| `tests/kwjdbc_svt/test_main_col_bind.py` | main 入口端到端 col_tag_bind=true + mixed table（§8.4） |
| `tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml` | sparse 4000 列 col_tag_bind fixture |
| `tests/kwjdbc_svt/fixtures/test_cfg_col_bind.yaml` | sparse col_tag_bind 配置 fixture |

**修改**（5 工件）：

| 文件 | 改动 |
|------|------|
| `src/config_parser/models.py::WriteConfig` | 新增 `col_tag_bind_mode: bool = False` + `col_num_per_tag: int = 0` 字段；不动现有字段 |
| `src/seed_data_generator/orchestrator.py::_generate_table_seeds` | 新增 `skip_row_aggregate: bool = False` 参数；列种子照常生成，跳过最后 `build_row_aggregate` + `write_row_aggregate` |
| `src/jmx_skeleton_generator/generators/write_groups.py` | 现有 SetupTG sampler 加 if 分支（skip col_tag_bind 表的行种子加载）；新增 `generate_bind_setup_thread_group(seed_csv_paths, write_configs, num_threads)` 函数 |
| `src/jmx_skeleton_generator/generators/write_groups.py::_build_inline_sql_preprocessor_script` | 扩展入参 `col_tag_bind_mode` + `col_num_per_tag` + `num_threads`；列绑定分支拼子集列名 + 子集值 |
| `src/jmx_skeleton_generator/generators/rest_write_groups.py::generate_rest_write_thread_group` | 扩展入参 `write_configs`；列绑定分支 Groovy PreProcessor 读 `_bind` namespace，Inflow Line `field_set` 部分填子集列 |
| `src/kwjdbc_svt/main.py` | 顶层装配 `write_configs: List[WriteConfig]`（直接复用 `test_cfg.write_config`，内部按 `{db}.{table}` 索引成 `write_cfg_by_table`）；3 项 main 入口校验（col_num_per_tag > 0 / ≤ data_col_count / ≥1 ptag）；传给 Orchestrator + SetupTG 生成器 |

**复用，零改动**：

- `src/seed_data_generator/io.py::read_column_seed` / `write_column_seed` — 列种子 IO 不动
- `src/jmx_skeleton_generator/generators/shared_memory_setup.py` — 现有 SetupTG 行种子加载器逻辑，仅加 if 分支
- `src/ddl_generator/generator.py` — DDL 生成（DDL 仍是全列）
- `src/utils/xml_helpers.py` — 通用 XML 构造工具
- `src/utils/rest_errors.py` — TLS 校验（与本 DCR 无关）
- `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` — smoke 命令模板沿用；如新增 fixture 跑法，追加注释但不重写 skill

## 全局约束

- **零改动原则**：DDL 生成 / 列种子 IO / rest_errors / rest_query_groups 全部**不动一行**。所有复用只通过现有签名调用。
- **每表独立**：`col_tag_bind_mode` 字段在 `WriteConfig` 而非 `WriteConfig` 全局或 `TestModelConfig`；与其他表正交。
- **mode 正交**：列绑定是 mode 之上的能力，适用 5 种 mode 无任何 mode 限制。
- **混合表支持**：同一 test plan 中部分全行 + 部分列绑定**并行存在**（SetupTG 两个 sampler OR 关系）。
- **SharedMemory 命名区分**：列绑定表用 `__SHARED_MEM_{db}_{table}_bind`（独立 key），与全行 `__SHARED_MEM_{db}_{table}` 共存不冲突。
- **NOT NULL 列强制列入**：spec 约束，生成器层面把显式 `NOT NULL` 的 `data_col` 追加到子集列名末尾。
- **DDL 不变**：DDL 仍是全列；子集 INSERT 由 server 用 NULL 填充未填列。
- **hash 函数**：Decision 4 = `hash(ptag_tuple) mod num_threads`，**多对一**映射（避免 ptag 组合数远大于 num_threads 时的冗余）。
- **pytest baseline**：全量 pytest 701+ 不 regress。
- **smoke 验收**：sparse 4000 列 + schemaless 双 smoke 通过。

## 任务

### 阶段 1: 配置 schema（tasks §1）— commit 1

**文件**：修改 `src/config_parser/models.py`。

- 1.1 在 `WriteConfig`（[models.py:344](src/config_parser/models.py#L344)）新增字段：
  - `col_tag_bind_mode: bool = False`
  - `col_num_per_tag: int = 0`
- 1.2 不动现有字段；不动 `TableConfig` / `RelTableConfig` / `TsTableConfig`。
- 1.3 Pydantic 校验放在 `WriteConfig.model_validator(mode="after")`：
  - `col_tag_bind_mode=true` 时 `col_num_per_tag > 0`，否则 `ValueError("col_num_per_tag must be > 0 when col_tag_bind_mode=true; got {value}")`。
- 1.4 新增 `tests/config_parser/test_col_tag_bind_config.py` 覆盖：
  - `test_default_mode_false_and_zero_per_tag` — 默认值
  - `test_explicit_false_accepted` — 显式 false 合法
  - `test_true_with_positive_per_tag_accepted` — 合法 case
  - `test_true_with_zero_per_tag_rejected` — `col_num_per_tag=0` 拒绝
  - `test_true_with_negative_per_tag_rejected` — `col_num_per_tag=-1` 拒绝
  - `test_all_five_modes_accepted_when_bind_enabled` — 5 种 mode 全允许（含 schemaless）

**verification**:
- `python -m pytest tests/config_parser/test_col_tag_bind_config.py -v` → 6 个 case 全 pass
- `python -m pytest tests/config_parser/` → 全 pass（baseline 不 regress）
- **commit 1**: `feat(col-tag-bind-write): per-table col_tag_bind_mode + col_num_per_tag in WriteConfig`

### 阶段 2: Orchestrator 跳过行种子文件（tasks §2）— commit 2

**文件**：修改 `src/seed_data_generator/orchestrator.py::_generate_table_seeds` + `src/kwjdbc_svt/main.py`。

- 2.1 `_generate_table_seeds` 新增 `skip_row_aggregate: bool = False` 关键字参数（不改位置参数，避免现有调用者破坏）。
- 2.2 当 `skip_row_aggregate=True`：跳过 `header, rows = build_row_aggregate(...)` + `write_row_aggregate(aggregate_path, header, rows)` + `generated.append(aggregate_path)` 三步；列种子照常生成并 append。
- 2.3 `generate_seeds` 顶层循环增加：每个表先查 `test_cfg.write_configs` 找对应 `WriteConfig`，如有 `col_tag_bind_mode=True` 则 `skip_row_aggregate=True`。
- 2.4 新增工具函数 `_find_write_config_for_table(test_cfg, db_name, table_name) -> Optional[WriteConfig]`（放 `src/kwjdbc_svt/main.py`，与现有 `_build_relational_init_specs` 同级）。
- 2.5 新增 `tests/seed_data_generator/test_orchestrator_col_bind.py` 覆盖：
  - `test_skip_row_aggregate_skips_aggregate_csv` — `col_tag_bind_mode=true` → 无 `{db}/{table}.csv`
  - `test_skip_row_aggregate_keeps_column_seeds` — 列种子文件仍生成
  - `test_default_skip_false_keeps_aggregate` — 默认行为不变（生成 aggregate）
  - `test_mixed_table_skip_only_for_bind` — mixed：bind 表无 aggregate，全行表有 aggregate

**verification**:
- `python -m pytest tests/seed_data_generator/test_orchestrator_col_bind.py -v` → 4 个 case 全 pass
- `python -m pytest tests/seed_data_generator/` → 全 pass
- **commit 2**: `feat(orchestrator): skip row aggregate generation when col_tag_bind_mode=true`

### 阶段 3: SetupTG 追加 Bind sampler（tasks §3.2 升位 + §4 合并）— commit 3

> **修订 (2026-08-05)**：原 Plan 把"SetupTG if 分支"放在 commit 3，"追加 Bind sampler"放在 commit 4。commit 2 fix 在 main.py 装配层 `seed_csv_paths` 过滤掉 bind 表（物理效果 = SetupTG 收不到 bind 表 csvPath），等价于原 commit 3 的"if 短路"。为避免 SetupTG 生成器冗余过滤逻辑（Plan §3.1 if 分支），commit 3 直接合并原 commit 3（删） + commit 4（追加 Bind sampler），落地到 commit 3。

**文件**：修改 `src/jmx_skeleton_generator/generators/write_groups.py`（追加新函数）+ 修改 `src/kwjdbc_svt/main.py`（装配新 SetupTG）。

- 3.1 新增函数 `generate_bind_setup_thread_group(write_configs: List[WriteConfig], seed_dirs: Dict[str, str], num_threads: int = 1) -> List`（放 `src/jmx_skeleton_generator/generators/write_groups.py`）：
  - 遍历 `write_configs`，过滤 `col_tag_bind_mode=True` 的表。
  - 对每张 col_tag_bind 表生成 1 个 JSR223 PreProcessor 子节点（Groovy 模板见 Design Doc §4.3）。
  - 返回 `[SetupThreadGroup, hashTree]`，按现有 SetupTG 模式（num_threads=1, scheduler, duration=60, loops=1）。
- 3.2 Groovy PreProcessor 行为（每张 col_tag_bind 表一份）：
  - 读 `seeds/{db}/{table}/*.csv` 列种子文件。
  - 按 `ptag_columns` 注入 `${device_code}` + 其他 ptag 运行时值 → 拼 `ptag_tuple`。
  - `group_id = hash(ptag_tuple) mod num_threads`。
  - 每组 `col_names` = 前 `col_num_per_tag` 列；每组 `row_values` = `seed_num` 行循环填。
  - 写 `props.__SHARED_MEM_{db}_{table}_bind`。
- 3.3 main 入口装配（`src/kwjdbc_svt/main.py::_run_pipeline`）：
  - 在生成 `generate_shared_memory_setup_thread_group` 之后，判断 `if any(wc.col_tag_bind_mode for wc in cfg.write_config):` 追加 `generate_bind_setup_thread_group(...)`。
  - Bind sampler 写到**独立** SetupThreadGroup（与现有 SharedMemory SetupTG 并列），保持 OR 关系。
- 3.4 新增 `tests/jmx_skeleton_generator/test_setup_bind_sampler.py`：
  - `test_bind_sampler_emits_per_bind_table`：2 张 col_tag_bind 表 → 2 个 Bind PreProcessor + 2 个 `_bind` props key
  - `test_no_bind_sampler_when_all_full_row`：全行配置 → 无 Bind SetupTG
  - `test_bind_sampler_preserves_mixed_table_setup`：mixed（bind + 全行）→ 两个 SetupTG 共存
- 3.5 **反退化 §8.7 单元测试**：`tests/jmx_skeleton_generator/test_hash_distribution.py::test_hash_distribution_no_degeneracy`
  - 16 个不同 ptag tuple + `num_threads=4`
  - 断言至少 2 个不同 `group_id`（hash 不退化为单组）

**verification**:
- `pytest tests/jmx_skeleton_generator/test_setup_bind_sampler.py tests/jmx_skeleton_generator/test_hash_distribution.py -v` → 全 pass
- `pytest tests/jmx_skeleton_generator/` → 0 regress
- **commit 3**: `feat(setup-tg): append bind sampler for col_tag_bind tables`

### 阶段 4: 写入 TG 列子集 INSERT（tasks §4）— commit 4

**文件**：修改 `src/jmx_skeleton_generator/generators/write_groups.py::_build_inline_sql_preprocessor_script`。

- 5.1 函数签名扩展（仅关键字参数，不动位置参数）：
  - `col_tag_bind_mode: bool = False`
  - `col_num_per_tag: int = 0`
  - `num_threads: int = 1`
  - `not_null_data_cols: Optional[List[str]] = None`
- 5.2 `col_tag_bind_mode=False`：生成现有全行 INSERT Groovy（行为不变，**完整回归测试**）。
- 5.3 `col_tag_bind_mode=True`：
  - `rows_key = f"__SHARED_MEM_{db}_{table}_bind"`。
  - 读 `props.get(rows_key) as Map`。
  - 计算 `group_id = Math.abs(ptag_tuple.hashCode()) % num_threads`。
  - 取 `groups[group_id].col_names` + `groups[group_id].row_values[random]`。
  - INSERT 列名 = `[ts] + ptag_names + groups[group_id].col_names + not_null_data_cols`（保序去重）。
  - INSERT 值 = `[ts_fmt] + ptag_runtime_values + row_values_subset`。
- 5.4 新增 `tests/jmx_skeleton_generator/test_inline_sql_bind.py` 覆盖：
  - `test_bind_mode_emits_subset_columns` — 列数 < 全列
  - `test_bind_mode_emits_correct_group_id_lookup` — group_id 计算正确
  - `test_bind_mode_includes_not_null_data_cols` — NOT NULL 列追加
  - `test_bind_mode_no_group_returns_safe_default` — 空 group 时 return safe SQL（不 throw）
  - `test_default_mode_unchanged` — 默认 false 行为不变

**verification**:
- `python -m pytest tests/jmx_skeleton_generator/test_inline_sql_bind.py -v` → 5 个 case 全 pass
- `python -m pytest tests/jmx_skeleton_generator/` → 全 pass
- **commit 4**: `feat(write-tg): _build_inline_sql_preprocessor_script col_tag_bind_mode branch`

### 阶段 5: schemaless 集成（tasks §5）— commit 5

**文件**：修改 `src/jmx_skeleton_generator/generators/rest_write_groups.py::generate_rest_write_thread_group`。

- 6.1 函数签名扩展：`write_configs: Optional[List[WriteConfig]] = None`（内部索引成 `write_cfg_by_table: Dict[str, WriteConfig]`，key 为 `{db}.{table}`）。
- 6.2 对每张 col_tag_bind 表，Groovy PreProcessor 改为读 `__SHARED_MEM_{db}_{table}_bind`，按 group_id 取子集列名 + 值，**只填 InfluxDB Line `field_set` 部分**；`tag_set` 部分仍按所有 ptag + regular_tag 填（与现有 REST 路径一致）。
- 6.3 InfluxDB Line Protocol body 构造保持一致（`buildLine` 函数复用）。
- 6.4 新增 `tests/jmx_skeleton_generator/test_rest_write_bind.py` 覆盖：
  - `test_bind_mode_emits_subset_fields_in_line` — InfluxDB Line `field_set` 部分字段数 < 全字段数
  - `test_bind_mode_keeps_all_tags_in_line` — `tag_set` 不变
  - `test_default_mode_unchanged` — 默认 false 行为不变
  - `test_bind_mode_no_group_returns_safe_default` — 空 group 时 line 为注释（不 throw）

**verification**:
- `python -m pytest tests/jmx_skeleton_generator/test_rest_write_bind.py -v` → 4 个 case 全 pass
- `python -m pytest tests/jmx_skeleton_generator/` → 全 pass
- **commit 5**: `feat(rest-write): schemaless mode col_tag_bind branch (InfluxDB Line subset fields)`

### 阶段 6: main 入口校验 + 端到端 fixture + IT（tasks §6.3 + §8.4）— commit 6

**文件**：修改 `src/kwjdbc_svt/main.py` + 新增 fixture。

- 7.1 main 入口顶层校验（在生成 seed 文件前）：
  - `col_tag_bind_mode=true` 时 `col_num_per_tag > 0`：WriteConfig 校验已做（阶段 1），无需重复
  - `col_tag_bind_mode=true` 时 `col_num_per_tag ≤ data_col_count`：在 main 入口遍历 model + write_configs 校验
  - `col_tag_bind_mode=true` 时该表 ≥ 1 `primary_tag`：TsTableConfig 校验 `primary_tag_count ≥ 1`
  - 校验失败抛 `ValueError`，消息含 `{db}.{table}` + 具体字段名
- 7.2 main 入口装配 `write_cfg_by_table` 传给 Orchestrator + SetupTG 生成器 + 写入 TG 生成器。
- 7.3 新增 `tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml`：
  - 1 张 sparse ts 表（4000 data_cols + 1 ptag）+ 1 张 sparse ts 表（4000 data_cols + 1 ptag, mixed 场景备用）。
- 7.4 新增 `tests/kwjdbc_svt/fixtures/test_cfg_col_bind.yaml`：
  - `write_configs[0]: {tbl_name: <sparse>, mode: batch_prepared, col_tag_bind_mode: true, col_num_per_tag: 5}`。
- 7.5 新增 `tests/kwjdbc_svt/test_main_col_bind.py` 覆盖：
  - `test_end_to_end_col_bind_emits_subset_jmx` — 跑 `_run_pipeline`，断言 JMX 中 SetupTG 有 Bind sampler + 写入 TG 列数 < 全列
  - `test_mixed_table_end_to_end` — mixed：全行表 + col_bind 表，断言两个 namespace 共存
  - `test_main_validates_col_num_per_tag_exceeds_data_col_count` — `col_num_per_tag=4001 > 4000` → ValueError
  - `test_main_validates_zero_primary_tag` — `primary_tag_count=0` + `col_tag_bind_mode=true` → ValueError

**verification**:
- `python -m pytest tests/kwjdbc_svt/test_main_col_bind.py -v` → 4 个 case 全 pass
- `python -m pytest tests/` → **全 pass（baseline 701+ + 新增 ~25 case）**
- **commit 6**: `feat(main): col_tag_bind_mode validation + write_configs routing + mixed-table fixture`

### 阶段 7: 文档（tasks §7）— commit 7

**文件**：修改 `docs/specs/kwdb-svt-test-plan-generator-spec.md` + `docs/refs/kaiwudb-schemaless-write-reference.md`（如适用）+ `todolist.md`。

- 8.1 `docs/specs/kwdb-svt-test-plan-generator-spec.md`：
  - §131-136 增补 `col_tag_bind_mode` 段：每表独立 / 5 mode 适用 / NOT NULL 列入 / hash 分组语义。
  - 新增 requirement 段：`col_tag_bind_mode` 必须 ≥ 1 ptag，`col_num_per_tag` 校验范围。
- 8.2 `docs/refs/kaiwudb-schemaless-write-reference.md`（如适用）：
  - 增补 § "col_tag_bind + schemaless" 段：InfluxDB Line `field_set` 子集语义。
- 8.3 `todolist.md`：
  - 在"已完成"段压缩条目：DCR proposal (b9301c6) + Design Doc + Plan + 7 个 feat commit（待落地后回填 hash）。
  - "遗留真问题" 段删除（col_tag_bind 完成后无遗留）。

**verification**:
- 文档 diff 人工 review。
- `python -m pytest tests/` → **仍 701+ pass**（文档改动不触发代码）。
- **commit 7**: `docs(col-tag-bind-write): spec + reference + todolist update`

### 阶段 8: Smoke 验收（tasks §6）— commit 8

**文件**：新增 smoke fixture + 跑命令（不进 git，仅 verification 用）。

- 9.1 起 `kaiwudb-smoke` 容器（已 TLS 重建 + root/root123）。
- 9.2 跑 `kwjdbc-jmx-smoke` skill：
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
      -Jrest_api.hostname=127.0.0.1 \
      -Jrest_api.http_port=8081 \
      -Jrest_api.ca_cert_path=$PWD/../tests/kwjdbc_svt/fixtures/ca.crt \
      -Jwrite_throughput=60 \
      -l /tmp/jmeter-col-bind.jtl -j /tmp/jmeter-col-bind.log 2>&1 | tail -5
  ```
- 9.3 验证：
  - SetupTG 3/3 (Login + DDL-1 + DDL-2) + Write 10/10 + Query 1/1
  - `db_shig_sparse.t_cnc` `count(*) = setup_runs × num_threads × device_per_thread`
  - ptag 列 `device_id` 非 NULL
  - INSERT 列数 = `ts + 1 ptag + col_num_per_tag (5) = 7`（断言 JTL 中 `insert_sql` 列名部分）
- 9.4 反退化测试 §8.8：JTL 中至少 2 个不同 `insert_sql` 列名片段（多个 ptag → 不同 group_id → 不同列子集）。
- 9.5 schemaless smoke 同 9.2-9.4，验证 InfluxDB Line `field_set` 子集语义。

**verification**:
- Smoke v1: SetupTG 3/3 + Write 10/10 + Query 1/1，DB 行数 + 列数 + 反退化断言全绿。
- Smoke v2 (schemaless): SetupTG 3/3 + Write 10/10 + Query 1/1。
- **commit 8** (可选): `chore(smoke): col_tag_bind smoke v1 + v2 record`（仅留痕，不进 git 也可）

### 阶段 10: 反退化测试加固（tasks §8.7 + §8.8）— 阶段 4/9 内已覆盖

- 10.1 §8.7 单元测试 `test_hash_distribution_no_degeneracy` 在阶段 4.5 已落地。
- 10.2 §8.8 冒烟测试通过阶段 9.4 JTL 列名片段断言覆盖。
- 不再单独立 commit。

## 反退化测试（不做功能）

按 OpenSpec tasks.md §8.7 + §8.8：

- **§8.7 单元测试**：`test_hash_distribution_no_degeneracy`
  - 16 个不同 ptag tuple（`device_1..device_4` + ptag_varchar_1..ptag_varchar_4 组合）
  - `num_threads=4`
  - 断言至少 2 个不同 `group_id`（hash 不退化为单组）
  - 实现：直接调 Python 端 hash 函数模拟，验证 multi-to-one 分布
  - 位置：`tests/jmx_skeleton_generator/test_hash_distribution.py`

- **§8.8 冒烟测试**：跑 jmeter 验证多个 ptag 组合写出不同列子集
  - 阶段 9.4 JTL 中 `insert_sql` 列名片段统计：至少 2 个不同列名序列
  - 避免 hash 退化导致所有 ptag 写同一组

## 全局验收

- 全量 `python -m pytest tests/` 通过（baseline 701+ + 新增 ~25 case = ~726 pass）。
- sparse 4000 列 col_tag_bind=true smoke：SetupTG 3/3 + Write 10/10 + Query 1/1，DB 行数 = 期望。
- schemaless col_tag_bind=true smoke：SetupTG 3/3 + Write 10/10 + Query 1/1。
- 反退化测试 §8.7（单元）+ §8.8（冒烟）通过。
- docs/specs/kwdb-svt-test-plan-generator-spec.md 已增补 §col_tag_bind_mode 描述。
- docs/refs/kaiwudb-schemaless-write-reference.md 已增补 §col_tag_bind + schemaless 段（如适用）。
- todolist.md 已更新 DCR 进度（8 commits 落 hash）。
- working tree clean，无遗留 fix。
- 分支 `col-tag-bind-write` 已 ahead origin 8 commits，未 push。

## commit 节奏

| 阶段 | commit | 主题 | 验证点 |
|------|--------|------|--------|
| 1 | commit 1 | `feat(col-tag-bind-write): per-table col_tag_bind_mode + col_num_per_tag in WriteConfig` | 10 config_parser pytest pass |
| 2 | commit 2 | `feat(orchestrator): skip row aggregate generation when col_tag_bind_mode=true` + fix | 4 orchestrator + 2 main_col_bind IT pass |
| 3 | commit 3 | `feat(setup-tg): append bind sampler for col_tag_bind tables` | 3 setup_bind + 1 hash_distribution pytest pass |
| 4 | commit 4 | `feat(write-tg): _build_inline_sql_preprocessor_script col_tag_bind_mode branch` | 5 inline_sql_bind pytest pass |
| 5 | commit 5 | `feat(rest-write): schemaless mode col_tag_bind branch (InfluxDB Line subset fields)` | 4 rest_write_bind pytest pass |
| 6 | commit 6 | `feat(main): col_tag_bind_mode validation + write_configs routing + mixed-table fixture` | 4 main_col_bind pytest pass + 全量 736+ pass |
| 7 | commit 7 | `docs(col-tag-bind-write): spec + reference + todolist update` | 文档 review + pytest 仍 pass |
| 8 | commit 8 (optional) | `chore(smoke): col_tag_bind smoke v1 + v2 record` | smoke 全绿 + 反退化断言 |

> **修订 (2026-08-05)**：原节奏 9 个 commit 合并为 8 个。原 commit 3 "SetupTG if 分支" 已在 commit 2 fix 在 main.py 装配层实现（物理等价），删除。commit 3-8 顺位往前。

每 commit 后跑 `python -m pytest tests/<新测试文件>.py -v` + `python -m pytest tests/jmx_skeleton_generator/ tests/seed_data_generator/ tests/config_parser/ tests/kwjdbc_svt/` 确认无 regress。

## 风险与回滚

按 Design Doc §6 列的 8 条风险 + 缓解方案；本阶段实施时不引入新风险源。

回滚策略：

- 单 commit 可原子回滚（每阶段独立）。
- `col_tag_bind_mode=false` 默认值，整 feature 关闭 → 现有 fixture 行为不变。
- col_tag_bind=true 是 opt-in，不影响现有 sparse/rel/ts fixture。
