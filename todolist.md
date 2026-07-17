# 现状与遗留任务（2026-07-17 收尾）

## 重启后要重新做的

> **关键**：关机重启后工作树里的修改**不会丢**（未 commit 也是 .git/objects 上的 fs），但运行的中间件会丢。

| 项 | 重启后要做 | 命令 |
|----|-----------|------|
| venv | 不需要重装；`source venv/bin/activate` | `source venv/bin/activate` |
| KaiwuDB Docker 容器 | 容器**已停**（除非 docker restart=on-failure），需要重新拉起 | `docker start kaiwudb-smoke`（或 `docker run -d --name kaiwudb-smoke -p 26257:26257 kaiwudb/kaiwudb:3.2.0 --cluster-name=test-single`） |
| JMeter | 已结束，可直接复用 | `which jmeter`（应仍在 `/usr/bin/jmeter`） |
| `/tmp/jmeter-shig/` | **丢了**——重新生成 | `rm -rf /tmp/jmeter-shig && python -m kwjdbc_svt.main tests/kwjdbc_svt/fixtures/test_model_shig.yaml tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml -o /tmp/jmeter-shig` |
| DB 表行数 | 上次测后**留着**（Docker 持久化 volume），如要重测先清空 | 见下面 §6"待跑命令" |
| 工作树修改 | **不丢**——`git status` 看是否还在 | `git status`（应有上面 §9 改动清单的 9 文件 dirty） |

### 快捷自检脚本（粘贴到新 shell）

```bash
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
source venv/bin/activate
docker start kaiwudb-smoke 2>&1 | head -1
git status --short | head -20
python -m pytest tests/ 2>&1 | tail -3
```

期望：
- `docker start` 输出 `kaiwudb-smoke` / IDs
- `git status` 应列 8-9 个修改文件
- `pytest` 输出 `608 passed`

如果 `git status` 为空（工作树被 reset 过），按下面 §9 从 git reflog 拿回。

### 工作树丢了从 reflog 拿回的应急

```bash
git reflog --all | head -20          # 找最近的 dirty HEAD
git stash list                       # 找之前 stash
git stash apply stash@{0}            # 或 git checkout <commit> -- <file>
```

或者最坏情况下重做所有 FIX（按 §"改动文件清单" 重新应用补丁）。

## 已修复（未 commit）

### 1. parser EOF-on-quote bug（FIXED）
- 文件：[src/jmx_skeleton_generator/generators/query_groups.py](src/jmx_skeleton_generator/generators/query_groups.py)
- 现象：SQL 末尾是闭合 `'`（如 `INTERVAL '1 hour'`）被误判为未结束字符串
- 修法：内层 while 加 `closed` flag，区分闭合 break vs EOF 失效
- 测试：[tests/jmx_skeleton_generator/test_query_state_machine.py](tests/jmx_skeleton_generator/test_query_state_machine.py) `test_string_literal_ending_at_eof_is_closed` + `test_double_quoted_identifier_ending_at_eof_is_closed`
- 状态：18 passed

### 2. ColumnNamer N-aligned types bug（FIXED）
- 文件：[src/column_namer/namer.py](src/column_namer/namer.py) + [src/jmx_skeleton_generator/generators/write_groups.py](src/jmx_skeleton_generator/generators/write_groups.py)
- 现象：`data_col_count=8` 单 entry float4 → column_types UDV 仅 1 个 float4 → loader 把 col_float4_2..8 当 VARCHAR → `KSQLException: could not resolve "33519.88" as FLOAT4`
- 修法：
  - `ColumnNamer._build` 同步记录 `self._types` per-name
  - 加 `types_per_name` 属性 + `__call__` 返回 `(names, types_per_name, index_map)`
  - `write_groups.py` 用 `column_types = [ts] + all_types_per_name`
- 测试：[tests/column_namer/test_namer.py](tests/column_namer/test_namer.py) `test_types_per_name_one_entry_many_columns` + `test_types_per_name_parity_across_groups`
- 状态：9 passed

### 3. JDBCDataSource 字面 → `${db_url}` 引用（FIXED）
- 文件：[src/jdbc_datasource/jdbc_data_source_generator.py](src/jdbc_datasource/jdbc_data_source_generator.py)
- 现象：`dbUrl` 字面 jdbc URL，`-Jdb_url` 完全无效
- 修法：`db_url = "${db_url}"`、`db_username = "${db_username}"`、`db_password = "${db_password}"`，UDV 走默认 `jdbc:kaiwudb://127.0.0.1:26257/defaultdb`
- 测试：[tests/jdbc_datasource/test_jdbc_data_source_generator.py](tests/jdbc_datasource/test_jdbc_data_source_generator.py) `TestDbUrlAlwaysVariableReference` + 旧测试改成"default → variable reference"语义
- 状态：JDBCD 源测试通过

