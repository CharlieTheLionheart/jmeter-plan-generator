# pub-sub-end-to-end — Design

## Context

KaiwuDB 3.x 起提供发布订阅实现集群内 / 集群间的逻辑复制。`docs/refs/kaiwuDB/db-administration/pub-sub.md` 明确"基于逻辑复制实现,其中一个运行中的订阅者只能订阅一个发布者节点上的一个发布。订阅者从它们订阅的发布拉取数据。发布者上的更改会被实时发送给订阅者。订阅者以与发布者相同的顺序应用那些数据"。关键约束摘录:

- 仅支持时序表 / 时序库发布,**不支持**关系表、临时表、内部视图、常规视图。
- **KaiwuDB 平台限制**:发布订阅为 **1:1**(用户 2026-10-10 与 KaiwuDB 团队确认)— 一个 publication 对应一个 subscription,本 DCR 不考虑多 publication / 多 subscription 链式级联场景。
- 发布对象粒度分四级(由粗到细):
  1. **库级** `FOR DATABASE <db>` — 整库所有表,不支持过滤列 / WHERE
  2. **多表级** `FOR TABLE <db>.t1, <db>.t2, ...` — 多表,不支持过滤列 / WHERE
  3. **单表级** `FOR TABLE <db>.t1` — 单表全部列
  4. **单表 + 列子集** `FOR TABLE <db>.t1 (col1, col2)` — `columns` 必须含所有 primary_tag(因 spec §2.0 锁定 data 列默认 nullable=true,NOT NULL data_col 校验不触发)
- 单表 / 单表+列子集 可选 `WHERE <expr>`(`db-administration/pub-sub.md` §"过滤条件"明确 WHERE 限制:不能含聚合函数 / 类型转换 / 排序规则 / 系统列引用 / 非不可变内置函数)
- "创建订阅后,需等待约 **2-5 秒** 完成订阅端与发布端的连接,之后方可正常接收数据"
- "在发布端数据压力较低的情况下,数据从发布到订阅端一般可在 **10 秒左右** 完成同步;数据同步周期设置为 **2 秒**"
- "当目标数据库或者时序表中存在发布时,不允许任何的 DDL 操作"
- "一个发布只能有一个运行中的订阅"
- 订阅所需权限:对目标时序表有 `INSERT` 权限;发布所需权限:对发布时序表有 `SELECT` 权限
- `CREATE SUBSCRIPTION` 默认 `enable='on'` 立即启动;`ALTER SUBSCRIPTION` 在订阅处于开启状态时**不支持**修改,需先停止

当前 kwjdbc-svt 覆盖:单集群内单库(关系 + 时序)的 DDL、SetupTG 初始化、Write TG(3 mode:direct / prepare / schemaless)、Query TG。本 DCR 在该基础上扩"发布订阅最小链路 + 表级发布粒度"。

用户决策(2026-10-09 ~ 2026-10-10):
- **跨集群 → 同集群两库**(`publisher_db` + `publisher_db + '_sub'` 派生订阅库)。简化连接配置,不需要双 `db_url`、不需要两套 credentials。`subscriber_db` 字段已完全硬化(不再作为 `pub_sub_config` 字段),生成器内部硬约定 = `publisher_db + '_sub'`。
- **范围 → P0 + 表级 / 列子集 / WHERE**:覆盖 `FOR DATABASE` + `FOR TABLE` 两种发布粒度 + 列子集(仅 primary_tag 必含)+ 单表 WHERE 过滤;不覆盖 ALTER SUBSCRIPTION / 参数调优 / HA / 断点续传 / 发布关系表 / WHERE 语法 parse 时校验。
- **不测 DROP / 不生成 tearDown**:DROP 操作稳定性属功能测试范畴;DROP 后无法继续观察同步效果;`DROP SUBSCRIPTION` / `DROP PUBLICATION` 文档未明确支持 `IF EXISTS`;测试计划仅在流水线内集成,数据库清理由流水线侧负责。

## Goals / Non-Goals

**Goals:**
- `test_cfg.yaml` 声明 `pub_sub_config` 段时,生成器在现有 SetupTG DDL 之后追加:
  1. `CREATE PUBLICATION <pub_name> FOR [DATABASE | TABLE ...]`(粒度由 `tables` 字段决定)
  2. `CREATE TS DATABASE <publisher_db>_sub`(硬约定派生)+ 克隆所有 ts_tables DDL(subscriber schema = publisher 全列,即使列子集发布也保持 super-set)
  3. `CREATE SUBSCRIPTION <sub_name> CONNECTION '<conninfo>' PUBLICATION <pub_name>`
- 写入端(Write TG)不变:仍然写 publisher_db(= 现有 ts_dbs 第一张 db),通过服务端 CDC 触发同步。
- 新增 Verify TG(以 JMeter `tearDown ThreadGroup` 类型生成,确保在 Write TG 之后跑):首条 sampler 跑 `SHOW SUBSCRIPTION <sub_name>` 断言 `status` 含 `running`;后续每张 ts_table 一条 `select count(*) from <publisher_db>_sub.<table>` + `JSR223Assertion` 断言行数 ≥ 阈值;阈值默认 = `1`(内联兜底),`pub_sub_config.expected_min_rows` 显式覆盖(供 WHERE 过滤场景下调,如 `0` 走恒真)。
- 同集群两库共享现有 `${db_url}` 单条 `JDBC Connection Configuration`(`dbUrl` 指向 defaultdb,因为 tsdb 是 SetupTG 阶段后建的;连接时 tsdb 不存在会失败),**不**新增第二条 Connection Configuration、**不**派生 `${db_url_sub}` UDV。subscriber 端 sampler 全部用 FQN 表名(`<publisher_db>_sub.<table>`)跨库访问;publication / subscription metadata 在 defaultdb 连接上直接跑(per-cluster);时序库表 DDL 也用 FQN 跨库建表,**不**需 `USE` 切库。

**Non-Goals:**
- 不支持跨集群(本期同集群两库)
- 不测 ALTER SUBSCRIPTION / ALTER PUBLICATION 完整生命周期(归属功能测试范围,本期不测)
- 不生成 `DROP ... IF EXISTS` 幂等清理(DROP 操作稳定性属功能测试范畴;`DROP SUBSCRIPTION` / `DROP PUBLICATION` 文档未明确支持 `IF EXISTS`;DROP 后无法继续观察同步效果;测试计划仅在流水线内集成,数据库清理由流水线侧负责);**生成** tearDown ThreadGroup,仅用于跑 Verify,不做 DROP
- 不测 enable='off'→'on' 启动切换(固定 `enable='on'` 默认)
- **强制** `pub_sub_config.options` 必填且 `options.target` 必填(同集群两库场景下,`target` 是唯一区分发布库表 ↔ 订阅库表映射的机制;无 `target` 服务端拒绝执行 CREATE SUBSCRIPTION);Pydantic validator 强制 options 存在 + target key 存在
- 支持 publication-side options(`buffer_size` / `retrieve_tags` / `publish`)+ subscription-side options(`target` / `enable` / `ignore_history` / `retry`)分组注入到对应 DDL;smoke 用固定 `target` 跑(参数调优由功能测试范围覆盖)
- 不测 HA 主备切换、断点续传(功能测试范围)
- 不支持发布关系表(文档已明确不支持)
- 不测多 publication / 多 subscription 并行 / 链式级联(KaiwuDB 平台 1:1 限制)
- 不在 Pydantic 层做 WHERE 表达式语法解析(`where` 字符串仅做非空校验,聚合 / 类型转换 / 排序规则 / 系统列引用 / 非不可变函数的合法性由 KaiwuDB 服务端在 CREATE PUBLICATION 执行时报错)

## Decisions

### Decision 1:发布粒度由 `tables` 字段决定,`null/[]` 降级到 `FOR DATABASE` 整库模式

**选择**:`pub_sub_config.tables` 是 `Optional[List[PublicationTableEntry]]`;`None` 或 `[]` → 整库模式 `FOR DATABASE <publisher_db>`;非空 → 表级模式。

`PublicationTableEntry` Pydantic 模型:
```python
class PublicationTableEntry(BaseModel):
    name: str                                          # 必填,ts_dbs[].tables[].name
    columns: Optional[List[str]] = None                # 可选,列名列表(单表限定)
    where: Optional[str] = None                        # 可选,SQL WHERE 表达式(单表限定)
```

