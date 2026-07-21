# 现状与遗留任务（2026-07-20 收尾）

> 上周 8 个 fix 已在 commit `4e9bbe1`。本轮追加 5 个真 bug fix，commit `9e285aa`。

## 已完成（本轮）

### F-9 PK seed 重复键（FIXED）
- 现象：rel-table PK 列 `val_range="=1"` + `seed_num:1` → seed 文件只有 1 个值，row aggregate cyclic-fill 后 N 行 PK 全是 1 → `duplicate key value (pk_int8_1)=(1) violates unique constraint`
- 修法：`src/seed_data_generator/orchestrator.py` 预计算 `max_seed_num`，PK 列自动扩展 1..N 唯一序列
- 测试：`tests/seed_data_generator/test_orchestrator.py::test_pk_column_with_constant_val_range_gets_unique_values`
- Smoke 验证：factory 5 行、workshop 5 行（之前 0/0）

### F-10 Write ThreadGroup UDV 污染（FIXED）
- 现象：两个 Write TG 都用 `<Arguments>` 定义同名 UDV（table_name/insert_sql/column_types），JMeter JMeterVariables 不按 TG 隔离，第二个 TG 线程读到第一个 TG 的值 → t_cnc 永远 0 行
- 修法：`src/jmx_skeleton_generator/generators/write_groups.py` 把 per-TG 值（table_name / insert_sql / batch_lines / ms_step / first_ptag / column_types）全部 bake 进 Groovy 字面量，消除 UDV 查找
- 测试：`tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py` 4 个新断言
- Smoke 验证：t_cnc 11900、t_electmeter 11900

### F-11 query ${param_N} 空绑定（FIXED）
- 现象：first ptag 没 seed 文件时 PreProcessor 走 `['null']` fallback → `"null".equalsIgnoreCase ? "" : raw` 把 param 绑成空串 → SQL 变 `WHERE ptag_varchar_1 =` → `at or near "EOF": syntax error`
- 修法：`src/jmx_skeleton_generator/generators/query_groups.py` fallback 改 `['device_' + vars.get('device_start')]`，直接 `vars.put(..., raw)` 不再 ternary
- 测试：`tests/jmx_skeleton_generator/test_query_seed_resolution.py::test_param_never_binds_to_empty_string`
- Smoke 验证：EOF 类错误消失

### F-12 SetupThreadGroup.duration 太短（FIXED）
- 现象：`duration=1` 让 5+ 表 SharedMemoryLoader 跑不完就被 scheduler 切断，Write PreProcessor 读到 null → `Cannot invoke method size() on null object`
- 修法：`src/jmx_skeleton_generator/generators/shared_memory_setup.py` 改 60s
- 测试：`tests/jmx_skeleton_generator/test_shared_memory_setup.py` 新增
- Smoke 验证：t_cnc/electmeter sharedRows 不再 null

### F-13 queryArgumentsTypes 数量不匹配（FIXED）
- 现象：JDBCSampler 校验 args 和 types 数量一致，原空 `""` 被算 1 个 type，2-4 个 args 触发 `number of arguments (N) and number of types (1) are not equal`
- 修法：`src/jmx_skeleton_generator/generators/query_groups.py` 按 `param_count` 生成 N 个 VARCHAR
- Smoke 验证：参数查询 200 OK

## 遗留任务

### L-1 LLM FILTER 方言翻译（未做）
- 现象：FILTER (WHERE ...) 在 KaiwuDB 3.2 不支持，5 条 LLM 查询里 4 条报错 `at or near "group": syntax error`
- 选项：
  - A：把 FILTER 改写成 `CASE WHEN`（query 侧翻译）
  - B：DCR 加 "Dialect token" 层，query_groups 支持 FILTER → KaiwuDB native 翻译
  - C：永久排除 FILTER 类查询
- 优先级：P3（与业务对齐后再决）

### L-2 `last_row(*)` JDBC 驱动兼容（未做）
- 现象：505 samples 中 10 个 err 来自 KaiwuDB JDBC prepared statement 对 `last_row(*)` 处理异常（`column index out of range: 1, number of columns: 0`），kwbase sql 直跑同样 SQL OK
- 与本批 fix 无关，建议另开 issue 跟踪 driver 行为

### L-3 跑命令模板（明天可直接复制）

```bash
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
source venv/bin/activate
docker start kaiwudb-smoke 2>&1 | head -1
python -m pytest tests/ 2>&1 | tail -1   # 期望 617 passed

docker exec kaiwudb-smoke ./kwbase sql --insecure -e \
  "delete from db_shig_rel.sub_company; delete from db_shig_rel.factory;
   delete from db_shig_rel.workshop; delete from db_shig.t_cnc;
   delete from db_shig.t_electmeter;"
rm -rf /tmp/jmeter-shig
python -m kwjdbc_svt.main tests/kwjdbc_svt/fixtures/test_model_shig.yaml \
                      tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml \
                      -o /tmp/jmeter-shig
cd /tmp/jmeter-shig && jmeter -n -t test_plan.jmx \
  -Jtest_duration=2 -Jnum_threads=1 -Jdevice_start=1 -Jdevice_per_thread=2 \
  -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
  -l /tmp/jmeter-shig/result.jtl -j /tmp/jmeter-shig/jmeter.log
docker exec kaiwudb-smoke ./kwbase sql --insecure -e \
  "select 'sub_company' t, count(*) c from db_shig_rel.sub_company
   union all select 'factory', count(*) from db_shig_rel.factory
   union all select 'workshop', count(*) from db_shig_rel.workshop
   union all select 't_cnc', count(*) from db_shig.t_cnc
   union all select 't_electmeter', count(*) from db_shig.t_electmeter;"
```

期望：5 表全部填行；pytest 617 passed。

## 改动文件清单（已 commit 9e285aa）

```
src/jmx_skeleton_generator/generators/query_groups.py        # F-11, F-13
src/jmx_skeleton_generator/generators/shared_memory_setup.py # F-12
src/jmx_skeleton_generator/generators/write_groups.py       # F-10
src/seed_data_generator/orchestrator.py                      # F-9
tests/jmx_skeleton_generator/test_batch_prepared_typed_binding.py  # F-10
tests/jmx_skeleton_generator/test_query_seed_resolution.py         # F-11
tests/jmx_skeleton_generator/test_shared_memory_setup.py    # F-12 (new)
tests/multi_end_coordination/test_helper_unified.py          # F-10 refactor
tests/seed_data_generator/test_orchestrator.py                # F-9
```