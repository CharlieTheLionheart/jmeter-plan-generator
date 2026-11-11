# stream-computation — Tasks

> 落地顺序严格按依赖:1 → 2 → 3 → 4 → 5 → 6。前一组不绿,后一组无法验证。
> 每个任务都写明验证方式;纯 Python 任务靠 pytest,任务 6 靠真实集群。

## 1. 配置模型与跨 model 校验

- [ ] 1.1 `config_parser/models.py` 新增 `StreamConfig`(Pydantic):字段 `stream_name` / `source_table` / `target_table` / `select_list` / `window` / `group_by`(可选,默认 `""`)/ `options`(可选,默认 `{}`)/ `expected_min_rows`(可选,默认 1,`ge=0`)/ `verify_delay_seconds`(可选,默认 60,`ge=0`);`extra="forbid"`;`TestConfig` 新增 `stream_config: Optional[StreamConfig] = None`
      → 验证:`pytest tests/config_parser/test_stream_config.py -v`
- [ ] 1.2 `config_parser/models.py` 新增 `validate_stream_refs(model, test_config)`(与 `validate_pub_sub_refs` 同风格,抛 `ConfigParserError`):源/目标表存在于 `model.ts_dbs`、源 ≠ 目标、源表在 `write_config` 中
      → 验证:同一测试文件内 3 类负向用例 + 1 类正向用例
- [ ] 1.3 校验项:`select_list` 前两项必须是与 `window` 匹配的窗口边界函数 —— `TIME_WINDOW` 三参(滑动)→ `first(ts)` / `last(ts)`;两参或非 `TIME_WINDOW` → `first_row(ts)` / `last_row(ts)`
      → 验证:滑动 / 非滑动 / 写错函数名 三类负向用例
- [ ] 1.4 校验项:`select_list` 输出项数 == 目标表总列数(时间列 1 + data_cols 展开 + primary_tags + regular_tags);切分必须**括号感知**
      → 验证:列数不匹配负向用例 + 含带逗号函数调用的切分用例
- [ ] 1.5 `ddl_generator/generator.py` 新增公开方法 `DDLGenerator.ts_table_column_count(table: TsTableConfig) -> int`,内部复用既有 `_allocate_group`(与 `CREATE TABLE` 同源,design D6);`config_parser` 的列数校验调用它
      → 验证:`tests/ddl_generator/` 新增用例:列数 == `CREATE TABLE` 展开的列数(含 primary_tags / regular_tags)
- [ ] 1.6 `config_parser/__init__.py` 导出 `StreamConfig` 与 `validate_stream_refs`
      → 验证:`python -c "from config_parser import StreamConfig, validate_stream_refs"`

## 2. 流 SQL 生成(纯函数)

- [ ] 2.1 新建 `src/stream_comp/__init__.py` + `src/stream_comp/stream_sql.py`:`build_drop_stream_sql(stream_name)` → `DROP STREAM IF EXISTS <name>`
      → 验证:`pytest tests/stream_comp/test_stream_sql.py -v`
- [ ] 2.2 `stream_sql.py`:`build_create_stream_sql(...)` 拼 `CREATE STREAM <name> INTO <target> [WITH OPTIONS (k = 'v', ...)] AS SELECT <select_list> FROM <source> [GROUP BY <group_by>, ]<window>`;`options` 为空 → 不发 `WITH OPTIONS`;option 顺序按配置序
      → 验证:无 options / 有 options / 有 group_by / 无 group_by 四类形态用例
- [ ] 2.3 `stream_sql.py`:`build_delete_target_sql(target_table)` → `DELETE FROM <db>.<table>`;`split_select_items(select_list)` 括号感知切分
      → 验证:切分器用例(`count(*)` / `date_trunc('day', ts)` / 嵌套括号)
- [ ] 2.4 `stream_sql.py`:`build_group_by_clause(group_by, window)` → `GROUP BY <group_by>, <window>` / `GROUP BY <window>`;窗口函数恒在最后
      → 验证:两类形态用例
- [ ] 2.5 `stream_sql.py`:`_required_boundary_functions(window)` + `_item_fn(item)` 两个 module-private helper —— `TIME_WINDOW` 两参 → `("first_row","last_row")`;三参(滑动)→ `("first","last")`;非 `TIME_WINDOW` → `None`(不校验,交服务端)
      → 验证:滑动 / 非滑动 / 非 TIME_WINDOW 三类用例

## 3. 线程组装配

- [ ] 3.1 新建 `src/stream_comp/stream_setup_tg.py`:`append_stream_to_setup_tg(setup_tg_element, stream_config, target_table)` —— 依次追加 `DropStream-<name>` / `DeleteTargetRows-<db>-<table>` / `CreateStream-<name>` 三个 JDBC sampler + 各自 paired empty hashTree
      → 验证:`pytest tests/stream_comp/test_stream_setup_tg.py -v`(断言 sampler 数量、顺序、SQL 文本、paired hashTree 结构)
- [ ] 3.2 新建 `src/stream_comp/stream_verify_tg.py`:`generate_stream_verify_tg(stream_config, model)` → `(tg, tg_hash)`,委托 `teardown_thread_group_element`(delay = `verify_delay_seconds`,num_threads=1,loops=1)
      → 验证:`pytest tests/stream_comp/test_stream_verify_tg.py -v`
