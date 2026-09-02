# 现状与遗留任务（2026-08-31 checkpoint）

> 10 个 fix + 2 个 DCR + R-3（partial + FK DDL 续）+ F-17 + 条件关系初始化 + §1-§5 + §6 insecure-removal + §6 UDV/skill + §6.4 调试填充 + §6.4.2 全修 + B1/B3/B5 + **col-tag-bind-write 8 commits + 4 fix (D-9~D-13)** + **write-strategies 死代码清理（ffa6cfd / ab9e262）**：稳定基线 `c876acc` / `27b8aec` / `4351c99` / `d461e40` / `b9301c6`（DCR proposal）/ `3898aa8` `b677255` `9769493` `b067c8c` `c078431` `801ed46` `90f7dee` `6455cab` `389dc56` `76cb16a` `4e3791c` `22092a8` `3e65a37`（doc）/ `8246c44`（fixture ts+root pwd）/ `526dcbf`（seed+ddl decimal）/ `f23773a`（JMeter 5.6.3 stop API + ptag_values wiring）/ `7fef4ab`（fixture decimal→float8）/`ffa6cfd`（collapse strategy call site to inline lookup）/`ab9e262`（delete strategy module + tests + helper）。pytest 661/661。**smoke 已实跑**（bind path 30s jmeter 127 samples / 0 Err，iot_monitor.meters 60 行 + t_full 60 行，distinct ptag=2 各表，JMX Write TG sampler=`JSR223Sampler` 与 d83a09e/af21456 baseline 字节一致）。分支 `feat/sparse-table` ahead origin 3 commits（未 push）。**write-batch-mode-semantics DCR 5 件套已起头**（`openspec/changes/write-batch-mode-semantics/{.openspec.yaml, proposal.md, design.md, tasks.md, specs/write-batch-mode-semantics/spec.md}`，openspec-validate 通过；未 commit 待 plan.md 路径 `/home/liujin/.claude/plans/crispy-enchanting-panda.md` 8 commit 落地）。**已合并 `ptag-runtime-derived` DCR**：原 `openspec/changes/ptag-runtime-derived/`（commit 1 `16a66a1` 仅文档落地，tasks 未勾）已删除；其核心规则（ptag 第 1 列 runtime 派生 + SetupTG 双层 for + deviceIndex 与 device_start 绑定）全部归入本 DCR，用内联 GString `"${threadNum}_${deviceIndex}"` 直接拼接，不抽 `ptagRuntimeValue` helper。

遗留：spec gap 19 个未验功能点；col-tag-bind-write §8 smoke 端到端反退化断言 + JDBC bind path 验证待补；t_full full-row path `escapeLineValue` Groovy regex `PatternSyntaxException` 是 rest-schemaless §1-§5 范围 D-15 独立 bug（与 bind 无关）。

## 已完成（压缩）

- **write-strategies 死代码清理 (ffa6cfd / ab9e262)**：`WriteStrategy` ABC + 5 个具体策略 + `STRATEGY_REGISTRY` + `ResolvedTable`/`WriteRuntime` 在生产仅 `get_sampler_type()` + `get_config("usePrepared")` 两方法被消费（仅 `single_prepared`/`batch_prepared`），其余 6 抽象方法（`mode_name` / `requires_prepared_insert_template` / `generate_query` / `requires_param_setup` / `get_preprocessor_code` / `get_sampler_script`）全 0 生产引用。问题源自 `commit 040e555` (2026-07-10) 重构后 `_build_batch_prepared_sampler_body` 自接管 Groovy 体生成，strategy 层 `get_sampler_script()` 整套设计落空；`single_insert`/`batch_insert` 模式始终走 `_build_direct_insert_components` 直调 `direct_insert_write`，绕过 strategy。`commit 1 (ffa6cfd)`：write_groups.py:1046-1049 3 行 strategy 调用折叠为 `_PREPARED_MODE_SAMPLER: Dict[str, Tuple[str, bool]]` inline lookup（`single_prepared`→`(JDBCSampler, True)` / `batch_prepared`→`(JSR223Sampler, False)`），删 `from write_strategies import get_strategy`，xml_helpers docstring 同步。`commit 2 (ab9e262)`：`git rm -r src/write_strategies/`（9 文件）+ `tests/write_strategies/`（11 文件）+ `test_helper_unified.py` single_prepared 侧断言改写；spec §7"代码层冗余" + design §3.7 STRATEGY_REGISTRY 块同步改写为"策略层已合入"历史归档。pytest 765→765（commit 1）→661（commit 2，删 104 strategy 测）/ 0 regress。**smoke 实跑**：30s jmeter -n on `test_model_col_bind.yaml` + `test_cfg_col_bind_jdbc.yaml` → 127 samples / 0 Err (0.00%)，JMX Write TG sampler `testclass="JSR223Sampler"`（与 d83a09e/af21456 baseline 一致），iot_monitor.meters 60 行 (device_1=30, device_3=30) + iot_monitor.t_full 60 行 (device_1=30, device_3=30)，distinct ptag=2 各表，列互补 100% 兑现（device_1 + device_3 per D-21）。

