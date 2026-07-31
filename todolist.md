# 现状与遗留任务（2026-07-29 checkpoint）

> 10 个 fix + 2 个 DCR + R-3（partial + FK DDL 续）+ F-17 + 条件关系初始化 + §1-§5 + §6 insecure-removal + §6 UDV/skill + §6.4 调试填充：上一个稳定基线 `c876acc` / `27b8aec` / `4351c99`。pytest 694/694。本基线新增 2 份 docs/refs + SKILL.md §6.4 4 条调试条目。

遗留：spec gap 19 个未验功能点（按 P1/P2/P3 排序）+ schemaless smoke 后续 3 项。

## 已完成（压缩）

- **F-9 至 F-17 + R-1/R-2/R-3/R-3 续 + #3**（9e285aa / cbc0b8d / ea3dcfe / 3069d9c / e33605e / 09fa065 / 8614b90 / b3e2c5e / 1c02629 / 2c32c81 / d9c3fa9 / 87faab9 / c14969f / 9333117）：10 fix + 2 DCR + R-3 partial + 条件关系初始化。shig smoke 0 err / 4-20-100-3900-3900 / FK 23503 验证 / 0 orphans / pytest 633+10 = 643 pass / sparse 603 samples。
- **§1-§5 (rest-schemaless-write)** (996427f / 71400dc / 67d8f7b / ef2faed / af32312 / 87bf67c / 93d8a18 / dd4a091 / 7b3e904 / 2f2f575 / d481022 / d9c2720 / 5b21cc3 / 92efda5)：HTTP sampler + RestConfigError + SetupTG HTTP DDL pre-create + Write TG (InfluxDB Line) + Query Round-Trip + mode 路由。pytest 666 pass + 6 个新 test_ddl_setup_http_thread_group case。
- **§2 上接** (300d675 / 53adf3b / 06ebb3c / fb99013)：SetupTG HTTP DDL pre-create 落地，fail-fast TLS + ca_cert_path 缺失。
- **§6.x insecure-removal (c876acc)**：schemaless Login 强制非空密码 → 必须 TLS → insecure 路径无解（SQLSTATE 28P01）。`RestApiConfig.https_mode` Literal 收紧 `["tls"]` + ca_cert_path 必填 + 三处 generator 删 insecure 分支 + fixture `test_cfg_schemaless.yaml` 删 + `test_cfg_schemaless_tls.yaml` login_password 改 `root123`。test 5 调整 + 2 新增。16 文件 +306/-241。
- **§6.x UDV/skill sync (27b8aec)**：kwjdbc-jmx-smoke 恢复双模式（JDBC 走 insecure / schemaless 走 TLS 唯一）；ca_cert_path 改 `${__P(rest_api.ca_cert_path,)}` UDV（与 hostname/port 一致），绝对路径 -J 注入；SKILL.md §6 双模式 + §6.0 容器 TLS 重建 + §6.0.1 隔离陷阱 + §6.2 jmeter 命令加必填 -J + §6.4 调试占位。design.md Decision 2 加范围说明。test 2 调整。8 文件 +105/-21。
- **§6.4 调试填充 + 2 docs/refs (4351c99)**：3 次 TLS smoke 实跑沉淀 4 条调试条目（root 无密码 / DDL-2 props.put null / Query 表不存在 cascade / 端口 8080 误报）。新增 2 份 docs/refs：`kaiwudb-kwbase-sql-reference.md` 3.2.0 全参数 + `kaiwudb-user-management-reference.md` CREATE/ALTER/DROP + 权限模型 + insecure 限制。SKILL.md 交叉引用区扩到 4 条。3 文件 +564/-1。

## 遗留真问题

- §6.4.2 DDL-2 失败根因（生成器层 `props.put(K, null)` → Authorization header = `Basic null`）。workaround 已记录在 §6.4.2，待生成器层根治。
- §6.5 insecure ↔ TLS 切换流程尚未落地（容器 cert 导出 / dbs 备份 / 容器销毁重建 / 旧 fixture 清理）。
- §6.3 (a)-(e) 全绿未验证（DDL-2 fix 之前 12/14 pass；fix 后期望 14/14 + DB count + ptag 范围）。

## 🔖 Checkpoint — 2026-07-29（停手，下次续）

**当前 state**：

| 项 | 状态 |
|---|------|
| branch | `feature/20260723/rest-schemaless-write` |
| worktree | `.worktrees/20260723/rest-schemaless-write` |
| base ref | `53adf3b` |
| phase | build（§6.4 调试沉淀 + 2 新 ref docs 已 commit） |
| pytest baseline | 694/694 |
| git status | clean |
| last commit | `4351c99` (docs(skill): link kwbase/user-mgmt refs + fill §6.4 TLS debug) |
| 容器 | `kaiwudb-smoke` 跑 TLS 模式 + `root/root123` + `ca.crt` 拷到 `tests/kwjdbc_svt/fixtures/ca.crt`（gitignored） |
| smoke 实际 | 14 samples / 12 pass / 2 fail（DDL-2 + Query cascade by §6.4.2） |

**下次续 3 件事**（按建议顺序）：

1. **§6.4.2 根因修复**：改 `ddl_setup.py:367` setprop_script 加 null/empty 守卫，pytest 新增 1 项 + 跑 smoke 验 14/14。最小 1 文件 + 1 行。
2. **§6.3 (a)-(e) 全绿验证**：§6.4.2 修后跑 smoke → 验 DB `count(*) from defaultdb.meters` 匹配 + ptag 范围 `device_1..device_10`。
3. **§6.5 insecure ↔ TLS 切换流程**：导出旧 cert / dbs 备份 / 容器销毁 / 旧 fixture cert 清理 / 反向重建。SKILL.md 新增 §6.5。