**SQL 生成规则**(互斥六选一,每个再可选 `WITH OPTIONS` 子句):
| `tables` 形态 | 生成的 SQL 片段 |
|---|---|
| `None` / `[]` | `FOR DATABASE <publisher_db>` |
| 长度 1,无 columns 无 where | `FOR TABLE <pub_db>.<t1>` |
| 长度 1,有 columns 无 where | `FOR TABLE <pub_db>.<t1> (col1, col2, ...)` |
| 长度 1,无 columns 有 where | `FOR TABLE <pub_db>.<t1> WHERE <expr>` |
| 长度 1,有 columns 有 where | `FOR TABLE <pub_db>.<t1> (col1, col2, ...) WHERE <expr>` |
| 长度 N>1 | `FOR TABLE <pub_db>.<t1>, <pub_db>.<t2>, ...`(多表自动禁 columns/where) |

**`WITH OPTIONS` 拼接规则**:`options` 字典仅含 publication-side keys(`buffer_size` / `retrieve_tags` / `publish`)时,在 SQL 末尾追加 `WITH OPTIONS (k1 = v1, k2 = v2)`,保留插入顺序;空 / 缺省则不追加。例:
- 无 options → `CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor`
- 有 options → `CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor WITH OPTIONS (buffer_size = 4, publish = insert)`

**备选 A**:为整库 / 表级分别提供 `publication_kind: Literal["database", "tables"]` 字段。**否决**:语义冗余,`tables` 字段存在与否已足够区分。

**备选 B**:为每张表分别配 `CREATE PUBLICATION`(一个 publication 一张表)。**否决**:KaiwuDB 平台 1:1 限制,多 publication = 多 subscription,本期 1:1 不变。

### Decision 2:`tables[i].columns` 必须含所有 primary_tag 列,校验在 config_parser 阶段完成

**选择**:Pydantic `@model_validator(mode='after')` 校验 `columns` 字段:
- 必填字段:`name`
- 可选字段:`columns` / `where`
- `name` 必须 ∈ `ts_dbs[*].tables[*].name`
- `columns` 元素必须 ∈ 该表 `primary_tags + regular_tags + data_cols` 名称集合
- `columns` 必须**包含**该表所有 `primary_tags` 名称(spec §2.0 锁定 ptag `nullable=false`,隐式必含)
- **NOT NULL data_col 校验不实施**:spec §2.0 锁定 data 列默认 `nullable=true`,实际不会触发;列子集发布的 NOT NULL data_col 限制由 `pub-sql.md` 文档保证,生成器不重复校验
- `len(tables) > 1` 时所有 `columns` 与 `where` 必须为空(`pub-sql.md` 明确"不支持指定表中的列,不支持设置过滤条件" for multi-table publication)

校验失败时抛 `ValidationError`,错误消息引用 offending field 名 + table 名 + column 名。

**备选 A**:校验推迟到 JMX 生成阶段。**否决**:违反项目惯例(主 spec §"约束"明确"约束性校验在 config_parser 阶段完成"),用户错误延迟到生成阶段才报,体验差。

**备选 B**:`columns` 允许 user 传 partial,生成器自动补全 ptag。**否决**:"自动补全" 隐式行为,用户写的 SQL 与最终生成的 SQL 不一致,debug 时困惑;且文档明确"指定列时必须包含所有的主键列",显式列出才是合规用法。

### Decision 3:`expected_min_rows` 显式覆盖字段,未设时取 `1` 兜底(Verify TG 内联)

**选择**:`pub_sub_config.expected_min_rows: Optional[int] = None`。
- `None` / 未设 → Verify TG 内联取默认值 `1`(写在 `generate_pub_sub_verify_tg` 函数体内)
- 显式数值 → Verify TG 改用 `count(*) >= expected_min_rows` 断言
- 显式 `0` → 走恒真(WHERE 过滤场景下严格匹配不到任何行,user 可设 `0` 接受"行数=0"也算 PASS)

**理由**:
- 默认 `1` 能 catch "subscription 未起型 / 同步完全失败"(若订阅正常 + Write TG 写了至少 1 行 → row >= 1 通过;若订阅未启动 / 完全没同步 → row = 0 失败)
- 简化 Verify TG 签名(只接 `pub_sub_config` + `test_model_config` 两个参数)
- `SHOW SUBSCRIPTION <sub_name>` 首条 sampler 断言 `status` 含 `running` 是兜底:row 断言失败先于 subscription status 失败时,排查逻辑仍清晰("subscriber 表没数据但 subscription 跑起来了 → CDC 同步问题" vs "subscription 没跑起来 → 服务端拒收/网络问题")

### Decision 4:订阅端 schema = publisher 全列,即使列子集发布也保持 super-set

**选择**:subscriber 端(`<publisher_db>_sub`)的 `CREATE TABLE` DDL 仍走 `DDLGenerator.generate(test_model_config)` + 字符串替换 db 前缀;**不**根据 publication `columns` 缩窄 subscriber 表的列集合。

**理由**:`sub-sql.md` 明确"目标表要包含发布表的字段,无论指定字段或全部字段" — superset schema 是合法形态;且 subscriber 表只多列不报错(CDC 把未发布列写 NULL,subscriber 端 schema 容许 NULL 即可)。superset 简化:
- 生成器逻辑统一(只用一套 DDL 派生)
- 测试覆盖完整(subscriber 表 = publisher 表,可直接 SELECT * 比对)
- 未来扩 publication 粒度(改 columns / where)不用动 subscriber DDL

**备选 A**:列子集发布时 subscriber 表也只建 columns 列。**否决**:要求生成器识别 publication 类型再决定 DDL 形态,逻辑分支翻倍;且用户改 `pub_sub_config.tables[0].columns` 时,subscriber 表结构要同步变化,fixture 维护成本高。

**备选 B**:列子集发布时 subscriber 表用更宽 schema(含 columns 列表 + 服务端推荐的 ptag 列)。**否决**:与"superset = publisher 全列"等价,只是中间形态,反而引入"哪些是推荐列" 的歧义。

### Decision 5:同集群两库单池 + FQN 跨库(无需切库)

**选择**:现有 `JDBC Connection Configuration`(`dbUrl=${db_url}`)**不动**(单池,无第二条 Connection)。`${db_url}` 指向 **defaultdb**(`tests/kwjdbc_svt/fixtures/test_cfg.yaml:2` 当前 fixture 写法 `jdbc:kaiwudb://localhost:26257/defaultdb`)— 因为被发布的时序库也是 SetupTG 阶段后建的,连接时只有 defaultdb 存在;**如果连接池指向尚未创建的 tsdb,JDBC 连接初始化会失败**(per 2026-10-12 user 纠正)。所有 sampler 在 defaultdb 连接上执行,subscriber 端 sampler 全部用 FQN 表名(`<publisher_db>_sub.<table>`)跨库访问,**不**需要 `USE` 切库:
- publication / subscription 元数据(`SHOW SUBSCRIPTION` / `CREATE SUBSCRIPTION`):**per-cluster**(per 2026-10-12 user 与开发同事核实,发布与订阅是集群下唯一的,不区分库)→ 在 defaultdb 连接上直接跑
- 时序库 / 时序库表 DDL(`CREATE TS DATABASE <publisher_db>_sub` / `CREATE TABLE <publisher_db>_sub.t_cnc ...`):通过 FQN 跨库执行(per 2026-10-12 user:时序库表需要 FQN 创建,但不需切库)

**理由**:KaiwuDB JDBC driver 支持"在连接到 defaultdb 的连接上,用 FQN 表名直接操作其他库"(`select count(*) from <publisher_db>_sub.t_cnc` 等跨库查询合法;`CREATE TABLE <publisher_db>_sub.t_cnc ...` 等跨库建表也合法)。KaiwuDB 发布订阅 metadata 是 **per-cluster**(不区分当前连接的 db)。所以**不**新增第二条 Connection Configuration、**不**派生 `${db_url_sub}` UDV、**不**需要 `USE` 切库。