- **write-batch-mode-semantics DCR 收尾 + direct_insert path 死代码清理**（待 commit）：`_build_inline_sql_preprocessor_script` main path 重写 — 修两个 bug：`new ArrayList(srcRow)` 改 `srcRow.toList()`（ArrayList 无 Object[] 构造器，Groovy runtime 报 `Could not find matching constructor for: java.util.ArrayList([Ljava.lang.Object;)`)`）+ `rows.add("(...)")` 位置从 d for 内移至 r for 内（之前错位置导致每 device 只 add 1 行丢 ×batchLines 倍数据）；保留 dpt for + 整步 ts（`baseTime + (long) r * msStep`）+ deviceCode 派生 + 数值/字符串 quoting 逻辑。direct_insert_write 模块 dead 清理：删 `preprocessor_generator.generate_preprocessor_script`（已 dead，被 inline script 替代，13 case test 删）+ `sampler_generator.{generate_jdbc_sampler_config, create_jdbc_sampler, create_jsr223_preprocessor_for_write}`（write_groups.py 死 import）+ `sql_generator.generate_single_insert_sql`（无生产调用）；`__init__.py` 同步清理导出；`write_groups.py` 删 4 个死 import；保留 `preprocessor_generator.{_groovy_str_literal, _safe_key_token, generate_relational_init_preprocessor_script}` + `sql_generator.generate_batch_insert_sql` + `sampler_generator.generate_relational_table_init_sampler`（ddl_setup 关系表 init 生产用）。fixtures cfg throughput 全部改 1.0（spec §2.2 新规约：每分钟 1 sampler tick 攒 batch_lines × msStep 整步 ts 窗口；7 个 cfg 文件 30 处 throughput 字段统一改 1.0）。注释清理：所有 generator + helper + test 注释重写为"现在做什么 + 为什么"，删"write-batch-mode-semantics DCR (2026-08-31) §X.Y"、"pre-fix had ..."、"tasks.md §X.Y"等修订历史引用；test 方法名中英文混杂 `test_uses_整步_ts_formula` → `test_uses_step_per_row_ts_formula`。pytest 673→639（-34 dead case）/ 0 regress。**smoke 双路径 0 Err**：`direct_insert`（mode=batch_insert, throughput=1, dpt=2, bl=60, test_duration=120s）→ 240 rows / 4 devices / 60 ts / **Err 0.00%**；`batch_prepared`（test_cfg_col_bind_jdbc, mode=batch_prepared + col_tag_bind_mode=true）→ 480 rows / 4 devices / 240 ts / **Err 0.00%**；清理未破坏 batch_prepared 路径。

- **F-18 稀疏表（SPARSE TABLE）数据模型 (TODO_COMMIT)**：KaiwuDB 2.4.1+ 新增 `SPARSE` 关键字，仅时序引擎。`TsTableConfig.sparse: bool = False` + 派生 `@model_validator check_data_col_count_cap` 双轨硬校验（sparse ≤20000 / 普通 ≤4096）；`_create_ts_table` 按 flag 拼 `create [sparse] table [if not exists]`；`tests/column_namer/test_namer.py::test_large_column_count` 1 case 转 sparse=True（pre-fix 10000 列违反新 cap）；新 `tests/config_parser/test_ts_table_sparse.py` 7 case + `tests/ddl_generator/test_ts_ddl.py` 追 5 case（keyword 发射 + if_not_exists 顺序 + with_hash 末位 + 无 if_not_exists 形态）；`test_model_shig_sparse.yaml` 表层加 `sparse: true`（复用既有 4000 列 fixture）；spec §3.2/§8.3 各加一段说明。pytest 758 passed / 0 regress（+12 sparse 测，基线 746）；pre-existing 7 fail（bind sampler `__P` + col_bind e2e）未触碰。DDL emit 实测：`create sparse table if not exists db_shig_sparse.t_cnc (ts timestamp not null, col_char_1, ..., 4000 列)`。
- **D-17 JDBC bind path smoke + D-27 generator fix (af21456 / d83a09e)**：D-17 验证 `mode=batch_prepared + col_tag_bind_mode=true` JDBC 路径真集群 smoke，发现并修 D-27 — `_build_batch_prepared_preprocessor_body` 完全没有 `col_tag_bind_mode` 分支，prep 仍读 `__SHARED_MEM_<table>` 但 SetupTG bind sampler 写 `__SHARED_MEM_<table>_bind` → Write TG 每轮 NPE `size() on null`。fix: 加 `_build_batch_prepared_bind_preprocessor_body` helper，按 D-21 per-deviceCode key（与 schemaless 路径一致）从 bind map 取 row，按 ColumnNamer 实际列顺序（`[ts, *data_cols, *ptag]`，ptag 在末尾）填 row，未在 subset 的列填 NULL。`_build_batch_prepared_preprocessor_body` + `build_batch_prepared_preprocessor_script` + `generate_write_thread_groups` 三层透传参数；D-27 fix 同时给 `test_model_col_bind.yaml` 两张表补 `ts_col`（name=ts, type=timestamp, ms_step=1000）—— pre-fix `_build_columns_by_table` 在 `ts_col=None` 时跳过 'ts' 列名，baked INSERT 模板少 1 列 vs DDL 12 列 → server reject；schemaless bind path 不读 baked insertSql 所以未暴露。7 个新 pytest case（test_batch_prepared_bind.py），753 总 pass / 0 regress。30s jmeter -n smoke：127 samples / 0 Err (0.00%)，iot_monitor.meters 60 行 (device_1=30, device_3=30)，iot_monitor.t_full 60 行 (device_1=30, device_3=30)，distinct ptag=2 各表，列互补 100% 兑现（device_1 写 col_char_1 only，device_3 写 col_int8_1 + col_varchar_2 only）。分支 `col-tag-bind-write` ahead origin +2 commits (af21456 / d83a09e)。

- **§7 文档对齐 + schemaless dead-code 标注 (2e97349)**：3 个 T1/T2 功能（PreparedStatement / 外键 / 无模式写入）已落地但主 spec §7 未维护，文档/代码脱节。改主 spec §7 表格 + 删过时 note + 加 "代码层冗余" + 加 "回归覆盖" note；schemaless_strategy.py module/class docstring 改写为 "DEAD CODE since d461e40"；registry.py:78 加 NOTE；single/batch_prepared_strategy.py + _build_foreign_key_clause + pregenerate_reference_columns 加 commit 引用。7 文件 +56/-15。pytest 746 passed 0 regress。
- **F-9 至 F-17 + R-1/R-2/R-3/R-3 续 + #3**（9e285aa / cbc0b8d / ea3dcfe / 3069d9c / e33605e / 09fa065 / 8614b90 / b3e2c5e / 1c02629 / 2c32c81 / d9c3fa9 / 87faab9 / c14969f / 9333117）：10 fix + 2 DCR + R-3 partial + 条件关系初始化。shig smoke 0 err / 4-20-100-3900-3900 / FK 23503 验证 / 0 orphans / pytest 633+10 = 643 pass / sparse 603 samples。
- **§1-§5 (rest-schemaless-write)** (996427f / 71400dc / 67d8f7b / ef2faed / af32312 / 87bf67c / 93d8a18 / dd4a091 / 7b3e904 / 2f2f575 / d481022 / d9c2720 / 5b21cc3 / 92efda5)：HTTP sampler + RestConfigError + SetupTG HTTP DDL pre-create + Write TG (InfluxDB Line) + Query Round-Trip + mode 路由。pytest 666 pass + 6 个新 test_ddl_setup_http_thread_group case。
- **§2 上接** (300d675 / 53adf3b / 06ebb3c / fb99013)：SetupTG HTTP DDL pre-create 落地，fail-fast TLS + ca_cert_path 缺失。
- **§6.x insecure-removal (c876acc)**：schemaless Login 强制非空密码 → 必须 TLS → insecure 路径无解（SQLSTATE 28P01）。`RestApiConfig.https_mode` Literal 收紧 `["tls"]` + ca_cert_path 必填 + 三处 generator 删 insecure 分支 + fixture `test_cfg_schemaless.yaml` 删 + `test_cfg_schemaless_tls.yaml` login_password 改 `root123`。test 5 调整 + 2 新增。16 文件 +306/-241。
- **§6.x UDV/skill sync (27b8aec)**：kwjdbc-jmx-smoke 恢复双模式（JDBC 走 insecure / schemaless 走 TLS 唯一）；ca_cert_path 改 `${__P(rest_api.ca_cert_path,)}` UDV（与 hostname/port 一致），绝对路径 -J 注入；SKILL.md §6 双模式 + §6.0 容器 TLS 重建 + §6.0.1 隔离陷阱 + §6.2 jmeter 命令加必填 -J + §6.4 调试占位。design.md Decision 2 加范围说明。test 2 调整。8 文件 +105/-21。
- **§6.4 调试填充 + 2 docs/refs (4351c99)**：3 次 TLS smoke 实跑沉淀 4 条调试条目（root 无密码 / DDL-2 props.put null / Query 表不存在 cascade / 端口 8080 误报）。新增 2 份 docs/refs：`kaiwudb-kwbase-sql-reference.md` 3.2.0 全参数 + `kaiwudb-user-management-reference.md` CREATE/ALTER/DROP + 权限模型 + insecure 限制。SKILL.md 交叉引用区扩到 4 条。3 文件 +564/-1。
- **§6.4.2 全修 + B1/B3/B5 (d461e40)**：squash merge `fee6986`+`a6d079a`+`12e5238`+`ddb0329`。DDL SetupTG setprop_script 加 null/empty 守卫（DDL-2 根因修复）+ duration 1s→`${test_duration}` + Write TG 默认 db `defaultdb`→`iot_monitor` + SharedMemory 加载回 setup + **B1** Write body-code assertion（锁 J）+ **B3** Query `$.data` 抽取 + assertion 检 `data.size() >= expected_rows`（避 `$.rows` 列数假阳性）+ **B5** Write prep `ctx.stopThread()` 替代 `ctx.setStopThread(true)`（JMeter 5.6.3 Groovy 无 boolean 参数版）+ SKILL.md §6.4.5 新增空 body 诊断 + 反例/防退化清单。smoke v17 全绿：SetupTG 3/3 + Write 10/10 + Query 1/1，DB `count(*) from iot_monitor.meters`=10，ptag `device_1+device_2` 各 5 行。pytest 701/701。30 文件 +4530/-247。
- **col-tag-bind-write 8 commits + 4 DCR fix (3898aa8 / b677255 / 9769493 / b067c8c / c078431 / 801ed46 / 90f7dee / 6455cab / 389dc56 / 76cb16a / 4e3791c / 22092a8 / 3e65a37 / 8246c44 / 526dcbf / f23773a / 7fef4ab)**：
  - **commit 1 (3898aa8)** `feat(col-tag-bind-write): per-table col_tag_bind_mode + col_num_per_tag in WriteConfig` — `WriteConfig` 加 2 字段 + `check_col_tag_bind_mode_positive` 校验 + 6 config_parser case
  - **commit 2 (e33605e 部分改写)** `feat(orchestrator): skip row aggregate generation when col_tag_bind_mode=true` — `_generate_table_seeds` 加 `skip_row_aggregate` + main entry 装配 `write_cfg_by_table` + 4 orchestrator case
  - **commit 3 (90f7dee + 6455cab + c078431)** `feat(setup-tg): append bind sampler for col_tag_bind tables` — `generate_bind_setup_thread_group` + hash 分组 Groovy sampler + 4 setup_bind + 1 hash_distribution 反退化
  - **commit 4 (801ed46)** `feat(write-tg): _build_inline_sql_preprocessor_script col_tag_bind_mode branch` — JDBC bind 路径 + safe SELECT 1 兜底 + 5 inline_sql_bind case
  - **commit 5 (389dc56 + 76cb16a + 4e3791c)** `feat(rest-write): schemaless mode col_tag_bind branch (InfluxDB Line subset fields)` + 2 fix — schemaless bind + 4 rest_write_bind case
  - **commit 6 (22092a8)** `feat(main): col_tag_bind_mode validation + write_configs routing + mixed-table fixture` — main entry ValueError 校验 + write_configs 路由 + 4 main_col_bind case + 端到端混合表 fixture
  - **commit 7 (3e65a37)** `docs(col-tag-bind-write): spec + reference + todolist update` — §col_tag_bind_mode spec §131-144 + reference §5.5 集成段
  - **D-9 (526dcbf)** `fix(seed-ddl): align decimal/numeric support with spec §403` — adapter `_FLOAT_TYPES` + DDL mapper 加 decimal/numeric + 6 pytest
  - **D-10 (8246c44)** `fix(col-tag-bind-write): fixture timestamp val_range + root password` — timestamp regex + decimal numeric range + ent 镜像密码策略（Kaiwu#2026）
  - **D-12/D-13 (f23773a)** `fix(col-tag-bind-write): JMeter 5.6.3 stop API + ptag_values wiring` — `vars.put('request_body','')` 兜底替换 stopThread 错误推断（jmeter.apache.org API 确认 JMeterContext 无 stop 类方法）+ SetupTG 烤 `ptag_values` / `ptag_names` + skeleton.py `_ptag_names_by_table()` 传 write_cfg
  - **D-11 (7fef4ab)** `fix(col-tag-bind-write): fixture decimal→float8 for ts table type scope` — spec §8.1 (L412-428) 通用时序 data 列类型未含 decimal（仅关系表）
  - pytest 701→745（+44：6 config_parser + 4 orchestrator + 4 setup_bind + 1 hash_distribution + 5 inline_sql_bind + 4 rest_write_bind + 4 main_col_bind + 3 ddl_mapper + 3 adapter + 10 旧 case 覆盖）。0 regress。schemaless bind path smoke 实测：`iot_monitor.meters` 10 行写入成功。

## 遗留真问题

- **write-batch-mode-semantics DCR 5 gap 未修（仅 DCR 起头）**：
  - gap #1：SetupTG bind sampler 仅烤 numThreads 个 entry（`shared_memory_setup.py:232`），Write TG bind 分支固定取 index=0 → 当 `device_per_thread > 1` 时 SetupTG 不烤 numThreads×dpt 个 deviceCode，部分设备找不到 SharedMemory key。现有 `tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml`（dpt=2）已暴露
  - gap #2：schemaless bind 分支 InfluxDB Line `tag_set` 只填 ptag（`rest_write_groups.py:244-248`），缺 regular_tag，违反 spec §2.0 L145 约定
  - gap #3：`single_insert` / `batch_insert` / `single_prepared` 三个 mode 与 `col_tag_bind_mode=true` 静默错配（`generate_write_thread_groups` / `_build_direct_insert_components` 不读 `wc.col_tag_bind_mode`）
  - gap #4：`single_prepared + batch_lines > 1` schema 未禁（运行时未定义行为）
  - gap #5：`_build_inline_sql_preprocessor_script` bind 分支整批共用一个 ts（`write_groups.py:181`），与 D-24 schemaless bind 分支"batch_lines 个递增 ts"不一致
  - **前置条件**：ptag-runtime-derived DCR commit 2-3 必须先 archive（提供 `ptagRuntimeValue` helper + SetupTG 双层 for）— 当前 tasks.md 全部 `- [ ]` 未勾

## D-23/D-24/D-25/D-26 闭环（2026-08-14）

D-23 修 spec §4 L327 cyclic-fill（random start + wrap-around）：commit 5 简化实现 `rows.remove(0)`（rows 用尽后 prep 静默退出）→ 改 random start + wrap-around（rows 永不用尽）。

D-24 实现 batch_lines 拼 N 行 body：prep 每次 prep 构造 `batch_lines` 个 InfluxDB Line 用 `\n` 分隔，spec §4 L327 完整语义。

D-25 SetupTG bind sampler 给每 deviceCode 烤 batch_lines row（之前每 device 1 row，batch_lines=10 时 10 行重复同一 row → server reject duplicate-value）→ D-25 让 SetupTG 烤 batch_lines 行不同 row（per-(deviceCode, b) hash 取列种子索引）。

D-26 deviceId 用 threadNum 派生：之前 `(iterNum-1 + b) % devicePerThread + deviceStart`，devicePerThread=1 时 mod 1 = 0 → deviceId 永远 = deviceStart → distinct ptag = 1。改 `threadNum × batchLines + b + deviceStart` 让 thread 间区分。

**5min smoke 实测**（user 要求 throughput 偏差 ≤5%）：
- 4 threads × 1/sec × 10 batch_lines × 300s = 12000 行/thread × 4 = **实测 12000+12000 = 24000 行**
- meters 12000 (偏差 0%)
- t_full 12000 (偏差 0%)
- meters distinct ptag = 4 ✓ (SetupTG 烤的 4 deviceCode)
- pytest 746 passed (0 regress)

## D-15 / D-22 闭环（2026-08-14）

D-15 真根因找到（D-22 commit `78b81a4`）：**不是 commit 5 加的 `escapeLineValue`**（它是死代码，0 调用），而是 **`formatFieldValue` 行 100 的字符串转义分支**——`replaceAll('\\\\\\\\', '\\\\\\\\\\\\\\\\')` Python 双反斜杠转义链到 Groovy 单引号串后 Java regex 看到 trailing backslash。

之前能调通的原因：D-21 之前 Write TG ThreadGroup `num_threads` 硬编码 1，t_full threadNum=1 永不跑 prep——formatFieldValue 路径从未真触发。D-21 修 num_threads 后 threadNum=1 跑 prep 才暴露。

**修法**：formatFieldValue 字符串转义改用 `String.replace` (literal, 无 regex)。同时删 `escapeLineValue` 死代码，保留 `escapeTagValue` 兜底。

**真集群 smoke 验证 D-22**（用户要求非仅 UT）：
- 临时 fixture t_full 加 col_varchar_3 `val_range: "^[ \",=]+$"`（字符集只含 InfluxDB Line 协议保留字符 `space , = "` 不含字母数字 → 强制 100% 触发 formatFieldValue 字符串转义分支）
- 实测 seed 内容：`"  \""\""  ="` `" = \""\""\""\""=="` （**全保留字符**）
- smoke `PatternSyntaxException = 0`（D-22 修法生效）
- DB `col_varchar_3` 真值含 `"  \""\""  ="`（**保留字符 round-trip 写入成功**）
- 回归 fixture 删除 col_varchar_3 后 pytest 746 passed + smoke t_full 5 行

