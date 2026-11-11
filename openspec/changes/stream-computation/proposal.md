# stream-computation — Proposal

## Why

当前 kwjdbc-svt 只覆盖"写入 + 查询"两段负载，无法驱动 KaiwuDB **流计算**(`CREATE STREAM`)能力的测试。KaiwuDB 3.x 提供 `CREATE STREAM` 把时序表的增量写入按窗口聚合成目标表(`docs_kaiwuDB/sql-reference/other-sql-statements/stream-sql.md` 明确"流计算"是独立于 CDC 发布订阅的一等能力)。当前仓库对该能力**零覆盖**:既没有建流的路径,也没有"源表写入 → 流聚合 → 目标表落库 → 断言产出"的端到端链路。

2026-11-10 在 KaiwuDB 3.2.0(容器 `kwdb-x86_64-master` nightly)实测确认:`CREATE STREAM` / `SHOW STREAM` / `ALTER STREAM` / `DROP STREAM` 均可用,且目标表列按**位置**映射流查询输出列 —— 这使"目标表直接用现有 `test_model.yaml` 的普通时序表表达、DDL 复用现有 `DDLGenerator`"成为可行路径,无需新增第二套 DDL 真源。

本 DCR 在测试计划生成器中新增流计算最小链路验证能力:**同一集群内一库一表为源、一库一表为目标**,由 JMeter 自动完成"建库建表 + 建流 + 写源表 + 等窗口闭合 + 目标表验证"全链路。

## What Changes

- 新增 `test_cfg.yaml` 顶层段 `stream_config`(段存在 = 启用,不存在 = 不启用):声明 `stream_name`、源表 `source_table`(`{db}.{table}`)、目标表 `target_table`(`{db}.{table}`)、流查询三段结构化字段 `select_list` / `group_by` / `window`、可选 `options`(原样透传给 `WITH OPTIONS`)、可选 `expected_min_rows`(目标表行数阈值,默认 1)、可选 `verify_delay_seconds`(Verify TG 等待秒数,默认 60)。`test_cfg.yaml` 不声明 `stream_config` 段时,生成器零生效、零回归。
- **目标表放 `test_model.yaml` 当普通时序表**:DDL 由现有 `DDLGenerator` 生成(零新增 DDL 真源,与 pub-sub「不新增 SQL 真源」原则一致);目标表**不出现在** `write_config` → 不被写入,只被流写。生成器在种子生成阶段**排除目标表**,避免无用列种子 CSV + 多余 shared-memory loader。
- 新增 SetupTG 追加链(挂在现有 ts_dbs DDL 之后,与 pub_sub 同一挂点):`DROP STREAM IF EXISTS <name>`(幂等 —— `CREATE STREAM` 不支持 `IF EXISTS`,流水线重跑会撞 `42710`)+ `DELETE FROM <target>`(清掉上一轮残留,避免重跑时行数断言被旧数据满足成假阳性)+ `CREATE STREAM <name> INTO <target> [WITH OPTIONS (...)] AS SELECT <select_list> FROM <source> GROUP BY <group_by>, <window>`。
- 新增 Verify `PostThreadGroup`(排在写入 TG 之后,仿 pub_sub):`SHOW STREAM <name>` 断言 `status` 含 `Enable` **且** `error_message` 为空(防"建流成功但引擎没起来"的假阳性 —— 实测该场景下流会 `Disable` 并带失败原因)+ `select count(*) from <target>` 断言行数 ≥ `expected_min_rows`。
- 新增生成期跨 model 校验 `validate_stream_refs(model, test_config)`:源表/目标表必须存在于 `test_model.ts_dbs`、二者不得相同(服务端同样报 `cannot use the table ... as both source and target table of stream`)、源表必须在 `write_config` 中(否则无数据流入,流永不产出 = "配了却不生效"的静默失效)、`select_list` 前两项必须是与 `window` 匹配的窗口边界函数(`TIME_WINDOW` 非滑动 → `first_row(ts)`/`last_row(ts)`;滑动 → `first(ts)`/`last(ts)`)、`select_list` 输出项数必须等于目标表总列数(ts 列 + data_cols + tags,服务端报 `the output number of stream query doesn't match the target table`)。
- **schemaless(REST)路径本期不支持**:声明 `stream_config` 时若任一 `write_config.mode == "schemaless"`,生成期**报错**而非静默忽略(吸取 write-missing-data「配了参数却完全不生效」的教训)。
- 不生成 tearDown 侧的 `DROP STREAM` 清理 —— 与 pub-sub 一致,清理由流水线侧负责;但建流前先 `DROP STREAM IF EXISTS` 保证重跑幂等。
- 新增 `docs/refs/kaiwudb-stream-computation-references.md`:`CREATE STREAM` / `SHOW STREAM` / `ALTER STREAM` / `DROP STREAM` 语法 + 选项白名单实测 + 窗口闭合语义 + 目标表类型匹配规则 + 容器 `--advertise-addr` 环境坑。
- **不**覆盖:跨集群流计算、`time_bucket` 等非 `TIME_WINDOW` 窗口函数的类型推导、`ALTER STREAM` 完整生命周期(归属功能测试范围)、`LOW_LATENCY` / `PROCESS_HISTORY` 等参数调优(但**支持**通过 `options` 配置生成对应 SQL)、多个流并行(本期 1 个流)、流计算结果的精确行数断言(尾部窗口在写入停止后不再闭合,只支持"≥ 阈值"断言)。