**SetupTG 串顺序**(单池,FQN):
1. `CREATE PUBLICATION <pub_name> FOR ...` — 在 defaultdb 连接上跑(FQN 表名 `<publisher_db>.<t>`)
2. `CREATE TS DATABASE <publisher_db>_sub` — FQN 跨库建库
3. `CREATE TABLE <publisher_db>_sub.t_cnc (...) TAGS (...) PRIMARY TAGS (...) WITH (...)` — FQN 跨库建表
4. `CREATE SUBSCRIPTION <sub_name> CONNECTION '...' PUBLICATION <pub_name>` — per-cluster,在 defaultdb 连接上跑

**VerifyTG 串顺序**(单池,FQN):
1. `SHOW SUBSCRIPTION <sub_name>` — per-cluster,在 defaultdb 连接上跑
2. per ts_table:`select count(*) from <publisher_db>_sub.<table>` — FQN 跨库查

**备选 A**:新增第二条 JDBCDataSource(`dbUrl` 指向 `<publisher_db>_sub`)。**否决**:本 DCR 单池已能跑通所有 sampler;第二条 Connection 是浪费连接资源。user 2026-10-12 方案:单池 + FQN 跨库,**更简单**。

**备选 B**:`${db_url}` 切成 `${db_host}` + `${db_port}` + `${db_name}` 三个 UDV,subscriber 端 dbUrl 字面拼 `${db_host}:${db_port}/<publisher_db>_sub`。**否决**:破坏现有 fixture 与 smoke skill 的 `${db_url}` 单 UDV 约定,影响面过大;单池方案已规避此问题。

**备选 C**:`USE <publisher_db>_sub;` 切库后跑 metadata / DDL。**否决**:user 2026-10-12 确认 `USE` 不需要 — publication / subscription metadata per-cluster;时序库表用 FQN 即可跨库建表 / 跨库查。`USE` 是过度设计,会给 SetupTG / VerifyTG 串多加冗余采样器且引入"切换失败时半截执行"的回滚复杂度。

### Decision 6:Verify TG 首条 SHOW SUBSCRIPTION status 防"订阅未启动但 row 数对"假阳性

**选择**:Verify TG 第一条 sampler 跑 `SHOW SUBSCRIPTION <sub_name>`,`RegexExtractor` 提 `status` 列,`JSR223Assertion` 断言包含 `running`;之后才是 `select count(*) from <publisher_db>_sub.<table>` per table。

**理由**:订阅未启动时(`enable='off'` 或 connection refused)row=0 也能通过 `count(*) >= 0`(尤其 `expected_min_rows=0` 时恒真)。SHOW SUBSCRIPTION status 是"订阅是否真连上" 的权威信号,放最前保证 status 假阳性先于 row count 假阳性触发。

**元素构造契约**(单池 + FQN,无 `database` 字段覆盖):
- 首 sampler:`SHOW SUBSCRIPTION <subscription_name>`(per-cluster,在 defaultdb 连接上跑)+ JDBC Request **不**填 `database` 字段(单池 + FQN 机制)+ RegexExtractor + JSR223Assertion
- 后续 per ts_table:`select count(*) from <publisher_db>_sub.<table>`(FQN 跨库查,不需 USE)
- `<RegexExtractor refName="sub_status" regex="status\s*\|\s*(\w+)" template="$1$" match_number="1">`(`SHOW SUBSCRIPTION` 返回字段布局 `name | pub_name | conn | parameter | status | start_time | ...`)
- `<JSR223Assertion scriptLanguage="groovy">assert vars.get('sub_status')?.contains('running') : 'subscription not running, status=' + vars.get('sub_status')</JSR223Assertion>`

**备选 A**:SHOW SUBSCRIPTION 也走 row count 断言(数字 status code 之类)。**否决**:`SHOW SUBSCRIPTION` 返回的是文本(字段含 `running` / `disabled` / `error` 等),RegexExtractor + 字符串包含判断更直接。

**备选 B**:跳过 SHOW SUBSCRIPTION,只信 row count(默认公式阈值)。**否决**:失效 case 见 Decision 3 备选 A 描述。

### Decision 8:Subscriber DDL 字符串替换,复用 `DDLGenerator.generate(...)`,不新增 SQL 真源

**选择**:`DDLGenerator.generate(test_model_config)` 输出 `publisher_ddls`,subscriber DDL 通过两步字符串替换派生:

**字符串替换契约**(`src/pub_sub/subscribe_dest_schemas.py::build_subscribe_dest_schemas`):
```python
# subscriber_db 硬约定 = publisher_db + '_sub'(完全硬化见 func 段)
subscribe_dest_schemas = []
for ddl in publisher_ddls:
    sub_ddl = ddl.replace(f'CREATE TS DATABASE {publisher_db}',
                            f'CREATE TS DATABASE {publisher_db}_sub')
    sub_ddl = re.sub(rf'\b{re.escape(publisher_db)}\.',
                     f'{publisher_db}_sub.', sub_ddl)
    subscribe_dest_schemas.append(sub_ddl)
```

**理由**:文档明确"发布订阅双方包含的表的结构需要保持一致"。两套独立 SQL 生成器会引入"哪份是真源" 的歧义;字符串替换简单可靠,正则 `\b` word boundary 防误匹配 `iot_monitor_other` 这类前缀。

**备选 A**:subscriber 用 schemaless 自动建表(无需预建 DDL)。**否决**:schemaless 自动建表的列顺序与显式 DDL 不一致,CDC 复制时可能列错位。

**备选 B**:subscriber 表只建主键 + 时间戳列 + ptag,data 列依赖 CDC 同步补齐。**否决**:文档明确要求"订阅端的表必须包含指定列",初次同步的 data 列如果订阅端不存在会报错。

---

## `pub_sub_config` Pydantic 模型与 fixture 示例

`pub_sub_config` 是 `TestConfig` 的可选字段(Pydantic 模型 `PubSubConfig`),与现有 `write_config` / `query_config` 同位 — 仍归 `src/config_parser/models.py`。`TestConfig.pub_sub_config: Optional[PubSubConfig] = None`:**段存在 = 启用;段不存在 = 不启用**。`subscriber_db` 字段**已移除**(完全硬化为 `<publisher_db>_sub`)。

### 整库模式 fixture 示例(`test_cfg_pub_sub.yaml`)

```yaml
conn_config:
  db_url: jdbc:kaiwudb://localhost:26257/defaultdb
  db_username: root
  db_password: ""
  conn_pool_size: 10
  device_start: 1
  test_duration: 60
write_config:
  - tbl_name: iot_monitor.t_cnc
    throughput: 100
    batch_lines: 100
    num_threads: 1
    device_per_thread: 1
    device_start: 1
pub_sub_config:
  publisher_db: iot_monitor
  publication_name: pub_iot
  subscription_name: sub_iot
  conninfo: postgresql://root@localhost:26257/iot_monitor?sslmode=disable
  # tables 为空 / null → 整库模式 FOR DATABASE iot_monitor
  options:
    target: '{"iot_monitor.t_cnc":"iot_monitor_sub.t_cnc"}'
    enable: "on"
  # expected_min_rows 不设 → Verify TG 内联取 1(兜底)
```

### 表级 + 列子集 + WHERE 模式 fixture 示例(`test_cfg_pub_sub_tables.yaml`)

```yaml
pub_sub_config:
  publisher_db: iot_monitor
  publication_name: pub_iot_tables
  subscription_name: sub_iot_tables
  conninfo: postgresql://root@localhost:26257/iot_monitor?sslmode=disable
  tables:
    - name: t_cnc
      columns: [k_timestamp, device_id, col_float8_1]   # 列子集(必须含所有 primary_tag)
      where: "col_float8_1 > 0"                          # WHERE 过滤
  options:
    target: '{"iot_monitor.t_cnc":"iot_monitor_sub.t_cnc"}'
    enable: "on"
    ignore_history: "true"
    retry: "5s"
  # expected_min_rows 显式设 0 → 走恒真(WHERE 过滤后预期 row=0)
  expected_min_rows: 0
```

### `PubSubConfig` 字段清单