**smoke 实测**（D-22 后）：
- iot_monitor.meters (bind): 20 行 ✓ (D-21 互补列不变)
- iot_monitor.t_full (full-row): 5 行 ✓ (seed_num=5 用尽后 rows empty 兜底)
- pytest 746 passed

## 收尾确认

**col-tag-bind-write 当前状态**（11 commits ahead origin）：
```
e765bf1 docs(col-tag-bind): per-deviceCode key 修订 + per-group-subsets DCR 跟踪
fcaef6f fix(col-tag-bind-write): per-deviceCode SharedMemory key + col_names by loop index (D-21)
be6b7fe docs(todolist): D-14 bind path ptag_values 真值验证 + 移除 D-16
2fdabde fix(col-tag-bind-write): bind SetupTG first-ptag = deviceCode regardless of name (D-14)
de87bea docs(col-tag-bind-write): checkpoint D-9/D-10/D-11/D-12/D-13 + D-15/D-16/D-17 follow-ups
7fef4ab fix(col-tag-bind-write): fixture decimal→float8 for ts table type scope (D-11)
f23773a fix(col-tag-bind-write): JMeter 5.6.3 stop API + ptag_values wiring (D-12/D-13)
8246c44 fix(col-tag-bind-write): fixture timestamp val_range + root password (D-10)
526dcbf fix(seed-ddl): align decimal/numeric support with spec §403 (D-9)
3e65a37 docs(col-tag-bind-write): spec + reference + todolist update
22092a8 feat(main): col_tag_bind_mode validation + write_configs routing + mixed-table fixture
```