建议先做 1（最小修复 + 跑通 14/14 验证连接），再做 2（全绿测试），最后 3（流程固化）。

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

## 跑命令模板（schemaless TLS smoke — 2026-07-29 基线）

```bash
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt/.worktrees/20260723/rest-schemaless-write
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

# 预期：14 samples / 12 pass / 2 fail（DDL-2 + Query cascade — §6.4.2 待修）
# §6.4.2 修后期望 14/14 + DB count match + ptag 范围 device_1..device_10
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "select count(*) from defaultdb.meters; select distinct ptag_varchar_1 from defaultdb.meters"
```

**容器镜像**：用 `devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest`（F-17 已修）。`/kaiwudb/bin/kwbase` 绝对路径，`PATH` 里没有。

## 改动文件清单（R-3 + F-17 + 条件关系初始化 + §1-§6 + §6.4/2docs 基线 4351c99）

```
src/config_parser/models.py                                    # R-2, R-3: QueryConfig.name + validate_foreign_key_refs 用 column NAME
src/ddl_generator/data_type_mapper.py                         # R-1: add "char"
src/ddl_generator/generator.py                                # R-3 续: _ColumnSpec.val_range + _build_foreign_key_clause
src/jmx_skeleton_generator/generators/query_groups.py        # F-11, F-13, F-14, R-2: query_label
src/jmx_skeleton_generator/generators/shared_memory_setup.py # F-12
src/jmx_skeleton_generator/generators/test_plan.py           # F-15, F-16
src/jmx_skeleton_generator/generators/write_groups.py       # F-10
src/jmx_skeleton_generator/generators/ddl_setup.py            # §2 + §6.x: generate_ddl_setup_http_thread_group + JSON Extractor + JSR223 PostProcessor + ca_cert_path UDV
src/jmx_skeleton_generator/generators/rest_write_groups.py  # §3 + §6.x: InfluxDB Line + ca_cert_path UDV
src/jmx_skeleton_generator/generators/rest_query_groups.py  # §4 + §6.x: ca_cert_path UDV
src/seed_data_generator/orchestrator.py                      # F-9
src/config_parser/test_parser.py                             # R-3: test_foreign_key_target_exists 改用 pk_int8_1
tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py  # F-10
tests/jmx_skeleton_generator/test_generators.py              # F-14, R-2
tests/jmx_skeleton_generator/test_query_seed_resolution.py         # F-11, F-14
tests/jmx_skeleton_generator/test_shared_memory_setup.py    # F-12 (new)
tests/jmx_skeleton_generator/test_ddl_setup_http_thread_group.py  # §2 (new): 6 case 覆盖 Login/DDL/RelInit/TLS
tests/multi_end_coordination/test_helper_unified.py          # F-10 refactor
tests/multi_end_coordination/test_udv_property_injection.py # F-15, F-16
tests/multi_end_coordination/test_udv_integration.py         # F-15
tests/seed_data_generator/test_orchestrator.py                # F-9
tests/seed_data_generator/test_reference.py                  # R-3: ref: pregenerate
tests/throughput_control/test_udv_integration.py             # F-15
tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml                 # R-1/R-3/F-17: Q1 rtag→ptag, NIL, Q4/Q5 rtag_varchar_1 引用 op_group_1..4
tests/kwjdbc_svt/fixtures/test_model_shig.yaml               # R-1/R-3/R-3 续/F-17: 67+49 cols, 3 层 FK, workshop 100 行, t_cnc/t_electmeter 2-3 rtag
tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml         # §6.1: meters measurement, 4 fields + 1 ptag + 2 rtag
tests/kwjdbc_svt/fixtures/test_cfg_schemaless_tls.yaml       # §6.x: https_mode=tls + login_password=root123
.claude/skills/kwjdbc-jmx-smoke/SKILL.md                     # §6: 双模式 + §6.0 TLS 容器重建 + §6.0.1 隔离陷阱 + §6.4 4 条调试 + 4 docs/refs 交叉引用
docs/issues/F17.md                                            # F-17: 完整 issue 报告
docs/issues/F17Repro.java                                     # F-17: 最小 Java repro
docs/refs/jmx-components-references.md                        # §2: 重写 HTTPSamplerProxy 节为 P0-A/B/C + P1+×2
docs/refs/kaiwudb-schemaless-write-reference.md               # §6: REST API 协议 + 鉴权 + DDL/Write/Query 流程
docs/refs/kaiwudb-tls-cert-reference.md                      # §6.0: TLS 证书体系 + kwbase cert 子命令
docs/refs/kaiwudb-kwbase-sql-reference.md                     # 4351c99: kwbase sql 全参数 + 输出格式 + 容器部署后建用户流程
docs/refs/kaiwudb-user-management-reference.md               # 4351c99: CREATE/ALTER/DROP USER + 权限模型 + insecure 限制
openspec/changes/query-naming/{proposal,design,tasks}.md    # R-2 DCR
openspec/changes/conditional-relational-setup/*             # #3 DCR
openspec/changes/rest-schemaless-write/*                    # §1-§6 主 change
docs/superpowers/plans/2026-07-23-rest-schemaless-write.md    # §2: frontmatter 对齐 guard schema (comet_change + role + canonical_spec)
openspec/changes/rest-schemaless-write/tasks.md                # §1-§6 勾选
```
