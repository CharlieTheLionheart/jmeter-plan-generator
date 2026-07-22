# 现状与遗留任务（2026-07-22 收尾）

> 10 个 fix + 2 个 DCR + R-3（partial + FK DDL 续）+ F-17（已在 nightly master 修）：9e285aa + cbc0b8d + ea3dcfe + 3069d9c + e33605e + 09fa065 + 8614b90 + b3e2c5e + 1c02629 + 2c32c81 + d9c3fa9 + 87faab9。smoke：0 err，4/20/100/3900/3900 填行，FK 约束 23503 验证，FK 完整性 0 orphans。pytest 633 passed。

遗留：spec gap 19 个未验功能点（按 P1/P2/P3 排序）。

## 已完成（压缩）

- **F-9** (9e285aa) PK 重复键：`val_range="=1"`+`seed_num:1` → 1..max_seed 自动扩展。test: `test_orchestrator::test_pk_column_with_constant_val_range_gets_unique_values`。smoke: factory 5、workshop 5。
- **F-10** (9e285aa) Write TG UDV 污染：per-TG 值 bake 进 Groovy 字面量。test: `test_batch_prepared_typed_binding` 4 新断言。smoke: t_cnc/electmeter 11900。
- **F-11** (9e285aa) `${param_N}` 空绑：fallback 改 `device_<start>`，去 ternary。test: `test_param_never_binds_to_empty_string`。smoke: EOF 错误消失。
- **F-12** (9e285aa) SetupTG.duration=1 太短：→ 60s。test: `test_shared_memory_setup` 新增。smoke: sharedRows 不再 null。
- **F-13** (9e285aa) queryArgumentsTypes 空 → 数量不匹配：按 param_count 生成 N 个 VARCHAR。smoke: 参数查询 200。
- **F-14** (cbc0b8d) **关键** ? 占位符 + raw 值绑：保留 `?` + raw 值剥 QUOTE_ALL 双引号直接 `setString`。test: 3 个新断言。smoke: 0 err。
- **F-15** (ea3dcfe) UDV 默认值 → `${__P(name,default)}`：UDV 优先于 JMeter property 导致 `-J<name>` 失效。test: `test_udv_uses_property_reference` 5 parametrize。smoke: `-Jtest_duration=60` 跑 61s。
- **F-16** (3069d9c) 凭证也走 `${__P(...)}`：raw literal 默认（不加 `!r` 引号）。空默认用 `${__P(name,)}`（逗号后留空），不是 `${__P(name)}`（会被 `"1"` 兜底）。test: 2 新断言。smoke: 默认 0 err。
- **R-1** (e33605e) shig fixture 列数对齐 develop-2.0 db_shig：t_cnc 67 列 + t_electmeter 49 列按真实类型比例分配；副效应 DDL 加 char 类型支持、regular_tag 改 varchar(63)、rtag val_range 改 NIL、Q1 rtag 改 ptag_varchar_2。test: pytest 仍全 pass。smoke: 5/5 表填行。
- **R-2** (e33605e) query SQL 命名 DCR：`QueryConfig.name` 可选字段；按模板顺序默认命名为 query1/query2/...。openspec/changes/query-naming/ 三件套（proposal/design/tasks）。test: 3 新断言。smoke: JMX testname 显示 query1..query12。
- **R-3** (09fa065) shig fixture 关系表 3 层 FK 层级 + t_cnc/t_electmeter rtag→workshop 关联：sub_company 4 行 + factory 20 行 + workshop 20 行（生产 100 缩 20 保持可读），t_cnc 加 3 rtag（sub_company_id + factory_id + workshop_id 全 smallint ref:），t_electmeter 加 2 rtag（op_group varchar + workshop_id smallint ref:），validator 修复（`validate_foreign_key_refs` 改用 column NAME 而非 col_type）。test: 同步更新 test_parser + smoke 0 err。
- **R-3 续** (8614b90) ddl_generator 加 FK 约束：data_col val_range 为 `ref:db.table.col` 时 DDL 附加 `REFERENCES db.table(col)` 子句；workshop 20→100 行（生产 100 车间名 enum + factory_id ref:）。DDL 实际生成 `CONSTRAINT fk_col_int2_1_ref_factory FOREIGN KEY (col_int2_1) REFERENCES factory(pk_int8_1)`。test: 验 workshop.factory_id=999 / factory.sub_comp_id=999 → SQLSTATE 23503 违反。pytest 633 pass + smoke 0 err + 4/20/100/3900/3900 填行。
- **F-17** (b3e2c5e / 1c02629 / 2c32c81 / d9c3fa9) kwdb server tag insert bug：在 2+ rtag 时序表（含 varchar + smallint）下，`setLong(smallint col)` 之后紧跟 `setString(varchar rtag)` 会让 server 把 varchar rtag 静默丢弃为 `""`（kwdb/kwdb:latest）或 container restart 时 `MMapTagColumnTable::push_back` segfault（kwdb-x86_64-master-dbg）。docs/issues/F17.md + F17Repro.java 完整 repro。`setShort(smallint)` 不触发；bug 仅限 JDBC `setLong → setString` 序列，原生 `kwbase sql` 不复现。**FIXED in `kwdb-x86_64-master:latest` (nightly 2026-07-22)**：F17Repro 2500 rows + rtag_varchar_1 = op_group_1..4 正确分布；shig smoke 4/20/100/3900/3900 + rtag_varchar_1 = op_group_2/3/4 + rtag_smallint_1 = 13/33/61。FK 完整性验 0 orphans。
- **#3** (c14969f / 9333117) **条件关系初始化 DCR**：`TestModelConfig` 未声明 `rel_dbs`、空 `rel_dbs` 或所有关系表为空时，生成器不生成任何 `RelInit_` 子树。同步 `batch_prepared` 修复：`setObject(colIdx+1, null)` 替 `setNull`；4000 列 INSERT SQL 按 16KB 分块为 Groovy 多字符串常量并运行时 `[..].join('')`。OpenSpec change `conditional-relational-setup`（proposal/design/review/tasks/delta spec/.openspec.yaml）+ Superpowers Design Doc + 实施 plan。test: pytest 643 passed（新增 8 项条件初始化集成断言 + 1 项 NULL `setObject` 锁定 + 1 项 SQL 拆分）。smoke: 5min sparse KaiwuDB 603 samples/0 errors/t_cnc 600 行 + 99% NULL 种子 + DB 非 NULL 行数符合随机分布；shig canonical smoke 0 errors（factory/workshop=0 属批次循环限制，与本 DCR 无关）。原始 spec §2.0/§2.2/§写入范围说明 与 design §1 决策 3/§3.6/线程组编排节 三处补齐边界。