**bind path smoke 真绿**（schemaless + 真集群）：
- `iot_monitor.meters`：20 行（numThreads=2 + devicePerThread=2）
- device_1 写 `col_float4_1 + col_float8_1 + col_bool_1 + col_float8_2 + col_char_1`
- device_3 写 `col_int8_1 + col_int4_1 + col_varchar_1 + col_varchar_2 + col_float8_3`
- **两组列 100% 互补**（design §1 业务语义："设备 1 关心列 1-5，其他列对它无效"）

**关键修复路径**（从错到对）：
- commit 5/6: 落地"每组共享前 N 列"简化版（design §4.3 简化说明）
- D-12: SKILL.md §6.4.5 stopThread 推断错（JMeter 5.6.3 无 stop API）→ 改 `vars.put('request_body','')` 兜底
- D-13: bind mode tag_set 漏 ptag → SetupTG 烤 `ptag_values` + skeleton 传 `ptag_names_by_table`
- D-14: SetupTG first-ptag 硬编码 device_id（fixture ptag_varchar_1 落空）→ 按 ptagNamesOrdered[0]
- D-15: t_full escapeLineValue regex bug — 与 bind 无关，独立 follow-up
- D-18: 改 colNamesSubset 按 group_id offset（hash 退化鲁棒性差）
- D-19: 改 random sampling（hash 退化仍是问题）
- D-21: **彻底改设计**——key=deviceCode（不用 hash）+ col_names by loop index `t` + Write TG ThreadGroup num_threads 修硬编码 1