## Capabilities

### New Capabilities

- `stream-computation`:流计算最小链路端到端测试生成能力,含 `stream_config` 配置段 / SetupTG 建流链 / Verify tearDown TG / 目标表复用 model DDL / 生成期跨 model 校验。

### Modified Capabilities

(无。现有 `config-parser` / `jmx-skeleton-generator` / `seed-data-generator` 边界不变;本 change 仅新增可选分支 + 新模块 `stream_comp` 子包。)

## Impact

- **新增模块**:`src/stream_comp/{__init__.py, stream_sql.py, stream_setup_tg.py, stream_verify_tg.py}`(SQL 字符串生成与 TG XML 装配彻底切割,与 `pub_sub` 子包同构)。
- **新增配置段**:`test_cfg.yaml::stream_config`(Pydantic 模型 `StreamConfig`)。
- **改动既有文件**:`src/config_parser/models.py`(新增 `StreamConfig` + `validate_stream_refs`)、`src/config_parser/__init__.py`(导出)、`src/kwjdbc_svt/main.py`(调 `validate_stream_refs` + 种子生成排除目标表)、`src/jmx_skeleton_generator/generators/skeleton.py`(SetupTG 追加建流链 + Verify TG 装配)。
- **新增 reference**:`docs/refs/kaiwudb-stream-computation-references.md`。
- **依赖**:无新增 Python 依赖;复用现有 `JDBCSampler` / `PostThreadGroup` / `JSR223Assertion` / `JMXAssembler`。
- **验证面**:`tests/stream_comp/` 新增 pytest 模块 + `tests/config_parser/test_stream_config.py` + `tests/kwjdbc_svt/fixtures/{test_model_stream,test_cfg_stream}.yaml` + `kwjdbc-jmx-smoke` skill 跑一次端到端(建流 → 写入 → 窗口闭合 → 目标表落库 → Verify 断言)。
- **回归风险**:低。`test_cfg.yaml` 不声明 `stream_config` 段时,生成器零生成,与现有 fixture 100% 兼容(以"与基线逐字节比对"核验);声明该段走新增分支,与现有 JDBC 写入 / 查询路径不重叠。唯一既有文件的行为改动是"种子生成排除流目标表" —— 仅在声明了 `stream_config` 时生效。