### 4. rel-table init sampler 缺发（FIXED）
- 文件：[src/jmx_skeleton_generator/generators/ddl_setup.py](src/jmx_skeleton_generator/generators/ddl_setup.py)、[src/jmx_skeleton_generator/generators/skeleton.py](src/jmx_skeleton_generator/generators/skeleton.py)、[src/kwjdbc_svt/main.py](src/kwjdbc_svt/main.py)
- 现象：spec §3.6 要求关表一次 INSERT，生成器漏发 → sub_company/factory/workshop 永远空
- 修法：
  - `ddl_setup.py` 增 `_build_rel_init_subtree(spec)`：LoopController + JSR223 PreProcessor + Prepared Update JDBCSampler
  - `skeleton.py` 加 `rel_init_specs` 透传
  - `main.py` 加 `_build_relational_init_specs(model)`：每个 rel table 一条 spec，自动算 `total_rows = max(seed_num)`、`batch_lines = largest_divisor_le(100)`、按 `iter_table_columns` 顺序拼 columns + rel_col_seed_files + column_types（JDBC mapped）
- 状态：pytest 608 passed；smoke 跑通生成

### 5. RelInit PreProcessor 子路径 bug（FIXED，调试中发现）
- 文件：[src/direct_insert_write/preprocessor_generator.py](src/direct_insert_write/preprocessor_generator.py)
- 现象：path 拼 `seeds/db_shig_rel.sub_company/...`（点当子目录）但实际是 `seeds/db_shig_rel/sub_company/...`（斜杠）
- 修法：`fs_subdir = table_name.replace('.', '/')`，路径用 `seedDir + '/' + fsSubdir + '/' + filename`

### 6. `__rel_batch_idx` 表间 bleed-over（FIXED，调试中发现）
- 现象：第二个 rel init sampler 继承第一 sampler 的 batch_idx，导致空批
- 修法：key 改为 `__rel_batch_idx_${table.replace('.', '_')}` 每表独立

### 7. `int8` 非 JDBC 类型名（FIXED，调试中发现）
- 现象：`PreparedStatement.setString` 配合 `queryArgumentsTypes="int8,..."` 抛 `Invalid data type: int8`
- 文件：[src/kwjdbc_svt/main.py](src/kwjdbc_svt/main.py)
- 修法：加 `_JDBC_TYPE_MAP` 表（int8→BIGINT, varchar→VARCHAR, float4→REAL, ...）和 `_to_jdbc_type()` helper；rel init spec 用 mapped 类型

### 8. `iter_table_columns` 重复列名（FIXED，调试中发现）
- 文件：[src/seed_data_generator/reference.py](src/seed_data_generator/reference.py)
- 现象：同 `(group, type)` 两个 entry 都用 `start=1` 重复生成 `col_varchar_1`；重复名进入 seed 文件路径 (2_col_varchar_1.csv, 3_col_varchar_1.csv) + INSERT 列名 → `multiple assignments to the same column`
- 修法：模仿 ColumnNamer 加 `type_counters` keying `(group, base_type)` 累计 start

## 当前 Smoke 状态

最后一次 smk 跑了 setup DDL + SetupThreadGroup rel init 全部 JDBCSampler，但**还没看到最终行数结果**（用户要求暂停）。在写出文件 `todolist.md` 之前 smoke 完成：
- RelInit JTL 行：`RelInit_db_shig_rel_sub_company`、`..._factory`、`..._workshop`
- DB 最终行：未知（需要在继续调试时再查）

## 遗留任务（明天继续）

### 9. **[VERIFY] t_cnc 写 0 行（真因未定位）**
- 现象：t_electmeter 44200 行，t_cnc 0 行，相同 JSR223Sampler Groovy 代码路径
- 已做过的对照：
  - 直接 kwbase 插同样 INSERT 进 t_cnc → INSERT 1 OK（DB 层 OK）
  - 通过 JMeter pipeline → 0 行
  - JTL 显示 `[Write] db_shig.t_cnc 200 OK` 多条
- 下一步诊断：
  1. JSR223Sampler 顶上加 `log.info(prepareStatement returned X, executeBatch returned Y)`
  2. `withCloseable` 之前 `conn.commit()`
  3. PreparedStatement 缓存撞 key 排查（与 t_electmeter 并发）
  4. 检查 `batchRows.size()` 实际值是不是 50

### 10. **`${param_N}` 空值（查询占位符空绑定）**
- 现象：Q2/Q3/Q4/Q5 等有 `?` 的查询报 `at or near "EOF": syntax error`，实际 SQL 是 `WHERE ptag_varchar_1 =` 后无值
- 原因：`?` → `${param_0}` 替换后运行时 JMeter 把 `${param_0}` 求值为空
- 下一步：
  1. 检查 `vars.get('rel_col_seed_files')` 与 PreProcessor param_N 设置时机
  2. 看 query_groups.py 的 PreProcessor Groovy 是否真跑
  3. 若 PreProcessor 用 `rel_col_seed_files` 找文件，相对路径 `/tmp/jmeter-shig/seeds/...` 是否能 resolve（对比 SharedMemory loader 用 `vars.get('seed_dir')`）