**设计教训**（D-18 → D-21 完整迭代）：
- "用 hash 函数决定列分配"对短字符串不可靠——Groovy 默认 hash 退化
- "用 random sampling" 仍依赖 hash group_id 索引
- "用 deviceCode 当 key" + "offset 用循环 index"——彻底避开 hash 依赖，每 device 真正独立
- 业务语义："设备 N 关心列 N" 对应 **per-deviceCode key**（非 per-groupId）

## 已删（误判 → 真因）

- ~~L-1 LLM FILTER 方言翻译~~ → 真因 F-14（? 占位符冲突），修了之后 smoke 0 errors
- ~~L-2 last_row(*) JDBC 驱动兼容~~ → 真因 F-14
- ~~L-2 -Jtest_duration=60 不生效~~ → F-15 + F-16
- ~~L-3 Q8-Q12 throughput=1/h vs 短测~~ → 实际生产 test_duration≥8h，无影响
- ~~R-1 shig fixture 列数严重不足~~ → e33605e 已对齐
- ~~R-2 query SQL 命名规则 DCR~~ → e33605e 已落地（openspec/changes/query-naming/）

## spec 未验功能点（kwdb-svt-test-plan-generator-spec.md gap 分析 2026-07-22）

shig fixture + smoke 跑过的：关系+时序混合、PK/ptag/rtag、ref: FK、batch_prepared 模式、SetupThreadGroup 共享内存、列名规则、throughput、单 `?` bind、retentions/partition_interval/with_hash、DDL FK 23503 验证。

