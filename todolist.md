# 现状与遗留任务（2026-07-21 收尾）

> 6 个 fix 在 commit `9e285aa` + `cbc0b8d`。本轮 smoke：505 samples, 0 errors, 5/5 表填行。

## 已完成

### F-9 PK seed 重复键（FIXED, 9e285aa）
- 现象：`val_range="=1"` + `seed_num:1` → row aggregate cyclic-fill 后 N 行 PK 全 1 → duplicate key
- 修法：`src/seed_data_generator/orchestrator.py` PK 列自动扩展 1..max_seed
- 测试：test_orchestrator::test_pk_column_with_constant_val_range_gets_unique_values
- Smoke：factory 5、workshop 5（之前 0/0）

### F-10 Write ThreadGroup UDV 污染（FIXED, 9e285aa）
- 现象：两个 Write TG 同名 UDV → 第二个 TG 读到第一个 TG 的值 → t_cnc 0 行
- 修法：`src/jmx_skeleton_generator/generators/write_groups.py` per-TG 值（table_name/insert_sql/batch_lines/ms_step/first_ptag/column_types）全部 bake 进 Groovy 字面量
- 测试：test_batch_prepared_typed_binding.py 4 个新断言
- Smoke：t_cnc 11900、t_electmeter 11900

### F-11 ${param_N} 空绑定（FIXED, 9e285aa）
- 现象：first ptag fallback `['null']` → `"null".equalsIgnoreCase ? "" : raw` 把 param 绑空 → SQL 变 `WHERE ptag_varchar_1 =` → at-or-near-EOF
- 修法：fallback 改 `['device_' + vars.get('device_start')]`，去掉 ternary
- 测试：test_query_seed_resolution.py::test_param_never_binds_to_empty_string
- Smoke：EOF 类错误消失

### F-12 SetupThreadGroup.duration 太短（FIXED, 9e285aa）
- 现象：`duration=1` 切线程太早，Write PreProcessor 读到 null → NPE on sharedRows.size()
- 修法：`src/jmx_skeleton_generator/generators/shared_memory_setup.py` 改 60s
- 测试：tests/jmx_skeleton_generator/test_shared_memory_setup.py 新增

### F-13 queryArgumentsTypes 数量不匹配（FIXED, 9e285aa）
- 现象：空 `""` 被算 1 个 type，2-4 args → number of arguments (N) and number of types (1)
- 修法：按 param_count 生成 N 个 VARCHAR

### F-14 ? 占位符 + raw 值绑（FIXED, cbc0b8d）— 关键
- 现象：原来把 `?` 改写 `${param_N}` 让 JMeter 替换，但 `Prepared Select Statement` 已走 positional bind → 两层替换冲突，result-set metadata 返 0 列 → 22023 覆盖 10/10 带参查询（不只是 last_row）
- 修法：SQL 保留 `?` 占位符（新增 _count_placeholders），raw 值剥 QUOTE_ALL 双引号直接 `setString`
- 测试：test_query_keeps_question_mark_placeholders + test_seed_value_strips_quote_all_double_quotes + test_query_arguments_types_count_matches
- Smoke：0 errors

## 遗留真问题（2026-07-21 验证）

### L-1 LLM FILTER 方言翻译（未做，P3）
- 现象：FILTER (WHERE ...) KaiwuDB 3.2 不支持
- 受影响：Q13（FILTER + INTERVAL 双表 JOIN），Q14（UNION ALL + MIN/MAX 子查询，4 占位符）
- 当前状态：smoke 60s 内 Q13/Q14 throughput=0.0167/min (=1/hour) 没触发，被掩盖
- 验证方式：手动将 throughput 调到 ≥4/min 跑一次会看到 42601 `at or near "group": syntax error`
- 选项：
  - A：query 侧 FILTER → `CASE WHEN agg(...) FILTER (WHERE ...) END` 翻译
  - B：DCR 加 "Dialect token" 层
  - C：永久排除 FILTER 类
- 优先级：与业务对齐再决

### L-2 `-Jtest_duration=60` 不生效（未做，P2）
- 现象：`tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml` 的 `conn_config.test_duration: 30` 写入 JMX UDV，JMeter `-Jtest_duration=60` 设的是 property，不覆盖 UDV
- 验证：`-Jtest_duration=60` 跑 smoke，summary 还是 31s（不是 60s）
- 影响：CLI 调时长失效，用户只能改 UDV 或 JMX
- 修法选项：
  - A：JMX 里把 `${test_duration}` 改成 `${__property(test_duration,30)}`（property 优先于 UDV）
  - B：main.py CLI 加 `--duration` 直接编辑 JMX 字面量
- 优先级：P2

### L-3 Q8-Q12 throughput=1/小时 设计 vs 短测（未做，P3）
- 现象：5 条 LLM 查询 throughput=0.0167/min（=1/小时）设计意图是 1h 测里只跑 1 次。但 `test_duration=30s` 短测下完全不触发，掩盖 L-1 真 bug
- 修法选项：
  - A：fixture throughput 调成 0.5-1/min 让 30s 短测也能触发 1 次
  - B：fixture 加注释说明"必须 test_duration≥1h 才覆盖 LLM 查询"
- 优先级：P3

## 已删（误判为真 bug，实际不是）

~~L-2 last_row(*) JDBC 驱动兼容~~ — 实际是 F-14（? 占位符 + raw 值绑），已修

## 跑命令模板

```bash
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
source venv/bin/activate
docker start kaiwudb-smoke 2>&1 | head -1
python -m pytest tests/ 2>&1 | tail -1   # 620 passed

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

期望：5 表填行；pytest 620 passed；0 errors（LLM throughput=1/h 不触发除外）。

## 改动文件清单（commit 9e285aa + cbc0b8d）

```
src/jmx_skeleton_generator/generators/query_groups.py        # F-11, F-13, F-14
src/jmx_skeleton_generator/generators/shared_memory_setup.py # F-12
src/jmx_skeleton_generator/generators/write_groups.py       # F-10
src/seed_data_generator/orchestrator.py                      # F-9
tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py  # F-10
tests/jmx_skeleton_generator/test_generators.py              # F-14
tests/jmx_skeleton_generator/test_query_seed_resolution.py         # F-11, F-14
tests/jmx_skeleton_generator/test_shared_memory_setup.py    # F-12 (new)
tests/multi_end_coordination/test_helper_unified.py          # F-10 refactor
tests/seed_data_generator/test_orchestrator.py                # F-9
```