### 11. **KaiwuDB 方言不支持 `time_bucket()` 和 `FILTER (WHERE ...)`**
- 现象：LLM Q9/Q11/Q12 报 `at or near "group": syntax error`（FILTER 解析失败）
- 用户上次说"实际都支持"，但 3.2 不认
- 下一步（可选项，非紧急）：
  - 选项 A：把 LLM Q9/Q11/Q12 改写成 KaiwuDB native（`time_bucket` → 自实现窗口切分；FILTER → `CASE WHEN`）
  - 选项 B：DCR 加"Dialect token"层，`query_groups` 支持 `time_bucket(...)` → KaiwuDB native 翻译
  - 选项 C：永久排除

### 12. **`query_groups.py` 占位符提取空绑定的具体根因**
- 现象（接 #10）：验证了 `?` → `${param_0}` 替换 OK，但 `vars.put("param_0", "")` 在 sampler 跑之前没赋值 / 取到了 `rel_col_seed_files=null`
- 要进一步查 PreProcessor 里的 `seed_dir` UDV 是否设置

### 13. **JUnit 测试覆盖**
- 已有：column_namer 9 / jmx_skeleton 18+ / jdbc_datasource 全部
- 缺：
  - `iter_table_columns` 唯一性回归测
  - `ddl_setup._build_rel_init_subtree` XML 结构测
  - `_build_relational_init_specs` spec 字段测
  - `_largest_divisor_le`（小数边界）测
  - `preprocessor_generator` 表间隔离、JDBC 类型 fix 回归测

### 14. **Pre-Commit Sanity**
- `python -m pytest tests/` → 608 passed（已验证）
- 实 DB smoke → rel init 待再跑一次确认行数
- write sampler log instrument 是 debug 用，commit 前可去掉

## 待跑命令（明天一上来）

```bash
# 0. 环境/状态恢复（先做这个！）
cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
source venv/bin/activate
docker start kaiwudb-smoke 2>&1 | head -1
git status --short
python -m pytest tests/ 2>&1 | tail -3   # 期望 608 passed

# 1. 重跑 smoke 验证 rel init 真把 row 写进去了（dup-name fix 之后）
docker exec kaiwudb-smoke ./kwbase sql --insecure -e \
  "delete from db_shig_rel.sub_company; delete from db_shig_rel.factory; delete from db_shig_rel.workshop;"
rm -rf /tmp/jmeter-shig
python -m kwjdbc_svt.main tests/kwjdbc_svt/fixtures/test_model_shig.yaml \
                      tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml \
                      -o /tmp/jmeter-shig
cd /tmp/jmeter-shig && jmeter -n -t test_plan.jmx \
  -Jtest_duration=2 -Jnum_threads=1 -Jdevice_start=1 -Jdevice_per_thread=2 \
  -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
  -l /tmp/jmeter-shig/result.jtl -j /tmp/jmeter-shig/jmeter.log
docker exec kaiwudb-smoke ./kwbase sql --insecure -e \
  "select 'sub_company' t, count(*) c from db_shig_rel.sub_company union all
   select 'factory', count(*) from db_shig_rel.factory union all
   select 'workshop', count(*) from db_shig_rel.workshop;"

# 2. 任务 #9 t_cnc 写 0 行 deep dive
# 3. 任务 #10 ${param_N} 空绑定 deep dive
# 4. 任务 #11 LLM SQL 方言决策（选项 A/B/C）
# 5. 任务 #13 加测试
# 6. 提交：commit 1+2+3+4+5+6+7+8 一起或分批
```

## 改动文件清单（uncommitted）

```
src/jmx_skeleton_generator/generators/query_groups.py        # FIX 1
src/column_namer/namer.py                                   # FIX 2
src/jmx_skeleton_generator/generators/write_groups.py       # FIX 2
src/jdbc_datasource/jdbc_data_source_generator.py           # FIX 3
src/jmx_skeleton_generator/generators/ddl_setup.py          # FIX 4
src/jmx_skeleton_generator/generators/skeleton.py           # FIX 4
src/kwjdbc_svt/main.py                                      # FIX 4, 7
src/direct_insert_write/preprocessor_generator.py          # FIX 5, 6
src/seed_data_generator/reference.py                        # FIX 8
tests/column_namer/test_namer.py                            # FIX 2
tests/jmx_skeleton_generator/test_query_state_machine.py   # FIX 1
tests/jdbc_datasource/test_jdbc_data_source_generator.py    # FIX 3
```