未验 / 缺口（按优先级排序）：

### P1：写入模式单一
- **#1** shig 只用 `batch_prepared`（T1）。spec §2.0 列 5 种模式：`single_insert` / `batch_insert`（T0）/ `single_prepared`（T1）/ `batch_prepared`（T1）/ `schemaless`（T2 暂不实现，应主动报错）。3 种未验。
- **#2** schemaless 主动报错行为未验。spec §7 要求生成器在 `mode: schemaless` 时拒绝生成。

### P1：数据生成边界
- **#3** `nullable=true` + `null_rate>0` 已验。sparse 4000 列 99% NULL fixture 落 commit `c14969f` / `9333117`，smoke 603 samples / 0 errors。
- **#4** `enum` 多种子数（`seed_num > len(enum_values)` 时循环填充）未验。shig rtag_varchar 4 值 seed=4 刚好命中，未触发循环分支。
- **#5** `regex` val_range 未验。shig 全 enum/int range。

### P2：跨表/跨 db
- **#6** `ref:` 跨 db 引用未验。shig 全 db_shig_rel 内部引用，未跨时序库引用关系库。
- **#7** 跨 db JOIN 未验。shig Q10 JOIN 是 t_cnc/t_electmeter（同 db）。

### P2：查询
- **#8** 多 `?` 占位符独立采样未验。shig Q4/Q5 都只 1 个 `?` bind ptag。
- **#9** 未关联列的 `?` 报错未验。spec §2.0 备注明确 `LIMIT ?` 等应在生成阶段报错。

### P3：约束/边界
- **#10** `retentions` 表级覆盖库级未验。shig 全库级 1d。
- **#11** Tag varchar 上限 128 字节未验。shig rtag varchar(64)。
- **#12** Primary Tag 上限 4 列 + varchar 128 字节未验。shig 1 ptag。
- **#13** WITH HASH 必须在 DDL 末尾未对比反例。
- **#14** WITH HASH 范围 1-50000 + 推荐值表未验。

### P3：协同/独立变量
- **#15** 多端协同（多 JMeter 端 + device_start 分割设备号）未验。
- **#16** 多表独立 num_threads 未验（spec §1.6 明确当前版本不支持，follow-up）。

### P3：验收/错误
- **#17** §6.2 配置错误清晰提示未系统测过。
- **#18** §6.2 代码覆盖率 > 80% 未验。
- **#19** §6.1 各表数据列类型分布 ±5% 偏差未单独验。

下一步建议：先验 **#1 多种写入模式** + **#3 nullable+null_rate** + **#2 schemaless 报错**。这三个是 P1 且不依赖新 fixture 改写（可用 shig 切 mode 测，或写一个新 fixture）。

## 跑命令模板（schemaless TLS smoke — 2026-07-31 基线）

```bash
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
source .venv/bin/activate

# 容器状态（已 TLS 重建 + root/root123 建好）
docker ps --filter name=kaiwudb-smoke --format "{{.Status}}"

# 1. 生成 JMX
rm -rf /tmp/jmeter-schemaless-out && mkdir -p /tmp/jmeter-schemaless-out
python -m kwjdbc_svt.main \
    tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml \
    tests/kwjdbc_svt/fixtures/test_cfg_schemaless_tls.yaml \
    -o /tmp/jmeter-schemaless-out

# 2. 跑 jmeter（ca.crt 已 docker cp 到 fixtures，写死路径）
cd /tmp/jmeter-schemaless-out
timeout 30 jmeter -n -t test_plan.jmx \
    -Jtest_duration=10 -Jnum_threads=1 -Jdevice_start=1 -Jdevice_per_thread=2 \
    -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
    -Jrest_api.hostname=127.0.0.1 \
    -Jrest_api.http_port=8081 \
    -Jrest_api.ca_cert_path=$PWD/../tests/kwjdbc_svt/fixtures/ca.crt \
    -Jwrite_throughput=60 \
    -l /tmp/jmeter-schemaless.jtl -j /tmp/jmeter-schemaless.log 2>&1 | tail -5

# 预期（d461e40 基线）：14 samples / 14 pass
#   SetupTG 3/3 (Login + DDL-1 create ts db + DDL-2 create ts table)
#   Write 10/10 (device_1..device_2 各 5 行, ctx.stopThread 兜底不再发空 body)
#   Query 1/1 ($.data 抽取, size() >= expected_rows)
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "select count(*) from iot_monitor.meters; select distinct device_id from iot_monitor.meters"
```