| 字段 | 类型 | 必填 | 默认 | 含义 / 约束 |
|---|---|---|---|---|
| `publisher_db` | `str` | 是 | — | 发布端 db 名;**必须**已存在于 `test_model.ts_dbs[*].name` 中(Pydantic validator 校验);`subscriber_db` 由 `f"{publisher_db}_sub"` 派生(完全硬化,无字段) |
| `publication_name` | `str` | 是 | — | publication 名;唯一标识,服务端用于 SHOW SUBSCRIPTION 输出关联 |
| `subscription_name` | `str` | 是 | — | subscription 名;唯一标识,SHOW SUBSCRIPTION status 断言用此字段(`vars.sub_status` 提取的 status 列) |
| `conninfo` | `str` | 是 | — | libpq 格式连接串(`postgresql://<user>:<password>@<host>:<port>/<publisher_db>?sslmode=disable` 或 `?sslmode=require&sslrootcert=<path>`);Pydantic validator 校验 `startswith("postgresql://")` + non-empty;user **必须**保证用户名/密码/host/port 与 `${db_url}` 一致,否则服务端鉴权失败 |
| `tables` | `Optional[List[PublicationTableEntry]]` | 否 | `None` | 发布粒度配置;`None` / `[]` → 整库模式 `FOR DATABASE <publisher_db>`;非空 → 表级模式(详见 Decision 1) |
| `options` | `Dict[str, str]` | 是 | — | publication-side + subscription-side options 字典;key 必须 ∈ `{buffer_size, retrieve_tags, publish, target, enable, ignore_history, retry}`;**`options.target` 必须**存在且 non-empty(D5 锁定:同集群两库场景下服务端无法仅靠两端 db.table 名对应推断同步关系);key 与 value 的字符串字面直接拼到对应 DDL 的 `WITH OPTIONS` 子句,保留插入顺序 |
| `expected_min_rows` | `Optional[int]` | 否 | `None` | Verify TG `count(*) >= expected_min_rows` 阈值;未设 → 生成器内联取 `1`(兜底);`0` 走恒真(WHERE 过滤场景 user 显式设 0 接受 "行数=0" 也算 PASS);负值 validator 拒绝 |

### `PublicationTableEntry` 子模型

| 字段 | 类型 | 必填 | 默认 | 含义 / 约束 |
|---|---|---|---|---|
| `name` | `str` | 是 | — | ts 表名;必须 ∈ `test_model.ts_dbs[*].tables[*].name`(Pydantic validator 校验) |
| `columns` | `Optional[List[str]]` | 否 | `None` | 列子集(单表限定);元素必须 ∈ 该表 `primary_tags + regular_tags + data_cols` 名称集合;**必须**包含所有 `primary_tag` 列名(spec §2.0 锁定 ptag `nullable=false`);`len(tables) > 1` 时 validator 强制 **为空**(详见 1 / 2 / Decision 1: 多表 MUST NOT 设置 columns) |
| `where` | `Optional[str]` | 否 | `None` | SQL WHERE 表达式(单表限定);Pydantic 仅校验 non-empty,**不**解析 SQL(语法 / 聚合函数 / 类型转换 / 排序规则 / 系统列引用 / 非不可变内置函数的合法性由 KaiwuDB 服务端在 CREATE PUBLICATION 执行时报错);`len(tables) > 1` 时 validator 强制 **为空** |

### `TestConfig` 字段挂载位置

`pub_sub_config` 是 `TestConfig` 的**可选顶层字段**(与 `write_config` / `query_config` / `rest_api_config` 同级),挂 `test_cfg.yaml` 顶层,不是 `TestModelConfig`(`test_model.yaml`)下的字段。`TestConfig.pub_sub_config: Optional[PubSubConfig] = None`:段存在即启用,段不存在即整段不读。

---

## Module Layout

`src/pub_sub/` 子包,5 个 .py 模块 + 1 个 `__init__.py`,纯函数式 API(无 class)。`PubSubConfig` / `PublicationTableEntry` 仍归 `src/config_parser/models.py`(与现有 `WriteConfig` / `QueryConfig` 同位),不放在本子包。

每个文件按"作用 / 包含的函数 / 依赖"三段描述。函数列表每行一条,格式 `func_name(参数: 类型, ...) -> 返回类型`,后接作用 + 输入 + 输出。

### `src/pub_sub/__init__.py`

- **作用**:本子包的公开 API 入口;从 5 个内部模块导入函数,集中到 `__all__` 供外部(skeleton.py / ddl_setup.py 等)调用
- **包含的函数**:无(纯导出文件)
- **导出列表**:
  - `build_publication_sql`
  - `build_subscribe_dest_schemas`
  - `build_create_subscription_sql`
  - `append_pub_sub_to_setup_tg`
  - `generate_pub_sub_verify_tg`
- **依赖**:4 个内部模块

---

### `src/pub_sub/publication_sql.py`

- **作用**:拼接 `CREATE PUBLICATION` SQL 字符串(6 种形态对应 D1 对照表)。纯函数,不执行 SQL,不连数据库
- **包含的函数**:
  - `build_publication_sql(publication_name: str, publisher_db: str, tables: Optional[List[PublicationTableEntry]], options: Optional[Dict[str, str]] = None) -> str`
    - **作用**:根据 `tables` 字段生成 6 种 `CREATE PUBLICATION` SQL 之一(可附加 `WITH OPTIONS` 子句)
    - **输入**:
      - `publication_name`:publication 名(用户填的 `pub_sub_config.publication_name`)
      - `publisher_db`:发布端库名
      - `tables`:`None` 或 `[]` → 整库模式;`List[PublicationTableEntry]` → 表级模式,每项含 `name` / 可选 `columns` / 可选 `where`
      - `options`:可选,publication-side options 字典(只接受 `buffer_size` / `retrieve_tags` / `publish` 三个 key;Pydantic Literal 校验已在外层完成,本函数不重复校验);空 / 缺省时**不**追加 `WITH OPTIONS` 子句
    - **输出**:`str`,形如:
      - 无 options → `'CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor'`
      - 有 options → `'CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor WITH OPTIONS (buffer_size = 4, publish = insert)'`
      - 表级 + WHERE → `'CREATE PUBLICATION pub_iot FOR TABLE iot_monitor.t_cnc WHERE ... WITH OPTIONS ...'`(options 子句始终在末尾)
- **依赖**:Python 标准库 + `config_parser.models.PublicationTableEntry`

---

### `src/pub_sub/subscribe_dest_schemas.py`

- **作用**:构建 subscriber 端 DDL 字符串。包括 (1) **schema 派生**(从 publisher DDL 字符串替换为 subscriber 端库 + 表) + (2) `CREATE SUBSCRIPTION` SQL 拼接(纯字符串,带 conninfo,末尾可选 `WITH OPTIONS` 子句)。所有函数都是纯函数,不执行 SQL、不连数据库、不构造 XML 元素
- **包含的函数**:
  - `build_subscribe_dest_schemas(publisher_ddls: List[str], publisher_db: str) -> List[str]`
    - **作用**:对 `publisher_ddls` 中每条 DDL 做两步字符串替换,生成 subscriber 端 schema DDL
    - **输入**:
      - `publisher_ddls`:`DDLGenerator.generate(test_model_config)` 输出(含建库 + 关系建表 + 时序建表)
      - `publisher_db`:发布端库名(`subscriber_db` 由本函数**内部硬约定**派生为 `f"{publisher_db}_sub"`,不再作为参数)
    - **输出**:与 `publisher_ddls` 等长的 `List[str]`,元素为替换后的 DDL 字符串
    - **替换规则**(`subscriber_db = f"{publisher_db}_sub"` 内部派生):
      1. `f'CREATE TS DATABASE {publisher_db}'` → `f'CREATE TS DATABASE {publisher_db}_sub'`(字符串精确替换)
      2. `re.sub(rf'\b{re.escape(publisher_db)}\.', f'{publisher_db}_sub.', ddl)`(word boundary regex)
    - **硬约定说明**:`subscriber_db` 不再作为 `pub_sub_config` 字段(完全硬化,见 Context / D5 段);同集群两库场景下 `subscriber_db = publisher_db + '_sub'` 是生成器的**唯一**命名规则,user 不需要在 fixture 中填写。若未来扩跨集群 / 自定义命名,另起 DCR。
  - `build_create_subscription_sql(subscription_name: str, publication_name: str, conninfo: str, options: Optional[Dict[str, str]] = None) -> str`
    - **作用**:拼接 `CREATE SUBSCRIPTION` SQL 字符串(纯字符串拼接,不执行、不连库)
    - **输入**:
      - `subscription_name`:订阅名
      - `publication_name`:要订阅的发布名
      - `conninfo`:libpq 格式字符串(`postgresql://<user>:<password>@<host>:<port>/<publisher_db>?sslmode=disable` 等),由 caller 从 `pub_sub_config.conninfo` 字段透传;**用途**:服务端用此连接串反向建立到**发布端** publisher_db 的物理连接,以拉取 publication 数据。user **必须**保证此连接串的用户名 / 密码 / host / port 与 `${db_url}` 一致,否则服务端鉴权失败
      - `options`:可选,subscription-side options 字典(只接受 `target` / `enable` / `ignore_history` / `retry` 四个 key;Pydantic Literal 校验已在外层完成,本函数不重复校验,且 caller 负责按本函数 key 集合过滤后传入 — 与 `build_publication_sql` 契约对齐);空 / 缺省时不追加 `WITH OPTIONS` 子句
    - **输出**:`str`,形如:
      - 无 options → `'CREATE SUBSCRIPTION sub_iot CONNECTION \'postgresql://...\' PUBLICATION pub_iot'`
      - 有 options → `'CREATE SUBSCRIPTION sub_iot CONNECTION \'postgresql://...\' PUBLICATION pub_iot WITH OPTIONS (target = sub_iot.t_cnc, enable = on)'`(options 子句始终在末尾)
    - **当前 scope 约束(同集群两库)**:`options.target` 在 Pydantic validator 阶段被锁定为必填(本场景下服务端无法仅靠"两端 db.table 名完全对应"推断同步关系,见 D5);因此 caller(`append_pub_sub_to_setup_tg`)实际注入的 `options` 永远非空,本函数的"无 options 分支"在本 DCR scope 内**不应被实际生产调用触发**。代码层支持该分支仅为后续多集群发布订阅扩展预留(多集群场景下 target 推断规则可能不同)。**pytest 需覆盖**(防御性测试,断言 `options=None` / `options={}` 时不追加 `WITH OPTIONS` 子句),**smoke test 无需覆盖**(当前 fixture 永远不会触发该分支,smoke 只走生产路径)
