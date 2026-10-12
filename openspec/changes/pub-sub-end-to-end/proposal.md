# pub-sub-end-to-end — Proposal

## Why

当前 kwjdbc-svt 仅覆盖"单集群内"写入 + 查询路径,无法驱动 KaiwuDB 数据发布订阅功能的端到端测试。KaiwuDB 3.x 起提供 `CREATE PUBLICATION` / `CREATE SUBSCRIPTION` 实现集群内 / 集群间的逻辑复制(`db-administration/pub-sub.md` 明确"订阅者从它们订阅的发布拉取数据。发布者上的更改会被实时发送给订阅者。订阅者以与发布者相同的顺序应用那些数据")。为给该功能补 SVT 场景测试,本 DCR 在测试计划生成器中新增发布订阅最小链路验证能力:**同一集群内一库为发布端、一库为订阅端**,通过 JMeter 自动完成"建库建表 + 建发布 + 建订阅 + 写发布端 + 等同步 + 订阅端验证"全链路。**不**生成 tearDown ThreadGroup 或 IF EXISTS 幂等清理 — 测试计划仅在流水线内集成使用,数据库清理工作由流水线侧负责(发布订阅本身也尚未支持 `IF EXISTS` 关键字)。

## What Changes

- 新增 `test_cfg.yaml` 顶层段 `pub_sub_config`(段存在 = 启用,不存在 = 不启用):声明发布端 DB 名 `publisher_db`(订阅端 DB 名**完全硬化**为 `<publisher_db>_sub`,不再作为 `pub_sub_config` 字段)、publication / subscription 名、libpq 格式 `conninfo`、可选 `tables` 数组(`[{name, columns?, where?}]`,支持表级发布 + 列子集 + WHERE 过滤)、可选 `options` 字典(支持 `CREATE PUBLICATION` 的 `buffer_size` / `retrieve_tags` / `publish` + `CREATE SUBSCRIPTION` 的 `target` / `enable` / `ignore_history` / `retry`)、可选 `expected_min_rows` 显式覆盖 Verify TG 行数阈值。`test_cfg.yaml` 不声明 `pub_sub_config` 段时,生成器零生效,零回归。
- 新增 SetupTG (DDL 阶段) 串联:在现有 ts_dbs DDL 之后追加 `CREATE PUBLICATION <pub_name> FOR [DATABASE <publisher_db> | TABLE <pub_db>.<t1> [(cols)] [WHERE <expr>] | TABLE <pub_db>.<t1>, <pub_db>.<t2>, ...]`(`tables` 字段决定粒度,默认降级为整库 `FOR DATABASE`)+ `CREATE TS DATABASE <publisher_db>_sub`(硬约定派生)+ 克隆所有 ts_tables DDL 到 `<publisher_db>_sub`(**`;` 分隔合到单 sampler**,KaiwuDB JDBC driver 支持一次执行多条 SQL — per 2026-10-12 user 提议,简化 sampler 数)+ `CREATE SUBSCRIPTION <sub_name> CONNECTION '<conninfo>' PUBLICATION <pub_name>`。
- 新增订阅端 Verify TG(以 JMeter `tearDown ThreadGroup` 类型生成,确保在 Write TG 之后跑):每张 ts_table 在 `<publisher_db>_sub` 上 `select count(*) from <publisher_db>_sub.<table>`,断言行数 ≥ `expected_min_rows`(默认 1,user 显式覆盖可设 0 走恒真);首条 sampler 跑 `SHOW SUBSCRIPTION <sub_name>` 断言 `status` 含 `running`(防"订阅未启动却同步成功"假阳性)。**不**改 `TestPlan.serialize_threadgroups`(保持现有 Write/Query 并行情景)。
- 现有 Write TG / Query TG 不修改;写入流量仍打 publisher_db(= 现有 ts_dbs),订阅通过服务端 CDC 拉到 `<publisher_db>_sub`。
- 复用 `DDLGenerator.generate(...)` 产 publisher_db DDL,`<publisher_db>_sub` 端 DDL 通过字符串替换 `CREATE TS DATABASE <pub_db>` → `CREATE TS DATABASE <pub_db>_sub` + `<pub_db>.` → `<pub_db>_sub.` 派生(由 `build_subscribe_dest_schemas` 内部硬约定 `sub_db = publisher_db + "_sub"`,无参数传入),**不**新增 SQL 真源。
- 同集群两库共享现有 `${db_url}` 单条 `JDBC Connection Configuration`(`dbUrl` 指向 defaultdb,因为 tsdb 是 SetupTG 阶段后建的,连接时 tsdb 不存在会失败),**不**派生 `${db_url_sub}` UDV、**不**新增第二条 Connection Configuration。订阅端 sampler 全部用 FQN 表名(`<publisher_db>_sub.<table>`)跨库访问;publication / subscription metadata 在 defaultdb 连接上直接跑(per-cluster);时序库表 DDL 也用 FQN 跨库建表,**不**需 `USE` 切库。
- 新增 `docs/refs/kaiwudb-pubsub-references.md`:CREATE PUBLICATION / SUBSCRIPTION 语法 + 权限 + 同步周期(2s)+ 端到端延迟(~10s)+ 2-5s 连接建立窗口 + insecure / TLS 两种 conninfo 示例 + 数据库清理归属说明(由流水线侧负责,生成器不生成 DROP)。
- **不**覆盖:跨集群(本期同集群两库)、WHERE 表达式语法校验(`where` 字符串仅做非空校验,SQL 语法 / 不可变函数 / 聚合函数 / 类型转换 / 排序规则 / 系统列引用的合法性由 KaiwuDB 服务端在 CREATE PUBLICATION 执行时报错)、ALTER SUBSCRIPTION / ALTER PUBLICATION 完整生命周期(归属功能测试范围,本期不测)、tearDown ThreadGroup / `DROP ... IF EXISTS` 幂等清理(DROP 操作稳定性属于功能测试范畴;`DROP SUBSCRIPTION` / `DROP PUBLICATION` 文档未明确支持 `IF EXISTS` 关键字;DROP 后无法继续观察同步效果,测试计划仅在流水线内集成,数据库清理由流水线侧负责)、smoke 不测 `buffer_size` / `retrieve_tags` / `publish=update/delete` 等参数调优(但**支持**通过 `pub_sub_config.options` 配置生成对应 SQL)、HA 主备切换、断点续传、发布关系表(文档已明确不支持)、多 publication / 多 subscription 并行(本期 1 个 publication 对应 1 个 subscription)。