- [ ] 3.3 `stream_verify_tg.py`:`SHOW STREAM <name>` sampler —— `query_type="Select Statement"`、**`result_set_handler="Store as Object"` + `result_variable="stream_rows"`**(**不用** `variableNames`,design D8/F22:列数不匹配会静默错绑)+ JSR223Assertion 用 `vars.getObject('stream_rows')` 取 `ArrayList<HashMap>` 按**列标签**读 `status` / `error_message`,断言 `status` 含 `Enable` **且** `error_message` 为空(失败信息带观测值)
      → 验证:断言脚本内容断言 + sampler 属性断言(`resultSetHandler` / `resultVariable` / `variableNames` 为空)
- [ ] 3.4 `stream_verify_tg.py`:`select count(*) from <target>` sampler(`variable_names="count"` → `vars.get('count_1')`)+ JSR223Assertion 断言 `count_1 >= expected_min_rows`(失败信息带观测值与阈值)
      → 验证:同上
- [ ] 3.5 `src/stream_comp/__init__.py` 导出公开 API(6 个函数),module-private helper 不导出
      → 验证:`from stream_comp import ...` 可用

## 4. 接线

- [ ] 4.1 `src/kwjdbc_svt/main.py`:`load_configs` 之后调 `validate_stream_refs(model, cfg)`;`ValueError` / `ConfigParserError` → 退出码 1(现有 `map_exception_to_exit_code` 已覆盖 `ConfigParserError`)
      → 验证:负向 fixture 生成时退出码为 1
- [ ] 4.2 `src/kwjdbc_svt/main.py`:构造 `seed_csv_paths` 时排除流目标表(不生成其种子 CSV / shared-memory loader)
      → 验证:目标表无种子文件;非目标表不受影响
- [ ] 4.3 `src/jmx_skeleton_generator/generators/skeleton.py`:JDBC 路径 —— SetupTG hashTree 追加建流链(挂点与 pub_sub 同: `ddl_elems[1]`),写入 TG 之后追加 Verify TG
      → 验证:`pytest tests/jmx_skeleton_generator/test_stream_wiring.py -v`
- [ ] 4.4 `src/jmx_skeleton_generator/generators/skeleton.py`:schemaless 路径 —— 声明 `stream_config` 时抛错(不支持),不静默忽略
      → 验证:schemaless + stream_config 的负向用例

## 5. Fixture、集成测试与零回归

- [ ] 5.1 新增 fixture `tests/kwjdbc_svt/fixtures/test_model_stream.yaml`(源表 + 目标表两张时序表;**目标表 `ts_col.type` 必须是 `timestamptz`**)+ `test_cfg_stream.yaml`(声明 `stream_config`)
      → 验证:`pytest tests/kwjdbc_svt/test_main.py -v`
- [ ] 5.2 集成用例:用 fixture 跑 `python -m kwjdbc_svt.main` → 断言 JMX XML 合法 + `CREATE STREAM` / `DROP STREAM IF EXISTS` / `DELETE FROM` / `SHOW STREAM` / 目标表 `count(*)` 五类语句各自出现在正确的线程组内
      → 验证:同一测试文件
- [ ] 5.3 **零回归核验**:不声明 `stream_config` 时,生成的 JMX 与本 change 的基线 commit **逐字节一致**;既有 fixture 全部输出不变
      → 验证:`pytest tests/` 全绿 + 逐字节比对脚本
- [ ] 5.4 新增 `docs/refs/kaiwudb-stream-computation-references.md`:`CREATE STREAM` / `SHOW STREAM` / `ALTER STREAM` / `DROP STREAM` 语法 + 12 个可设 option + 窗口闭合语义 + 目标表类型匹配规则 + `--advertise-addr` 环境坑
      → 验证:人工核对与 design.md 的 F1~F21 一致
- [ ] 5.5 实施档案同步:`docs/implementation-log.md` 追加本阶段条目 + 更新「已落地阶段一览」与「待办(跨会话)」
      → 验证:与代码同一个 commit

## 6. smoke(需真实 KaiwuDB 容器)

- [ ] 6.1 容器:**insecure 模式**(与仓库全部 fixture 一致,F25:明文模式下流正常);若日后切 TLS,必须补 `--advertise-addr=127.0.0.1:26257`(否则流 `Disable`,F21)—— 同步写进 `kwjdbc-jmx-smoke` skill §6.0
      → 验证:`SHOW STREAM` 的 `status` = `Enable` 且 `error_message` 为空
- [ ] 6.2 跑端到端:生成 JMX → `jmeter -n` → 断言 `Err: 0`、目标表行数 > 0、Verify TG 两个断言均通过
      → 验证:JTL 的 `success` / `responseCode` + 数据库直查目标表行数 + `jmeter.log` 无 `Problem in JSR223 script`
- [ ] 6.3 跑重跑幂等:连跑两次 → 第二次目标表行数与第一次同量级(不被上一轮残留抬高)
      → 验证:两次的行数对比
- [ ] 6.4 smoke 断言落成正式 pytest(opt-in),口径与 §6.2 一致
      → 验证:`KWJDB_SVT_SMOKE=1 pytest tests/kwjdbc_svt/test_stream_smoke.py -v`