**容器镜像**：用 `devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest`（F-17 已修）。`/kaiwudb/bin/kwbase` 绝对路径，`PATH` 里没有。

## col-tag-bind-write DCR 推进状态（2026-08-05）

**分支**：`col-tag-bind-write`（从 `refactor/generic-test-plan`@`baf4c95` 拉），HEAD `b9301c6`，ahead origin 4 commits。

**产物**（4 件）：
- `openspec/changes/col-tag-bind-write/proposal.md` (48 行) + `design.md` (156 行) + `tasks.md` (190 行细化版) + `specs/col-tag-bind-write/spec.md` (143 行)
- `docs/superpowers/specs/2026-08-05-col-tag-bind-write-design.md` (393 行)
- `docs/superpowers/plans/2026-08-05-col-tag-bind-write.md` (286 行)
- `todolist.md` checkpoint 更新

**DCR 决策摘要**（8 Decisions）：
1. `col_tag_bind_mode` 每表独立（`write_config[].tbl_name` 项下），与 mode 正交
2. SetupTG 复用现有加载行种子文件 sampler + if 分支；启用追加新 JSR223 Sampler 加载列种子
3. 复用现有列种子文件（Orchestrator 已生成，API 在 `src/seed_data_generator/io.py`）
4. 映射函数：`hash(ptag_tuple) mod num_threads`（多对一）；每组行数 = `seed_num`
5. SharedMemory key 区分：`__SHARED_MEM_{db}_{table}_bind`（混合表场景强制需求）
6. INSERT 列名列表必须包含 NOT NULL 列（ts + primary_tag + 显式 NOT NULL data_col）
7. 适用所有 5 种 mode（含 schemaless）
8. schemaless 集成：InfluxDB Line 部分列从 bind 内存种子组取

**下一步**：commit 1 = `WriteConfig` 加 `col_tag_bind_mode` + `col_num_per_tag` 字段 + 6 config_parser pytest case + 全量 701+ 不 regress。

## 跑命令模板（col-tag-bind-write smoke — 待 commit 1-7 落地后跑）

```bash
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
source .venv/bin/activate

# 容器状态（已 TLS 重建 + root/root123 建好）
docker ps --filter name=kaiwudb-smoke --format "{{.Status}}"

# 1. 生成 JMX
rm -rf /tmp/jmeter-col-bind-out && mkdir -p /tmp/jmeter-col-bind-out
python -m kwjdbc_svt.main \
    tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml \
    tests/kwjdbc_svt/fixtures/test_cfg_col_bind.yaml \
    -o /tmp/jmeter-col-bind-out

# 2. 跑 jmeter
cd /tmp/jmeter-col-bind-out
timeout 30 jmeter -n -t test_plan.jmx \
    -Jtest_duration=10 -Jnum_threads=4 -Jdevice_start=1 -Jdevice_per_thread=2 \
    -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
    -Jrest_api.hostname=127.0.0.1 \
    -Jrest_api.http_port=8081 \
    -Jrest_api.ca_cert_path=$PWD/../tests/kwjdbc_svt/fixtures/ca.crt \
    -Jwrite_throughput=60 \
    -l /tmp/jmeter-col-bind.jtl -j /tmp/jmeter-col-bind.log 2>&1 | tail -5

# 预期（commit 7 落地后）：SetupTG 3/3 + Write 10/10 + Query 1/1
#   DB `iot_monitor.meters` count(*) = 4 × 2 × 5 = 40 行
#   INSERT 列数 = ts + 1 ptag + col_num_per_tag (5) = 7
#   反退化 §8.8：JTL 中至少 2 个不同 insert_sql 列名片段
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "select count(*) from iot_monitor.meters; select distinct device_id from iot_monitor.meters"
```

## 改动文件清单（R-3 + F-17 + 条件关系初始化 + §1-§6 + §6.4/2docs + §6.4.2全修+B1/B3/B5 基线 d461e40）

