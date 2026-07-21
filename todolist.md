# 现状与遗留任务（2026-07-21 收尾）

> 8 个 fix：9e285aa + cbc0b8d + ea3dcfe + 3069d9c。smoke：505/0 err，5/5 表填行。pytest 630 passed。

## 已完成（压缩）

- **F-9** (9e285aa) PK 重复键：`val_range="=1"`+`seed_num:1` → 1..max_seed 自动扩展。test: `test_orchestrator::test_pk_column_with_constant_val_range_gets_unique_values`。smoke: factory 5、workshop 5。
- **F-10** (9e285aa) Write TG UDV 污染：per-TG 值 bake 进 Groovy 字面量。test: `test_batch_prepared_typed_binding` 4 新断言。smoke: t_cnc/electmeter 11900。
- **F-11** (9e285aa) `${param_N}` 空绑：fallback 改 `device_<start>`，去 ternary。test: `test_param_never_binds_to_empty_string`。smoke: EOF 错误消失。
- **F-12** (9e285aa) SetupTG.duration=1 太短：→ 60s。test: `test_shared_memory_setup` 新增。smoke: sharedRows 不再 null。
- **F-13** (9e285aa) queryArgumentsTypes 空 → 数量不匹配：按 param_count 生成 N 个 VARCHAR。smoke: 参数查询 200。
- **F-14** (cbc0b8d) **关键** ? 占位符 + raw 值绑：`?` 改写 `${param_N}` 与 PreparedStatement positional bind 冲突 → result-set metadata 0 列（22023 覆盖 10/10 带参）。修法：保留 `?`，新增 `_count_placeholders`；raw 值剥 QUOTE_ALL 双引号直接 `setString`。test: 3 个新断言。smoke: 0 err。
- **F-15** (ea3dcfe) UDV 默认值 → `${__P(name,default)}`：UDV 优先于 JMeter property 导致 `-J<name>` 失效。test: `test_udv_uses_property_reference` 5 parametrize。smoke: `-Jtest_duration=60` 跑 61s。
- **F-16** (3069d9c) 凭证也走 `${__P(...)}`：raw literal 默认（不加 `!r` 引号，参考 `scenarios/shig/plans/plan.jmx`）。空默认用 `${__P(name,)}`（逗号后留空），不是 `${__P(name)}`（会被 `"1"` 兜底）。test: 2 新断言。smoke: 默认 0 err；`-Jdb_url=...wrong...` 触发 Connection refused 证明覆盖生效。

## 遗留真问题（2026-07-21 新增）

### R-1 shig fixture 列数严重不足（未做，P1）
- 用户反馈：之前按 plan.jmx 生成的 `test_model_shig.yaml` 列数差太多
- 真实模型：`develop-2.0` 分支 `resources/db_shig/`
  - `t_cnc` 30+ 列（cnc_sn / sp_set_speed / sp_act_speed / cnc_cycletime 等业务列）
  - `t_electmeter` 60+ 列（vol_a/b/c / cur_a/b/c / allenergy_a/b/c 等）
  - `.meta` 文件含 primary tag 列表
- 当前 fixture 只有 1+1+8 列（ptag/rtag/col_float4_*）
- 修法：从 develop-2.0 `resources/db_shig/t_cnc` + `t_electmeter` 重新生成
  `test_model_shig.yaml`，列数与真实模型对齐；test_cfg_shig.yaml 的 SQL 也对应重写

### R-2 query SQL 命名规则 DCR（未做，P2）
- 用户反馈：当前 query ThreadGroup testname 用截断 SQL 文本（`[Query] SELECT ts, col_float4_1 FROM db_shi...`），沟通失败 SQL 时不方便定位
- 修法（DCR）：
  - QueryConfig 加可选字段 `name: str`（默认 None）
  - 生成器规则：若 `name` 存在则用 `name`；否则按模板顺序命名为 `query1` / `query2` / ...
  - ThreadGroup testname = `[Query] {name}`，JDBCSampler testname = `[Query]` 保持不变
  - 同步更新 fixture 注释（Q1/Q2/... → 不再写 query 注释；用 name 字段）

## 已删（误判 → 真因）

- ~~L-1 LLM FILTER 方言翻译~~ → 真因 F-14（? 占位符冲突），修了之后 smoke 0 errors，Q11 FILTER 查询实测可执行（plan.jmx 第 4641-4642 行 `AVG(cur_a) FILTER (WHERE ...)`，用户 GUI 手动跑也能出结果）
- ~~L-2 last_row(*) JDBC 驱动兼容~~ → 真因 F-14
- ~~L-2 -Jtest_duration=60 不生效~~ → F-15 + F-16
- ~~L-3 Q8-Q12 throughput=1/h vs 短测~~ → 实际生产 test_duration≥8h，无影响；后续如有反馈再处理

## 跑命令模板

```bash
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
source venv/bin/activate
docker start kaiwudb-smoke 2>&1 | head -1
python -m pytest tests/ 2>&1 | tail -1   # 630 passed

docker exec kaiwudb-smoke ./kwbase sql --insecure -e \
  "delete from db_shig_rel.sub_company; delete from db_shig_rel.factory;
   delete from db_shig_rel.workshop; delete from db_shig.t_cnc;
   delete from db_shig.t_electmeter;"
rm -rf /tmp/jmeter-shig
python -m kwjdbc_svt.main tests/kwjdbc_svt/fixtures/test_model_shig.yaml \
                      tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml \
                      -o /tmp/jmeter-shig
cd /tmp/jmeter-shig && jmeter -n -t test_plan.jmx \
  -Jtest_duration=30 -Jnum_threads=1 -Jdevice_start=1 -Jdevice_per_thread=2 \
  -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
  -l /tmp/jmeter-shig/result.jtl -j /tmp/jmeter-shig/jmeter.log
docker exec kaiwudb-smoke ./kwbase sql --insecure -e \
  "select 'sub_company' t, count(*) c from db_shig_rel.sub_company
   union all select 'factory', count(*) from db_shig_rel.factory
   union all select 'workshop', count(*) from db_shig_rel.workshop
   union all select 't_cnc', count(*) from db_shig.t_cnc
   union all select 't_electmeter', count(*) from db_shig.t_electmeter;"
```

期望：5 表填行；pytest 630 passed；0 errors（LLM 1/h 不触发除外）。任意 UDV 可 `-J<name>=value` 覆盖。

## 改动文件清单

```
src/jmx_skeleton_generator/generators/query_groups.py        # F-11, F-13, F-14
src/jmx_skeleton_generator/generators/shared_memory_setup.py # F-12
src/jmx_skeleton_generator/generators/test_plan.py           # F-15, F-16
src/jmx_skeleton_generator/generators/write_groups.py       # F-10
src/seed_data_generator/orchestrator.py                      # F-9
tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py  # F-10
tests/jmx_skeleton_generator/test_generators.py              # F-14
tests/jmx_skeleton_generator/test_query_seed_resolution.py         # F-11, F-14
tests/jmx_skeleton_generator/test_shared_memory_setup.py    # F-12 (new)
tests/multi_end_coordination/test_helper_unified.py          # F-10 refactor
tests/multi_end_coordination/test_udv_property_injection.py # F-15, F-16
tests/multi_end_coordination/test_udv_integration.py         # F-15
tests/seed_data_generator/test_orchestrator.py                # F-9
tests/throughput_control/test_udv_integration.py             # F-15
```