## 遗留真问题

无。所有 R-3 + F-17 已落 commit 并验证通过；spec gap #3 已落 commit `c14969f` 与 `9333117` 并验证通过。下一阶段工作见末尾"spec 未验功能点"（19 个待验，按 P1/P2/P3 排序）。

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
- **#3** `nullable=true` + `null_rate>0` 已验。sparse 4000 列 99% NULL fixture 落 commit `c14969f` / `9333117`，smoke 603 samples / 0 errors，col_smallint_1/col_int_1/col_float4_1 NULL 种子比例 99%，DB 非 NULL 行数符合随机分布。
- **#4** `enum` 多种子数（`seed_num > len(enum_values)` 时循环填充）未验。shig rtag_varchar 4 值 seed=4 刚好命中，未触发循环分支。
- **#5** `regex` val_range 未验。shig 全 enum/int range。

### P2：跨表/跨 db
- **#6** `ref:` 跨 db 引用未验。shig 全 db_shig_rel 内部引用，未跨时序库引用关系库。spec §2.0 允许。
- **#7** 跨 db JOIN 未验。shig Q10 JOIN 是 t_cnc/t_electmeter（同 db）；spec 示例有 iot_monitor + iot_metadata JOIN。

### P2：查询
- **#8** 多 `?` 占位符独立采样未验。shig Q4/Q5 都只 1 个 `?` bind ptag。
- **#9** 未关联列的 `?` 报错未验。spec §2.0 备注明确 `LIMIT ?` 等应在生成阶段报错。

### P3：约束/边界
- **#10** `retentions` 表级覆盖库级未验。shig 全库级 1d。
- **#11** Tag varchar 上限 128 字节未验。shig rtag varchar(64)。
- **#12** Primary Tag 上限 4 列 + varchar 128 字节未验。shig 1 ptag。
- **#13** WITH HASH 必须在 DDL 末尾未对比反例。shig 都是末尾。
- **#14** WITH HASH 范围 1-50000 + 推荐值表未验。shig 4。

### P3：协同/独立变量
- **#15** 多端协同（多 JMeter 端 + device_start 分割设备号）未验。shig 单端。
- **#16** 多表独立 num_threads 未验（spec §1.6 明确当前版本不支持，follow-up）。

### P3：验收/错误
- **#17** §6.2 配置错误清晰提示未系统测过。
- **#18** §6.2 代码覆盖率 > 80% 未验（pytest 633 pass 不代表覆盖率达标）。
- **#19** §6.1 各表数据列类型分布 ±5% 偏差未单独验（smoke 通过不代表分布精度）。