## Capabilities

### New Capabilities

- `pub-sub-end-to-end`:发布订阅最小链路端到端测试生成能力,含 SetupTG 扩展 / Verify tearDown TG / `pub_sub_config` 配置段 / 单池 + FQN 跨库 + per-cluster metadata 机制 / 新增 reference 文档。

### Modified Capabilities

(无。现有 `config-parser` / `jmx-skeleton-generator` / `seed-data-generator` 边界不变;本 change 仅新增可选分支 + 新模块 `pub_sub` 子包。)

## Impact

- **新增模块**:`src/pub_sub/{__init__.py, publication_sql.py, subscribe_dest_schemas.py, pub_sub_setup_tg.py, pub_sub_verify_tg.py}`(DDL 字符串生成与 TG XML 装配彻底切割:DDL 生成在 `publication_sql.py` / `subscribe_dest_schemas.py`;TG XML 装配在 `pub_sub_setup_tg.py` / `pub_sub_verify_tg.py`)。
- **新增配置段**:`test_cfg.yaml::pub_sub_config` (Pydantic 模型 `PubSubConfig`)。
- **新增 reference**:`docs/refs/kaiwudb-pubsub-references.md`。
- **依赖**:无新增 Python 依赖;JMeter `JDBCSampler.database` 字段内置。
- **复用面**:现有 `DDLGenerator.generate(...)` 输出对 publisher_db 与 `<publisher_db>_sub` 100% 同源渲染(替换 db 前缀);现有 SetupTG XML 外壳 `setup_thread_group_element(...)` 复用;现有 `${db_url}` 单 Connection Configuration 复用,**不**新增第二条 Connection、**不**派生新 UDV。Verify TG 内联 `expected_min_rows`(默认 1,user 显式覆盖可设 0 走恒真),**不**复用现有 row-count 公式。
- **验证面**:`tests/pub_sub/` 新增 2 个 pytest 模块(`test_pub_sub_setup_tg` / `test_pub_sub_verify_tg`)+ `tests/config_parser/test_pub_sub_config.py` + `tests/jmx_skeleton_generator/test_ddl_setup_pubsub_append.py` + `tests/jmx_skeleton_generator/test_jdbc_request_database_override.py` + `tests/kwjdbc_svt/fixtures/{test_model_pub_sub,test_cfg_pub_sub,test_cfg_pub_sub_tables}.yaml`(tables 列子集 + WHERE 过滤 fixture)+ `kwjdbc-jmx-smoke` skill §7 跑两次端到端:(a) `test_cfg_pub_sub.yaml` 整库模式;(b) `test_cfg_pub_sub_tables.yaml` 表级 + 列子集 + WHERE 模式。
- **回归风险**:低。`test_cfg.yaml` 不声明 `pub_sub_config` 段时,生成器零生成,与现有 fixture 100% 兼容;声明 `pub_sub_config` 段走新增分支,与现有 JDBC 写入 / 查询路径互不重叠。