```
src/config_parser/models.py                                    # R-2, R-3: QueryConfig.name + validate_foreign_key_refs 用 column NAME
src/ddl_generator/data_type_mapper.py                         # R-1: add "char"
src/ddl_generator/generator.py                                # R-3 续: _ColumnSpec.val_range + _build_foreign_key_clause
src/jmx_skeleton_generator/generators/query_groups.py        # F-11, F-13, F-14, R-2: query_label
src/jmx_skeleton_generator/generators/shared_memory_setup.py # F-12
src/jmx_skeleton_generator/generators/test_plan.py           # F-15, F-16
src/jmx_skeleton_generator/generators/write_groups.py       # F-10
src/jmx_skeleton_generator/generators/ddl_setup.py            # §2 + §6.x + d461e40: generate_ddl_setup_http_thread_group + JSON Extractor + JSR223 PostProcessor + ca_cert_path UDV + §6.4.2 setprop_script null/empty 守卫 + duration→test_duration
src/jmx_skeleton_generator/generators/rest_write_groups.py  # §3 + §6.x + d461e40: InfluxDB Line + ca_cert_path UDV + B1 body-code assertion + B5 ctx.stopThread() 替换 setStopThread(true) + defaultdb→iot_monitor
src/jmx_skeleton_generator/generators/rest_query_groups.py  # §4 + §6.x + d461e40: ca_cert_path UDV + B3 JSONPostProcessor 抽 $.data + JSR223Assertion 检 vars.get('data').size()
src/jmx_skeleton_generator/generators/skeleton.py            # d461e40: §6 DDL/Write/Query TG 装配 + iot_monitor 路由
src/utils/rest_errors.py                                      # d461e40: RestConfigError + missing_ca_cert()（new）
src/utils/xml_helpers.py                                      # d461e40: http_request_sampler_element(...) 通用构造器（new）
src/seed_data_generator/orchestrator.py                      # F-9
src/config_parser/test_parser.py                             # R-3: test_foreign_key_target_exists 改用 pk_int8_1
tests/config_parser/test_rest_api_config.py                  # d461e40: 2 case 覆盖 TLS 必填 + login_password 非空（new）
tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py  # F-10
tests/jmx_skeleton_generator/test_generators.py              # F-14, R-2
tests/jmx_skeleton_generator/test_query_seed_resolution.py         # F-11, F-14
tests/jmx_skeleton_generator/test_shared_memory_setup.py    # F-12 (new)
tests/jmx_skeleton_generator/test_ddl_setup_http_thread_group.py  # §2 + d461e40: 6 case 覆盖 Login/DDL/RelInit/TLS + §6.4.2 token guard
tests/jmx_skeleton_generator/test_rest_write_groups.py       # d461e40: B1 body-code assertion + B5 stopThread 替换 + InfluxDB line (new, 655 行)
tests/jmx_skeleton_generator/test_rest_query_groups.py       # d461e40: B3 $.data 抽取 + size() 断言 (new, 525 行)
tests/kwjdbc_svt/test_main_routes_schemaless_influxdb.py     # d461e40: mode: schemaless_influxdb 路由集成 (new, 111 行)
tests/multi_end_coordination/test_helper_unified.py          # F-10 refactor
tests/multi_end_coordination/test_udv_property_injection.py # F-15, F-16
tests/multi_end_coordination/test_udv_integration.py         # F-15
tests/seed_data_generator/test_orchestrator.py                # F-9
tests/seed_data_generator/test_reference.py                  # R-3: ref: pregenerate
tests/throughput_control/test_udv_integration.py             # F-15
tests/utils/test_http_request_sampler_element.py             # d461e40: 通用 HTTP sampler 构造器 (new, 168 行)
tests/utils/test_rest_errors.py                               # d461e40: RestConfigError.missing_ca_cert (new, 52 行)
tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml                 # R-1/R-3/F-17: Q1 rtag→ptag, NIL, Q4/Q5 rtag_varchar_1 引用 op_group_1..4
tests/kwjdbc_svt/fixtures/test_model_shig.yaml               # R-1/R-3/R-3 续/F-17: 67+49 cols, 3 层 FK, workshop 100 行, t_cnc/t_electmeter 2-3 rtag
tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml         # §6.1: meters measurement, 4 fields + 1 ptag + 2 rtag
tests/kwjdbc_svt/fixtures/test_cfg_schemaless_tls.yaml       # §6.x: https_mode=tls + login_password=root123
.claude/skills/kwjdbc-jmx-smoke/SKILL.md                     # §6: 双模式 + §6.0 TLS 容器重建 + §6.0.1 隔离陷阱 + §6.3 (a)-(e) 断言表 + §6.4 5 条调试（新增 §6.4.5 空 body 诊断 + 反例/防退化）+ 4 docs/refs 交叉引用
docs/issues/F17.md                                            # F-17: 完整 issue 报告
docs/issues/F17Repro.java                                     # F-17: 最小 Java repro
docs/refs/jmx-components-references.md                        # §2: 重写 HTTPSamplerProxy 节为 P0-A/B/C + P1+×2
docs/refs/kaiwudb-schemaless-write-reference.md               # §6 + d461e40: REST API 协议 + 鉴权 + DDL/Write/Query 流程 + §2.0 DB 类型约束 + §3 含 DCR 阶段列
docs/refs/kaiwudb-tls-cert-reference.md                      # §6.0: TLS 证书体系 + kwbase cert 子命令
docs/refs/kaiwudb-kwbase-sql-reference.md                     # 4351c99: kwbase sql 全参数 + 输出格式 + 容器部署后建用户流程
docs/refs/kaiwudb-user-management-reference.md               # 4351c99: CREATE/ALTER/DROP USER + 权限模型 + insecure 限制
openspec/changes/query-naming/{proposal,design,tasks}.md    # R-2 DCR
openspec/changes/conditional-relational-setup/*             # #3 DCR
openspec/changes/rest-schemaless-write/*                    # §1-§6 + d461e40 主 change (proposal/design/tasks + d461e40 微调)
docs/superpowers/plans/2026-07-23-rest-schemaless-write.md    # §2: frontmatter 对齐 guard schema (comet_change + role + canonical_spec) + d461e40 4 行 update
openspec/changes/rest-schemaless-write/tasks.md                # §1-§6 + d461e40 勾选
```