- **依赖**:仅 Python 标准库(`re`)

---

### `src/pub_sub/pub_sub_setup_tg.py`

- **作用**:在 SetupTG 末尾追加 pub_sub DDL 链(4 步 JDBC Sampler:`CREATE PUBLICATION` → `CREATE TS DATABASE <publisher_db>_sub` → `;` 分隔 subscriber DDL 合并到单 sampler → `CREATE SUBSCRIPTION`)。**只做 XML 元素装配,不涉及任何 SQL 字符串拼接** — 所有 SQL 由 `publication_sql` / `subscribe_dest_schemas` 委托。原地修改 SetupTG 元素,无返回值
- **包含的函数**:
  - `append_pub_sub_to_setup_tg(setup_tg_element: Element, pub_sub_config: PubSubConfig, test_model_config: TestModelConfig) -> None`
    - **作用**:在 SetupTG 末尾追加 N+2 条 JDBC Sampler(每条执行一个 DDL 子句,全部 DDL 来自委托调用)。**内部**派生 `publisher_ddls`,避免 `JMXSkeletonGenerator` 在调用本函数前先 derive 一次;**内部**派生 `subscriber_db = f"{publisher_db}_sub"`(硬约定,见 `build_subscribe_dest_schemas` 段)
    - **输入**:
      - `setup_tg_element`:现有 SetupTG 的 `<hashTree>` 元素(由 `generate_ddl_setup_thread_group` 构造)
      - `pub_sub_config`:`TestConfig.pub_sub_config` 字段(Pydantic 模型,挂 `test_cfg.yaml` 顶层段,与 `write_config` / `query_config` 同位 — 不在 `TestModelConfig` 上);提供 `publication_name` / `publisher_db` / `tables` / `subscription_name` / `conninfo`(**不**含 `subscriber_db` 字段,完全硬化)
      - `test_model_config`:`test_model.yaml` 顶层 Pydantic 模型(`test_model.yaml` 含 `rel_dbs` + `ts_dbs`,由 `JMXSkeletonGenerator` 已持有);本函数**内部**调用 `DDLGenerator.generate(test_model_config)` 派生 `publisher_ddls`,再委托 `build_subscribe_dest_schemas` 做 subscriber 端 schema 替换
    - **输出**:`None`(原地修改 `setup_tg_element`)
    - **追加顺序**(4 步,单池 + FQN 跨库):
      1. `CREATE PUBLICATION` SQL(委托 `build_publication_sql`,JDBC Sampler,FQN 表名 `<publisher_db>.<t>`)
      2. `CREATE TS DATABASE <publisher_db>_sub`(JDBC Sampler,FQN 跨库建库)
      3. **`;` 分隔 `build_subscribe_dest_schemas` 输出(已含建库 + 建表),注入单个 JDBC Sampler**(per 2026-10-12 user 提议:KaiwuDB JDBC driver 支持一次执行 `;` 分隔的多条 SQL,循环注入多 sampler 太臃肿)
      4. `CREATE SUBSCRIPTION` SQL(委托 `build_create_subscription_sql`,JDBC Sampler,per-cluster metadata,在 defaultdb 连接上跑)
- **依赖**:`publication_sql.build_publication_sql` / `subscribe_dest_schemas.build_subscribe_dest_schemas` / `subscribe_dest_schemas.build_create_subscription_sql` / `DDLGenerator.generate` / `utils.xml_helpers` / `config_parser.models.PubSubConfig` / `config_parser.models.TestModelConfig`

---

### `src/pub_sub/pub_sub_verify_tg.py`

- **作用**:生成 Verify `PostThreadGroup`(JMeter 5.6.3 GUI 显示为 "tearDown Thread Group",`testclass="PostThreadGroup"` / `guiclass="PostThreadGroupGui"`,见 `docs/refs/jmx-components-references.md` §PostThreadGroup) 元素。PostThreadGroup 在所有普通 TG 完成后启动(与 `TestPlan.serialize_threadgroups` 设置无关),保证 Verify 在 Write TG 之后跑。**不**改 `TestPlan.serialize_threadgroups`(保持现有 Write/Query 并行情景)
- **包含的函数**:
  - `generate_pub_sub_verify_tg(pub_sub_config: PubSubConfig, test_model_config: TestModelConfig) -> Element`
    - **作用**:构造一个 `<hashTree>` 元素,内含 1 个 `PostThreadGroup`(testclass 同名)+ 1 个 SHOW SUBSCRIPTION status sampler + N 个 `select count(*)` sampler(每张 ts_table 一条)
    - **输入**:
      - `pub_sub_config`:Pydantic 模型,提供 `publisher_db` / `subscription_name` / `expected_min_rows`(允许 user 显式覆盖,如 `0` 走恒真 WHERE 过滤场景;未设则**内联**取默认值 `1`)(**不**含 `subscriber_db` 字段,完全硬化)
      - `test_model_config`:Pydantic 模型,提供 `ts_dbs`(遍历每张 ts_table 生成 count sampler)
    - **输出**:`Element`,代表整个 Verify PostThreadGroup 的 `<hashTree>` 根元素
    - **内部结构**:
      1. `PostThreadGroup`(num_threads=1, ramp_time=1, `delay=60s`,**不**写 `<longProp name="ThreadGroup.duration">` 让 TG 自然执行结束,`LoopController.loops=1` — 详 §PostThreadGroup 备注)
      2. 首条 sampler:`SHOW SUBSCRIPTION <sub_name>`(per-cluster,在 defaultdb 连接上跑)+ RegexExtractor 提 `status` + JSR223Assertion 断言含 `'running'`
      3. per ts_table:`select count(*) from <publisher_db>_sub.<table>`(FQN 跨库查)+ JSR223Assertion 断言 `count_1 >= expected_min_rows`
    - **expected_min_rows 默认值(内联,无独立模块)**:`expected_min_rows = pub_sub_config.expected_min_rows if pub_sub_config.expected_min_rows is not None else 1`(写在 `generate_pub_sub_verify_tg` 函数体内,常量 `1` 兜底:能 catch "订阅未起型 / 同步完全失败";WHERE 过滤场景 user 显式传 `expected_min_rows=0` 走恒真)
    - **ts_dbs 遍历 + D4 对齐备注**:从 `test_model_config.ts_dbs[*].tables[*]` 遍历得到的是 **publisher 端 table name**,与 `build_subscribe_dest_schemas` 的 DDL 替换一致(D4 锁定:**subscriber schema = publisher 全列,subscriber 表名 = publisher 表名,只 db 前缀不同**)。因此 `select count(*) from <publisher_db>_sub.<table_name>` 直接拿 publisher 表名拼 `<publisher_db>_sub` 前缀即可查订阅表,**无需**经 options.target 派生或重新映射(同集群两库场景下 subscriber 表名 ↔ publisher 表名 = 1:1 等同)。
    - **PostThreadGroup 属性说明**(对齐 `docs/refs/jmx-components-references.md` §PostThreadGroup):
      - `testclass="PostThreadGroup"` / `guiclass="PostThreadGroupGui"`(JMeter 5.6.3 实测;与 SetupThreadGroup 结构对称,但 testclass/guiclass 名不同)
      - `ThreadGroup.delay` = **60s**:PostThreadGroup 启动延迟 = 主线程(Write TG + Query TG)结束后等 60s 再启动 Verify TG。60s 覆盖 subscription 2-5s 连接建立 + ~10s 数据同步延迟 + 2s CDC 周期 + 多次同步周期累计,**确保 Verify TG 启动时数据已同步到 subscriber_db**(硬约定 = `<publisher_db>_sub`)
      - `ThreadGroup.duration` = **不显式设**(JMeter 5.6.3 实测:`<longProp name="ThreadGroup.duration">` 整段不输出,`scheduler=false`,TG 跑完 sampler 列表后自然结束、不循环)
      - `LoopController.loops` = 1:Verify sampler 列表只跑一次(无循环)
      - **不**依赖 `conn_config.test_duration`(签名简化后该参数已去掉,Verify TG delay 与 Write TG 时长解耦);若未来 fixture 需要更长延迟,扩 pub_sub_config verify_delay_seconds 字段(本 DCR 不引入)