下一步建议：先验 **#1 多种写入模式** + **#3 nullable+null_rate** + **#2 schemaless 报错**。这三个是 P1 且不依赖新 fixture 改写（可用 shig 切 mode 测，或写一个新 fixture）。

## 跑命令模板（R-1/R-2 之后）

```bash
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
source venv/bin/activate
docker start kaiwudb-smoke 2>&1 | head -1
python -m pytest tests/ 2>&1 | tail -1   # 633 passed

# R-1 之后建议 drop database（schema 变了，旧表会触发 char(30) 等 DDL 错误）
docker exec kaiwudb-smoke ./kwbase sql --insecure -e \
  "drop database db_shig_rel cascade; drop database db_shig cascade;"
rm -rf /tmp/jmeter-shig
python -m kwjdbc_svt.main tests/kwjdbc_svt/fixtures/test_model_shig.yaml \
                      tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml \
                      -o /tmp/jmeter-shig
cd /tmp/jmeter-shig && jmeter -n -t test_plan.jmx \
  -Jtest_duration=10 -Jnum_threads=1 -Jdevice_start=1 -Jdevice_per_thread=1 \
  -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
  -l /tmp/r-final.jtl -j /tmp/j-final.log
docker exec kaiwudb-smoke ./kwbase sql --insecure -e \
  "select 'sub_company' t, count(*) c from db_shig_rel.sub_company
   union all select 'factory', count(*) from db_shig_rel.factory
   union all select 'workshop', count(*) from db_shig_rel.workshop
   union all select 't_cnc', count(*) from db_shig.t_cnc
   union all select 't_electmeter', count(*) from db_shig.t_electmeter;"
```

期望：0 err；5/5 表填行（sub_company=4, factory=20, workshop=100, t_cnc=3900, t_electmeter=3900）；pytest 633 passed。FK 约束 SQLSTATE 23503 + FK 完整性 0 orphans 验证。任意 UDV 可 `-J<name>=value` 覆盖；ThreadGroup testname 显示为 `query1..query12`。

**容器镜像**：用 `kwdb/kwdb:latest` 或 `devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest`（F-17 已修）。`kwdb/kwdb:latest` + `kwdb-x86_64-master-dbg:latest` 仍含 F-17 bug。

## 改动文件清单（R-3 + F-17 收尾后）

```
src/config_parser/models.py                                    # R-2, R-3: QueryConfig.name + validate_foreign_key_refs 用 column NAME
src/ddl_generator/data_type_mapper.py                         # R-1: add "char"
src/ddl_generator/generator.py                                # R-3 续: _ColumnSpec.val_range + _build_foreign_key_clause
src/jmx_skeleton_generator/generators/query_groups.py        # F-11, F-13, F-14, R-2: query_label
src/jmx_skeleton_generator/generators/shared_memory_setup.py # F-12
src/jmx_skeleton_generator/generators/test_plan.py           # F-15, F-16
src/jmx_skeleton_generator/generators/write_groups.py       # F-10
src/seed_data_generator/orchestrator.py                      # F-9
tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py  # F-10
tests/jmx_skeleton_generator/test_generators.py              # F-14, R-2
tests/jmx_skeleton_generator/test_query_seed_resolution.py         # F-11, F-14
tests/jmx_skeleton_generator/test_shared_memory_setup.py    # F-12 (new)
tests/multi_end_coordination/test_helper_unified.py          # F-10 refactor
tests/multi_end_coordination/test_udv_property_injection.py # F-15, F-16
tests/multi_end_coordination/test_udv_integration.py         # F-15
tests/seed_data_generator/test_orchestrator.py                # F-9
tests/seed_data_generator/test_reference.py                  # R-3: ref: pregenerate
tests/throughput_control/test_udv_integration.py             # F-15
tests/config_parser/test_parser.py                           # R-3: test_foreign_key_target_exists 改用 pk_int8_1
tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml                 # R-1/R-3/F-17: Q1 rtag→ptag, NIL, Q4/Q5 rtag_varchar_1 引用 op_group_1..4
tests/kwjdbc_svt/fixtures/test_model_shig.yaml               # R-1/R-3/R-3 续/F-17: 67+49 cols, 3 层 FK, workshop 100 行, t_cnc/t_electmeter 2-3 rtag
.claude/skills/kwjdbc-jmx-smoke/SKILL.md                     # F-17: 镜像换 kwdb/kwdb:latest + /kaiwudb/bin/kwbase start-single-node
docs/issues/F17.md                                            # F-17: 完整 issue 报告
docs/issues/F17Repro.java                                     # F-17: 最小 Java repro
openspec/changes/query-naming/{proposal,design,tasks}.md    # R-2 DCR
```