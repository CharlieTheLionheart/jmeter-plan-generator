# 现状与遗留任务（2026-07-21 收尾）

> 10 个 fix + 2 个 DCR + 1 个 R-3（partial）+ 1 个 R-3 续（FK DDL + workshop 100）：9e285aa + cbc0b8d + ea3dcfe + 3069d9c + e33605e + 09fa065 + R-3 续待提交。smoke：0 err，4/20/100/3900/3900 填行，FK 约束 23503 验证。pytest 633 passed。

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

## 遗留真问题

- **R-3** shig fixture 关系表未体现 3 层 FK 层级 + t_cnc/t_electmeter rtag→workshop 关联（已落 fixture + validator，rtag 数据见 F-17）
  - 真因：`test_model_shig.yaml` 把 `sub_company` / `factory` / `workshop` 简化为 1/5/5 行无 FK 列；`t_cnc` `regular_tag_count: 0`、`t_electmeter` 只有 `varchar(63)` elect_name 一个 rtag（实际 DDL 是 `workshop_id smallint` + `op_group`）。
  - 生产 schema（192.168.124.51 db_shig_meta）：
    - `sub_company(id INT2 PK, name VARCHAR(32), region VARCHAR(16))` — 4 行（济南/沈阳/武汉/柳州分公司，北方/南方大区）
    - `factory(id INT2 PK, name VARCHAR(16), sub_comp_id INT2 NOT NULL)` — 20 行（每 sub_company 5 个）
    - `workshop(id INT2 PK, name VARCHAR(16), factory_id INT2 NOT NULL)` — 100 行（每 factory 5 个）
    - `t_cnc` rtags: `sub_company_id smallint` + `factory_id smallint` + `workshop_id smallint`
    - `t_electmeter` rtags: `op_group varchar(64)` + `workshop_id smallint` + `cnc_number int`
  - plan.jmx L827-829 显式算 hierarchy：`workshop_id = (threadNum-1)*5 + (deviceNum-1)%5 + 1`，`factory_id = (workshop_id+4)/5`，`sub_company_id = (factory_id+4)/5`
  - 修法（已落地）：
    - `factory.sub_comp_id: ref:db_shig_rel.sub_company.pk_int8_1` (int2)
    - `workshop.factory_id: ref:db_shig_rel.factory.pk_int8_1` (int2)
    - `t_cnc` 加 3 个 smallint rtag: sub_company_id / factory_id / workshop_id（全部 `ref:`）
    - `t_electmeter` 加 1 个 smallint rtag: workshop_id（`ref:`），保留 elect_name 兼容现有 query 的 rtag_varchar_1 引用
    - 数据规模：4 sub_company / 20 factory / 20 workshop（生产 4/20/100，workshop 缩 20 保持 fixture 可读）
  - 副效应：validator 修复（`validate_foreign_key_refs` 改用 `iter_table_columns` 输出 column NAME 而非 col_type，与 `seed_data_generator.reference.build_column_registry` 保持一致；`tests/config_parser/test_parser.py::test_foreign_key_target_exists` 同步更新为 `ref:...pk_int8_1`）
  - 验证：pytest 633 pass + smoke 0 err + 4/20/20 关系表填行 + t_cnc/t_electmeter 3900 行
  - 副作用 F-17：t_electmeter 2 个 rtag 时 `rtag_varchar_1` DB 数据为 `""`（基线 1 rtag 时 NIL/a023 正常）；rtag_smallint_1 仍有值但分布异常（4 个值集中）。CSV/seed/JMX 均正确，疑似 Groovy/JDBC 批处理 + 2 rtag 布局的 setString 绑定回归。**R-3 留 partial fix 状态**，FK 结构 OK 待 F-17 单独修

- **F-17** t_electmeter 2 rtag 时 rtag_varchar_1 setString 绑定失效（**已 root cause，kwdb server bug**）
  - 现象：基线 e33605e（1 rtag）rtag_varchar_1 正常写入 NIL/a023；R-3（2 rtag）后所有行 rtag_varchar_1 = `""`
  - 已排除：seed/CSV/INSERT/columnTypes/loader/ptag-overwrite/direct-psql 全部正确
  - **根因（docs/issues/F17.md + F17Repro.java 完整 repro）**：
    - kwdb server 在时序表有 2+ rtag（含 varchar + smallint）时，`setLong(smallint col)` 之后紧跟 `setString(varchar rtag)` 会让 server 把 varchar rtag 的 value 静默丢弃为 `""`（kwdb/kwdb:latest），或 container restart 时 `MMapTagColumnTable::push_back` segfault（kwdb-x86_64-master-dbg）
    - 关键子发现：`setShort(smallint)` 不触发 bug；只有 `setLong` 触发
    - driver 端 `setString(52, "op_group_3")` 100% 被调用，server 端 silently 忽略
    - 推测：server 缓存 prior bind 的 JDBC type，setLong on SMALLINT 留下"smallint"type hint，下一个 setString 被绑到 SMALLINT 占位符上（被截断为 0/`""`）而不是 VARCHAR
  - 修法（client 侧 workaround）：将 JMX batch_prepared 绑 smallint 改用 setShort 替代 setLong，避开 server bug（生产 fix 等 kwdb 服务端按 `parameterType` hint 修）
  - 已落地：t_electmeter 保持 1 rtag（workshop_id only）；op_group rtag 等 kwdb 修服务端 bug 后再加
  - 关联：t_cnc 的 3 rtag 全 smallint，无 varchar rtag，无 F-17 风险（验证 t_cnc rtag_smallint_1/2/3 写入正常）

## 已删（误判 → 真因）

- ~~L-1 LLM FILTER 方言翻译~~ → 真因 F-14（? 占位符冲突），修了之后 smoke 0 errors
- ~~L-2 last_row(*) JDBC 驱动兼容~~ → 真因 F-14
- ~~L-2 -Jtest_duration=60 不生效~~ → F-15 + F-16
- ~~L-3 Q8-Q12 throughput=1/h vs 短测~~ → 实际生产 test_duration≥8h，无影响
- ~~R-1 shig fixture 列数严重不足~~ → e33605e 已对齐
- ~~R-2 query SQL 命名规则 DCR~~ → e33605e 已落地（openspec/changes/query-naming/）

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

期望：0 err；5/5 表填行（R-3 续后：sub_company=4, factory=20, workshop=100, t_cnc=3900, t_electmeter=3900，**rtag_varchar_1 数据异常见 F-17**）；pytest 633 passed。FK 约束 SQLSTATE 23503 已验证。
任意 UDV 可 `-J<name>=value` 覆盖；ThreadGroup testname 显示为 `query1..query12`。

## 改动文件清单（commit e33605e 终态）

```
src/config_parser/models.py                                    # R-2: QueryConfig.name
src/ddl_generator/data_type_mapper.py                         # R-1: add "char"
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
tests/throughput_control/test_udv_integration.py             # F-15
tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml                 # R-1: Q1 rtag→ptag, NIL
tests/kwjdbc_svt/fixtures/test_model_shig.yaml               # R-1: 67+49 cols 重生成
openspec/changes/query-naming/proposal.md                    # R-2 DCR
openspec/changes/query-naming/design.md                      # R-2 DCR
openspec/changes/query-naming/tasks.md                       # R-2 DCR
```