- **依赖**:`utils.xml_helpers` / `config_parser.models.PubSubConfig` / `config_parser.models.TestModelConfig`

---

## Key Function Pseudocode

### `build_publication_sql(publication_name, publisher_db, tables)`

```python
def build_publication_sql(publication_name, publisher_db, tables):
    if tables is None or len(tables) == 0:
        # 形态 1: 整库模式
        return f"CREATE PUBLICATION {publication_name} FOR DATABASE {publisher_db}"

    if len(tables) == 1:
        # 形态 2-5: 单表
        t = tables[0]
        fqn = f"{publisher_db}.{t.name}"
        cols_clause = f" ({', '.join(t.columns)})" if t.columns else ""
        where_clause = f" WHERE {t.where}" if t.where else ""
        return f"CREATE PUBLICATION {publication_name} FOR TABLE {fqn}{cols_clause}{where_clause}"

    # 形态 6: 多表(Pydantic validator 已保证 len > 1 时 columns/where 均为空)
    fqns = [f"{publisher_db}.{t.name}" for t in tables]
    return f"CREATE PUBLICATION {publication_name} FOR TABLE {', '.join(fqns)}"
```

> 注:`build_publication_sql` 的 `WITH OPTIONS` 拼接逻辑放在 `build_publication_sql` 顶部(本节未列出 — 与 `build_create_subscription_sql` 对齐),仅在 `options` 非空时按传入顺序追加 `WITH OPTIONS (k1 = v1, k2 = v2)`。options 子句始终在末尾。

### `build_create_subscription_sql(subscription_name, publication_name, conninfo, options=None)`

> **Scope note(同集群两库,本 DCR)**:由于 `options.target` 在 Pydantic validator 阶段被锁定必填(D5),`append_pub_sub_to_setup_tg` 实际注入的 `options` 永远非空,本函数的 `if options:` else 路径在本 DCR scope 内**不应被实际生产调用触发**。该分支仅为后续多集群发布订阅扩展预留(多集群场景下 `target` 推断规则可能不同),保留实现层完整性。**pytest 需覆盖**(防御性测试 `options=None` / `options={}` 两条),**smoke test 无需覆盖**。

```python
def build_create_subscription_sql(subscription_name, publication_name, conninfo, options=None):
    base = (
        f"CREATE SUBSCRIPTION {subscription_name} "
        f"CONNECTION '{conninfo}' "
        f"PUBLICATION {publication_name}"
    )
    if options:
        # 保留 caller 传入的插入顺序;caller 已按 subscription-side key 集合过滤
        opts_str = ", ".join(f"{k} = {v}" for k, v in options.items())
        return f"{base} WITH OPTIONS ({opts_str})"
    return base
```

**key 集合**(写死常量,后续 DCR 可提到 `config_parser.models`):
```python
SUBSCRIPTION_OPTION_KEYS = frozenset({"target", "enable", "ignore_history", "retry"})
```

**caller 过滤契约**:`append_pub_sub_to_setup_tg` 在调用 `build_create_subscription_sql` 前用 SUBSCRIPTION_OPTION_KEYS 过滤 `pub_sub_config.options`(Pydantic Literal 已保证字典里只可能含这两组 key),与 `build_publication_sql` 调用前过滤 publication-side keys 对称。

### `build_subscribe_dest_schemas(publisher_ddls, publisher_db)`

```python
def build_subscribe_dest_schemas(publisher_ddls, publisher_db):
    # 硬约定:subscriber_db = publisher_db + '_sub'(完全硬化,无参数传入)
    sub_db = f"{publisher_db}_sub"
    result = []
    for ddl in publisher_ddls:
        # 步骤 1: 替换 CREATE TS DATABASE 行的 db 名
        sub_ddl = ddl.replace(
            f'CREATE TS DATABASE {publisher_db}',
            f'CREATE TS DATABASE {sub_db}'
        )
        # 步骤 2: 替换 db.schema. 前缀(用 word boundary 防误匹配)
        # 例子: 'CREATE TABLE iot_monitor.t_cnc' → 'CREATE TABLE iot_monitor_sub.t_cnc'
        # 反例: 'iot_monitor_other.t' 不应被匹配(<pub_db> 后跟非 . 不替换)
        sub_ddl = re.sub(
            rf'\b{re.escape(publisher_db)}\.',
            f'{sub_db}.',
            sub_ddl
        )
        result.append(sub_ddl)
    return result
```

### `append_pub_sub_to_setup_tg(setup_tg_element, pub_sub_config, test_model_config)`

```python
def append_pub_sub_to_setup_tg(setup_tg_element, pub_sub_config, test_model_config):
    pub_db = pub_sub_config.publisher_db  # 已 Pydantic 阶段校验非空
    # 硬约定:subscriber_db = publisher_db + '_sub'(完全硬化,不再作为 pub_sub_config 字段)
    sub_db = f"{pub_db}_sub"

    # 内部派生 publisher_ddls(避免 caller 在调用本函数前先 derive 一次):
    # JMXSkeletonGenerator 已持有 test_model_config,本函数复用一份即可。
    publisher_ddls = DDLGenerator.generate(test_model_config)

    # 1. CREATE PUBLICATION(FQN 表名, 在 defaultdb 连接上跑)
    pub_sql = build_publication_sql(pub_sub_config.publication_name, pub_db, pub_sub_config.tables)
    setup_tg_element.append(jdbc_sampler_element(
        name=f"CreatePublication-{pub_sub_config.publication_name}",
        query=pub_sql,
        database=None,  # publisher URL 默认 db = pub_db
    ))

    # subscriber DDL 由 build_subscribe_dest_schemas 派生(已含建库 + 建表,无 SQL 拼接)
    subscribe_dest_schemas = build_subscribe_dest_schemas(publisher_ddls, pub_db)
    # 一次性注入多条 subscriber DDL:KaiwuDB JDBC driver 支持 `;` 分隔的多条 SQL
    # 单个 JDBC Sampler 注入合并后的 query, 不循环注入多个 sampler(臃肿)。
    combined_subscriber_ddl = '; '.join(subscribe_dest_schemas)
    setup_tg_element.append(jdbc_sampler_element(
        name="CreateSubscriberDDL",
        query=combined_subscriber_ddl,  # ddl 内含 FQN 表名 <publisher_db>_sub.<table>
    ))

    # CREATE SUBSCRIPTION(委托 subscribe_dest_schemas.build_create_subscription_sql)
    # caller 侧过滤:只把 subscription-side keys 传入 options,与
    # build_publication_sql caller 侧过滤 publication-side keys 对称。
    # Pydantic Literal 已保证 pub_sub_config.options 仅含这两组 key 之一(或都含)。
    # Scope note(同集群两库):Pydantic validator 已锁定 options.target 必填(D5),因此
    # sub_options 在本 DCR scope 内永远非空;build_create_subscription_sql 的
    # "无 options" 分支不会被实际生产调用触发(仅代码层完整性保留,见该函数 docstring)。
    sub_options = {
        k: v for k, v in pub_sub_config.options.items()
        if k in SUBSCRIPTION_OPTION_KEYS
    }
    sub_sql = build_create_subscription_sql(
        subscription_name=pub_sub_config.subscription_name,
        publication_name=pub_sub_config.publication_name,
        conninfo=pub_sub_config.conninfo,
        options=sub_options,
    )
    setup_tg_element.append(jdbc_sampler_element(
        name=f"CreateSubscription-{pub_sub_config.subscription_name}",
        query=sub_sql,
        database=sub_db,
    ))
```

### `generate_pub_sub_verify_tg(pub_sub_config, test_model_config)`

```python
def generate_pub_sub_verify_tg(pub_sub_config, test_model_config):
    """生成 Verify PostThreadGroup Element。

    JMeter PostThreadGroup(GUI 显示 'tearDown Thread Group', testclass="PostThreadGroup")
    在所有普通 ThreadGroup 完成后才启动(与 TestPlan.serialize_threadgroups 设置无关),
    保证 Verify 在 Write TG 跑完 之后跑。**不**改 TestPlan.serialize_threadgroups
    (保持现有 Write/Query 并行情景)。

    PostThreadGroup 属性(对齐 docs/refs/jmx-components-references.md §PostThreadGroup):
    - ThreadGroup.delay = 60:主线程结束后等 60s 再启动,确保 CDC 同步完成
    - ThreadGroup.duration 不显式设(JMeter 默认行为:跑完 sampler 列表自然结束、不循环)
    - LoopController.loops = 1(JMeter 默认,本条不显式传参)

    结构(顺序):
    1. PostThreadGroup (num_threads=1, ramp_time=1, delay=60, no duration)
    2. 首条 sampler: SHOW SUBSCRIPTION <sub_name>(per-cluster,在 defaultdb 连接上跑)
       + RegexExtractor 提 status
       + JSR223Assertion 断言包含 'running'
    3. per ts_table: select count(*) from <publisher_db>_sub.<table>(FQN 跨库查)
       + JSR223Assertion 断言 count_1 >= expected_min_rows

    Returns:
        <hashTree> 元素,代表整个 Verify PostThreadGroup。
    """
    # 硬约定:subscriber_db = publisher_db + '_sub'(完全硬化,不再作为 pub_sub_config 字段)
    sub_db = f"{pub_sub_config.publisher_db}_sub"

    tg = teardown_thread_group_element(
        name=f"VerifyTearDownTG-PubSub-{pub_sub_config.subscription_name}",
        num_threads=1,
        ramp_time=1,
        delay=60,  # 主线程结束后等 60s 让 CDC 同步完成
        # duration 不显式设:JMeter 默认行为 = 跑完 sampler 列表自然结束、不循环
    )

    # expected_min_rows 内联:user 显式覆盖优先,否则默认 1
    expected_min_rows = (
        pub_sub_config.expected_min_rows
        if pub_sub_config.expected_min_rows is not None
        else 1
    )

    # 首条:SHOW SUBSCRIPTION status check
    tg.append(_build_show_subscription_status_sampler(
        subscription_name=pub_sub_config.subscription_name,
        subscriber_db=sub_db,  # = <publisher_db>_sub
    ))

    # per ts_table: count(*) check
    for ts_db in test_model_config.ts_dbs:
        for table in ts_db.tables:
            tg.append(_build_count_sampler(
                publisher_db=ts_db.name,
                table_name=table.name,
                subscriber_db=sub_db,  # = <publisher_db>_sub
                expected_min_rows=expected_min_rows,
            ))

    return tg
```

### `_build_show_subscription_status_sampler(subscription_name, subscriber_db)`

```python
def _build_show_subscription_status_sampler(subscription_name, subscriber_db):
    # SHOW SUBSCRIPTION 是 per-cluster, 直接在 defaultdb 连接上跑即可
    sampler = jdbc_sampler_element(
        name=f"ShowSubscription-{subscription_name}",
        query=f"SHOW SUBSCRIPTION {subscription_name}",
        variable_names="status",  # JDBC Request 把第一列绑定到 vars.get('status')
    )
    sampler.append(regex_extractor_element(
        ref_name="sub_status",
        regex=r"status\s*\|\s*(\w+)",
        template="$1$",
        match_number=1,
    ))
    sampler.append(jsr223_assertion_element(
        script=f"""
def s = vars.get('sub_status')
assert s != null && s.contains('running') : 'subscription not running, status=' + s
"""
    ))
    return sampler
```

### `_build_count_sampler(publisher_db, table_name, subscriber_db, expected_min_rows)`

```python
def _build_count_sampler(publisher_db, table_name, subscriber_db, expected_min_rows):
    # FQN 表名 {subscriber_db}.{table_name} 跨库查, 在 defaultdb 连接上跑即可
    sampler = jdbc_sampler_element(
        name=f"CountRows-{subscriber_db}-{table_name}",
        query=f"select count(*) from {subscriber_db}.{table_name}",
        variable_names="count",  # JDBC Request 把 count(*) 绑定到 vars.get('count_1')
    )
    sampler.append(jsr223_assertion_element(
        script=f"""
def n = vars.get('count_1') as int
assert n >= {expected_min_rows} : 'row count ' + n + ' below threshold {expected_min_rows}'
"""
    ))
    return sampler
```

---

## JMeter 5.6.3 Element Schema Reference

> 本节列出 pub_sub DCR 用到的 JMeter 元素 schema 详情(对齐 JMeter 5.6.3 GUI 实际输出)。

### `<JDBCSampler>` 元素(SetupTG 全部 DDL + Verify TG 全部查询)

```xml
<JDBCSampler testclass="JDBCSampler" testname="CreatePublication-pub_iot">
  <stringProp name="dataSource">kaiwu_db</stringProp>
  <stringProp name="query">CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor</stringProp>
  <stringProp name="queryArguments"></stringProp>
  <stringProp name="queryType">Select Statement</stringProp>  <!-- DDL 也用 Select Statement -->
  <stringProp name="resultVariable"></stringProp>
  <stringProp name="variableNames"></stringProp>
  <!-- 其他 JMeter 默认字段(如 queryTimeout / resultSetHandler / resultSetMaxRows 等空值字段省略) -->
</JDBCSampler>
```

**关键字段**:
- `queryType=Select Statement`:DDL 也用 Select Statement(JMeter 不区分 DDL/DML,JDBC driver 自行处理)
- `variableNames`:列名列表(JDBC Request 把第一列绑定到 `vars.get('count_1')` / `vars.get('status')` 等)。subscribed / published 端 sampler 通过 FQN 表名跨库访问,不依赖任何"切库"字段

### `<RegexExtractor>` 元素(Verify TG SHOW SUBSCRIPTION sampler 子节点)

```xml
<RegexExtractor guiclass="RegexExtractorGui" testclass="RegexExtractor" testname="sub_status">
  <stringProp name="RegexExtractor.useHeaders">false</stringProp>
  <stringProp name="RegexExtractor.refname"></stringProp>
  <stringProp name="RegexExtractor.regex">status\s*|\s*(\w+)</stringProp>
  <stringProp name="RegexExtractor.template">$1$</stringProp>
  <stringProp name="RegexExtractor.default"></stringProp>
  <boolProp name="RegexExtractor.default_empty_value">false</boolProp>
  <stringProp name="RegexExtractor.match_number"></stringProp>
</RegexExtractor>
```

**嵌套位置**:**作为 `<JDBCSampler>` 配对 hashTree 的子节点**(不能挂在 TG 级 hashTree,否则 JMeter 忽略 — 历史坑:`93d8a18` 修过类似问题)。

### `<JSR223Assertion>` 元素(Verify TG 全部 assertion)

```xml
<JSR223Assertion guiclass="TestBeanGUI" testclass="JSR223Assertion" testname="JSR223 Assertion">
  <stringProp name="cacheKey">true</stringProp>
  <stringProp name="filename"></stringProp>
  <stringProp name="parameters"></stringProp>
  <stringProp name="script">def s = vars.get('sub_status')
assert s != null &amp;&amp; s.contains('running') : 'subscription not running, status=' + s
</stringProp>
  <stringProp name="scriptLanguage">groovy</stringProp>
</JSR223Assertion>
```
```

**嵌套位置**:**作为 sampler 配对 hashTree 的子节点**(与 RegexExtractor 同层,均在 sampler 的 hashTree 内)。

### `<JDBC Connection Configuration>`(沿用现有,本 DCR 不修改)

无变化;`${db_url}` UDV 沿用。

---

## Data Flow & Sequence

### 测试计划生成主流程

```
JMXSkeletonGenerator.generate(test_model_config, test_config)
├── generate_ddl_setup_thread_group(...)  [现有]
│   └── 当 pub_sub_config 段存在:
│       └── pub_sub.pub_sub_setup_tg.append_pub_sub_to_setup_tg(setup_tg, pub_sub_config, test_model_config)
│           # 内部派生 publisher_ddls = DDLGenerator.generate(test_model_config)
│           ├── publication_sql.build_publication_sql(pub_name, pub_db, tables)
│           ├── subscribe_dest_schemas.build_subscribe_dest_schemas(publisher_ddls, pub_db, sub_db)
│           └── _build_test_action_pause_xml(5000)
├── generate_write_thread_groups(...)  [现有,无变化]
├── generate_query_thread_groups(...)  [现有,无变化]
└── 当 pub_sub_config 段存在:
    └── pub_sub.pub_sub_verify_tg.generate_pub_sub_verify_tg(pub_sub_config, test_model_config)
        # 生成 JMeter PostThreadGroup 元素(JMeter 引擎在所有普通 TG 完成后自动启动,与 serialize_threadgroups 无关)
        # 内部派生 sub_db = f"{pub_sub_config.publisher_db}_sub"(硬约定)
        # expected_min_rows 内联:pub_sub_config.expected_min_rows(未设则取 1,无独立 expected_rows 模块)
        ├── _build_show_subscription_status_sampler(subscription_name, sub_db)
        └── per ts_table: _build_count_sampler(publisher_db, table_name, sub_db, expected_min_rows)
```

### Verify PostThreadGroup 内部运行时序

```
VerifyTearDownTG 启动 (1 thread,所有普通 TG 跑完后,内部 delay=60s)
├── sampler 1: SHOW SUBSCRIPTION <sub_name>
│   ├── JDBC Request (per-cluster, 在 defaultdb 连接上跑)
│   ├── RegexExtractor → vars.sub_status
│   └── JSR223Assertion: assert sub_status.contains('running')
│       [FAIL] → TG 终止,后续 sampler 不跑
│       [PASS] → 继续
├── sampler 2: select count(*) from <publisher_db>_sub.t_cnc
│   ├── JDBC Request (FQN 跨库查,在 defaultdb 连接上跑)
│   └── JSR223Assertion: assert count_1 >= expected_min_rows
├── sampler 3: select count(*) from <publisher_db>_sub.t_motor
│   └── ...
└── ...
```

---

## Risks / Trade-offs

- **`test_duration` 过短时 Verify TG 假阳性**:`test_duration` < 30s 时,subscription 同步周期(2s) + 文档"~10 秒延迟" + Write TG 启动 5s 暂停叠加,Verify TG 跑时数据可能还没同步完成。**Mitigation**:`PubSubConfig` Pydantic validator 给 warning(不 raise,允许 expert 用户短测);`kwjdbc-jmx-smoke` skill §7 提示"pub_sub smoke `test_duration>=30s` 起步"。

- **`conninfo` 来源与构造**:`conninfo` **由 user 在 `test_cfg.yaml::pub_sub_config.conninfo` 字段显式填**(generator **不**派生,**不**用 `${db_url}` 字符串重写)。**构造方式**:libpq URL 格式 `postgresql://<user>:<password>@<host>:<port>/<publisher_db>?sslmode=disable`(insecure 容器)或 `?sslmode=require&sslrootcert=<path>`(TLS 容器)。**关键格式差异**:`conninfo` 是 libpq 格式(`postgresql://...`),`${db_url}` 是 JDBC 格式(`jdbc:kaiwudb://...`),两者不可互相替代 — 生成器在 SetupTG 注入到 `CREATE SUBSCRIPTION <sub_name> CONNECTION '<conninfo>' PUBLICATION <pub_name>` 时字面保留 user 提供的 conninfo。**Mitigation**:`docs/refs/kaiwudb-pubsub-references.md` §5 列 insecure / TLS 两种 conninfo 示例 + 字段对齐表(`db_url` 用户名/密码/host/port 必须与 `conninfo` 一致,否则 subscription 服务端鉴权失败);smoke skill §7 fixture 默认 `?sslmode=disable`。

- **WHERE 表达式语法错误延迟到执行时报错**:Pydantic 层只校验 `where` 字符串非空,不解析 SQL;语法错误 / 聚合函数 / 类型转换等会在 KaiwuDB 服务端执行 CREATE PUBLICATION 时报。**Mitigation**:`docs/refs/kaiwudb-pubsub-references.md` §"WHERE 限制" 列出所有不支持的表达式形态(聚合 / 类型转换 / 排序规则 / 系统列引用 / 非不可变内置函数);smoke skill §7 排错段加 "WHERE clause rejected by server" 诊断。

- **subscription 创建竞态**:`CREATE SUBSCRIPTION` 默认 `enable='on'` 立即启动,文档明确"创建订阅后需等待 2-5 秒完成订阅端与发布端的连接"。**Mitigation**:Verify TG 改为 tearDown 位置,启动时距 CREATE SUBSCRIPTION 完成已过 `5s + test_duration` 秒,远超 2-5s 连接窗口 + ~10s 数据同步延迟(2s 周期)。无 TestAction pause 必要时序仍安全。

- **订阅端表结构必须 100% 匹配 publisher_db**:`DDLGenerator` 当前为 publisher_db 设计,如果未来 DDL 输出含 `USING INDEX` 等 JDBC 特有语法,`<publisher_db>_sub` 渲染会失败。**Mitigation**:`tests/ddl_generator/` 加回归测试,确保 `DDLGenerator.generate(...)` 输出对 `<publisher_db>_sub` 也是合法 DDL。

- **`tables` 校验规则"multi-table 禁 columns/where" 与文档口径一致但易踩坑**:fixture 写错时 Pydantic 报错信息可能不够直观。**Mitigation**:`@model_validator` 错误消息明确引用 offending `tables[i]` index + 字段名 + 文档原文("不支持指定表中的列,不支持设置过滤条件")。

- **`\b` word boundary 在特殊字符 db 名下行为差异**:`re.sub(rf'\b{re.escape(publisher_db)}\.', ...)`,`\b` 在 `-` / `_` 开头的 db 名下行为可能差异。**Mitigation**:`tests/pub_sub/test_subscribe_dest_schemas.py` 加 case 覆盖含 `-` / `_` / 数字开头的 db 名替换。

---

## Migration Plan

### Step 1-7:实现 + 测试 + 文档(具体 task 见后续 tasks.md)

部署步骤:
1. 合并本 change 的所有 commit。
2. `tests/` 新增 pub_sub 测试 + fixture 全部通过(预计 pytest +N,既有 643 全 pass)。
3. `kwjdbc-jmx-smoke` skill §7 跑**两次**端到端:(a) `test_cfg_pub_sub.yaml` 整库模式;(b) `test_cfg_pub_sub_tables.yaml` 表级 + 列子集 + WHERE + `expected_min_rows` 调低。断言 (a)-(d) 两条 fixture 都过:
   - SetupTG 全部 `code==0`
   - Write TG JTL 100% 成功
   - Verify TG `count(*) >= threshold`
   - SHOW SUBSCRIPTION `status` 含 `running`
4. 文档:`docs/refs/kaiwudb-pubsub-references.md` 落地 + `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` §7 pub_sub smoke 章节。

回滚:删除 `src/pub_sub/` 模块 + 删除 `pub_sub_config` 字段 + 删除 `tests/pub_sub/` + 删除 fixture + 删除 docs/refs/kaiwudb-pubsub-references.md。`DDLGenerator` 与现有 SetupTG / Write TG 框架**零修改**。
