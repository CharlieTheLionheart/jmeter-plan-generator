# stream-computation — Design

## Context

### 现状

kwjdbc-svt 的 JMX 生成链路:`main.py` 解析两份 YAML(`test_model.yaml` 数据库场景模型 + `test_cfg.yaml` 运行时配置)→ 种子生成 → DDL 生成 → `JMXSkeletonGenerator` 装配 TestPlan。写入侧走 `write_groups.py`(JDBC 路径)或 `rest_write_groups.py`(schemaless 路径),查询侧走 `query_groups.py`。

仓库里已有一个**结构完全同构**的能力:`pub_sub` 子包(pub-sub-end-to-end change)。它证明了"新增顶层配置段 + SetupTG 追加 DDL 链 + Verify `PostThreadGroup`"这条路径在本仓库是成熟的。本 change 沿用同一形态,不发明第二套装配约定。

### 现状缺口

1. `CREATE STREAM` 能力零覆盖 —— 没有建流路径,也没有"写源表 → 流聚合 → 目标表落库 → 断言产出"的端到端链路。
2. `validate_pub_sub_refs` 定义在 `config_parser/models.py` 并导出,但**从未被调用**(`parser.py` / `main.py` 都没有调用点)—— pub-sub 的跨 model 校验实际是死代码。本 change **必须**给自己的校验找到真实调用点,不重复这个错误。
3. `pub_sub_verify_tg.py` 的 docstring 提到 `_build_show_subscription_status_sampler`,但该函数**从未实现**(`SHOW SUBSCRIPTION` 状态断言实际不存在)。本 change 的 `SHOW STREAM` 状态断言是**真实实现**。

### 实测事实(2026-11-10 ~ 11-11,KaiwuDB 3.2.0,容器 `devops.inspur.com/.../kwdb-x86_64-master:latest`)

本 design 的每条决策都基于以下实测,而非文档推断。**F1~F21** 在 KaiwuDB 侧,**F22~F26** 在 JMeter 5.6.3 侧。

#### KaiwuDB 侧

| # | 实测项 | 结果 |
|---|---|---|
| F1 | `CREATE STREAM` / `SHOW STREAM` / `ALTER STREAM` / `DROP STREAM` | 全部可用 |
| F2 | `CREATE STREAM` 目标表不存在 | `42P01 relation ... does not exist` |
| F3 | `CREATE STREAM` 重名 | `42710`(**不支持** `IF EXISTS`) |
| F4 | `DROP STREAM IF EXISTS <不存在的流>` | 成功(幂等可用) |
| F5 | `SHOW STREAM <不存在的流>` | 返回 **0 行**,不报错 |
| F6 | `TIME_WINDOW(ts,'1m')` + `first(ts), last(ts)` | 拒绝:`the first select clause of stream query must be the first_row(ts) of aggregation function time_window` |
| F7 | `TIME_WINDOW(ts,'1m')` + `first_row(ts), last_row(ts)` | 通过 |
| F8 | `TIME_WINDOW(ts,'1m','30s')`(滑动)+ `first(ts), last(ts)` | 通过 |
| F9 | 目标表列名与流查询输出列名**不一致** | 通过 —— 映射**按位置**,列名不必相同 |
| F10 | 流查询输出项数 ≠ 目标表列数 | 拒绝:`the output number of stream query doesn't match the target table: expected 4, got 3` |
| F11 | 输出类型与目标列类型不兼容 | 拒绝:`stream output type is not compatible with target table, column name: "w", source type: "timestamptz", target type: "timestamp"` |
| F12 | 类型兼容的实际边界 | `count(*)` → int4 **或** int8 均通过;`avg()` → float4 **或** float8 均通过;`timestamptz` → `timestamp` **不**通过(数据列严格) |
| F13 | 目标表的**时间列**类型检查 | **宽松** —— `ts TIMESTAMP` 接 `first_row(ts)`(timestamptz)通过;错配发生在**数据列**上 |
| F14 | 源表 = 目标表 | 拒绝:`cannot use the table "x" as both source and target table of stream` |
| F15 | 无效 option key | 拒绝:`invalid option "bogus_key"` |
| F16 | 可设置的 option key | 12 个全部可设:`enable` / `max_delay` / `sync_time` / `process_history` / `max_retries` / `checkpoint_interval` / `heartbeat_interval` / `buffer_size` / `low_latency` / `ignore_expired` / `ignore_update` / `recalculate_delay_rounds`(后 3 个**文档未列**但服务端接受) |
| F17 | `sync_time > max_delay` | 拒绝:`22023`(建流时校验) |
| F18 | `DELETE FROM <时序表>` | **可用**(`DELETE 1`);`TRUNCATE TABLE` 不可用(`0A000`) |
| F19 | 窗口闭合语义 | 窗口在水位线越过窗口尾时才落库。默认 `sync_time=1m` → 源表 ts 需推进 2 分钟;设 `sync_time='0'` → ts 一越过窗口尾即落库(实测 12s 内) |
| F20 | 写入停止后的尾部窗口 | **不再闭合** —— ts 停止推进,最后一个窗口永远不落库 |
| F21 | **TLS 模式**下 `--listen-addr=0.0.0.0` | 流的内部 RPC 用 `0.0.0.0` 宣告 → TLS 证书校验失败 → 流 `Disable`,`error_message: certificate is valid for 127.0.0.1, not 0.0.0.0`。需 `--advertise-addr=127.0.0.1:26257` |
| F25 | **insecure 模式**下同一场景 | 流**正常**(`status=Enable`,`error_message` 空)—— F21 是 **TLS 特有**,明文模式无证书校验故无此问题 |

#### JMeter 5.6.3 侧

| # | 实测项 | 结果 |
|---|---|---|
| F22 | `JDBCSampler.variableNames` 的绑定规则 | `vars[i]` → 结果集**第 `i+1` 列**;变量后缀是**行号**(1-based),`_#` = 总行数。**列数不匹配不报错** —— 给 3 个名字对 10 列,`status` 被静默绑到**第 2 列**(`target_table_name` 的值) |
| F23 | `resultSetHandler="Store as Object"` + `resultVariable` | `vars.getObject(name)` 返回 `java.util.ArrayList<HashMap<String,Object>>`,**map 的 key 是列标签** → 按列名取值,免疫列序 / 列数变化 |
| F24 | `SHOW STREAM` 经 JDBC sampler | 返回正常结果集(1 行 × 10 列);`error_message` 值为**空字符串**(非 null) |
| F26 | `SHOW STREAM <不存在的流>` | 返回 0 行 → F23 方案可判 `rows.isEmpty()`;F22 方案则只能拿到 null |

---

## Goals / Non-Goals

### Goals

- G1 一条测试计划内跑通"建流 → 写源表 → 目标表落库 → 断言产出"。
- G2 配置驱动:源表 / 目标表 / 查询 / 参数 / 断言阈值全部来自 YAML,不改代码。
- G3 生成期拦住可在生成期发现的错误(源表不存在、源=目标、窗口边界函数错、输出列数不匹配)。
- G4 流水线重跑幂等(重复跑同一份配置不因流已存在而失败,断言不被上一轮残留数据满足)。
- G5 不声明 `stream_config` 时零回归(与基线逐字节一致)。

### Non-Goals

- NG1 不做跨集群流计算。
- NG2 不做 `time_bucket` / 会话窗口 / 状态窗口 / 事件窗口 / 计数窗口 —— 本期只支持 `TIME_WINDOW`(滑动与非滑动)。
- NG3 不做流计算结果的**精确**行数断言(受 F20 尾部窗口不闭合约束,只支持 `>=` 阈值)。
- NG4 不做 `ALTER STREAM` 生命周期测试(启停、参数热改)—— 归属功能测试范围。
- NG5 不在 tearDown 侧生成 `DROP STREAM` 清理 —— 与 pub-sub 一致,清理由流水线侧负责。
- NG6 不做 schemaless(REST)路径的流计算。
- NG7 不做流计算输出列的**类型**推导与校验 —— 服务端在 `CREATE STREAM` 时校验(F11/F12),错误信息已足够定位;生成期做类型推导需要一套 SQL 表达式类型系统,超出本期范围。

---

## Decisions

### D1 — 配置段形态:`test_cfg.yaml` 顶层 `stream_config`

**决策**:新增顶层段 `stream_config`,段存在 = 启用,不存在 = 零生效。

**为什么**:与 `pub_sub_config` 同构 —— 用户已有的心智模型("顶层段 = 一个可选能力")直接复用;`TestConfig` 已经是 `extra="forbid"`,新增字段天然获得白名单语义。

**备选**:(a) 复用 `write_config` 增加字段 —— 会把"流计算"耦合进"写入负载"语义,且目标表不参与写入,两者生命周期不同;(b) 独立 YAML 文件 —— 与本仓库"双配置"模型冲突,且流水线侧要改。

### D2 — 流查询形态:结构化三字段(`select_list` / `group_by` / `window`)

**决策**:用三个字段表达流查询,生成器拼 `SELECT <select_list> FROM <source> GROUP BY <group_by>, <window>`。

**为什么**:
1. 可做生成期校验。F6(窗口边界函数)与 F10(输出列数)是**生成期就能判定的错误** —— 结构化后生成器能直接判;整段 SQL 字符串则完全依赖服务端报错。
2. `GROUP BY` 里窗口函数必须在最后 —— 结构化拼接天然满足这条规则,整段 SQL 由用户自己保证。
3. 与文档的 `stream_query` 语义(`SELECT` 普通查询语法的子集)不冲突:结构化只是**限定**了可表达的子集,而这个子集覆盖了 `TIME_WINDOW` 场景的全部需求。

**备选**:整段 SQL 字符串 —— 更自由(可写 `time_bucket`),但把 F6/F10/F14 三类错误全部推给服务端,失去生成期拦截价值。**本期否决**,NG2 已把 `time_bucket` 排除在外。

### D3 — 目标表放 `test_model.yaml`,DDL 复用 `DDLGenerator`

**决策**:目标表是 `test_model.ts_dbs` 里的普通时序表;DDL 由现有 `DDLGenerator` 生成;生成器在种子生成阶段排除该表。

**为什么**:
1. **单一 DDL 真源**。`pub_sub` 的 proposal 明确写过"不新增 SQL 真源";本 change 沿用该原则。若在 `stream_config` 里内联 DDL 字符串,仓库就有两套表定义方式,类型映射 / 列名分配 / 命名规范全部要双份维护。
2. F9 已实测确认**位置映射**成立 —— 目标表列名由 `column_namer` 生成(`col_int8_1` / `col_float8_1` / `col_timestamptz_1`),流查询的输出按位置落列,用户不需要知道目标表的真实列名。列名里带的类型后缀(`col_int8_1` → int8)反而**方便**用户对齐 F12 的类型规则。
3. 目标表不出现在 `write_config` → 不被写入,天然只被流写。

**代价与处置**:
- 目标表会进 `generate_seeds`(它遍历 model 全部表)→ 在 `main.py` 构造 `seed_csv_paths` 时排除目标表,避免无用列种子 CSV 与多余的 shared-memory loader sampler。
- 目标表的 `ts_col.type` 必须是 `timestamptz`(F12/F13:数据列类型严格,`timestamptz → timestamp` 不通过)。现有 fixture 惯例用 `timestamp`,因此**目标表**必须显式写 `timestamptz`。这条写进配置注释与 reference 文档。

### D4 — 建流链三步:`DROP STREAM IF EXISTS` → `DELETE FROM <target>` → `CREATE STREAM`

**决策**:SetupTG 追加三个 sampler,顺序如上。

**为什么**:
- `DROP STREAM IF EXISTS`:F3 表明 `CREATE STREAM` 不支持 `IF EXISTS`,重跑必撞 `42710`;F4 表明 `DROP STREAM IF EXISTS` 幂等可用。这是**唯一**能在建流前清掉同名流的方式。
- `DELETE FROM <target>`:模型 DDL 默认 `if_not_exists: true` → 重跑时目标表已存在且留着上一轮的行 → `count(*) >= N` 会被旧数据满足成**假阳性**。F18 实测 `DELETE FROM <时序表>` 可用(`TRUNCATE` 不可用)。
- 三步都是幂等的,重跑安全。

**备选**:生成 tearDown 侧的 `DROP STREAM` + `DROP TABLE` —— 与 pub-sub「清理由流水线侧负责」的口径不一致,且 tearDown 只在正常结束路径执行,异常中断时反而留下垃圾。**否决**。

### D5 — 生成期跨 model 校验:`validate_stream_refs(model, cfg)`

**决策**:新增独立校验函数,调用点放在 `main.py`(与 `_validate_col_tag_bind_constraints` 并列),**不放** `parser.py`。

**为什么**:`parser.py` 的 `parse_test_cfg_yaml(path)` 只拿到 cfg,拿不到 model;跨 model 校验必须在两份配置都载入内存之后做。`main.py` 的 `main()` 里 `model, cfg = load_configs(args)` 之后正是这个位置。

**校验项与对应实测**:

| 校验 | 对应实测 | 错误要点 |
|---|---|---|
| 源/目标表存在于 `model.ts_dbs` | — | 命名不可解析的表 |
| 源 ≠ 目标 | F14 | 服务端也拒,但生成期拦下更省事 |
| 源表在 `write_config` 中 | F19/F20 | "配了却无数据流入"的静默失效 |
| `select_list` 前两项是窗口边界函数 | F6/F7/F8 | 窗口是否滑动决定要 `first_row/last_row` 还是 `first/last` |
| `select_list` 项数 == 目标表总列数 | F10 | 两边计数都报出来 |

**为什么不校验输出类型**:见 NG7 —— 需要一套 SQL 表达式类型系统;服务端在 `CREATE STREAM` 时校验(F11),且错误信息带列名与两侧类型,定位成本低。

**注意**:`select_list` 的切分必须**括号感知** —— `count(*)` 无逗号但 `date_trunc('day', ts)` 有,朴素 `split(',')` 会数错。

### D6 — 目标表总列数复用 `DDLGenerator` 的分配逻辑

**决策**:在 `ddl_generator/generator.py` 的 `DDLGenerator` 上新增一个**公开**方法 `ts_table_column_count(table: TsTableConfig) -> int`,内部复用既有的 `_allocate_group` —— 与 `CREATE TABLE` 的列展开**同源**。

**为什么**:列数算错 → F10 误报(把对的配置判成错的)或漏报(把错的放过去)。若另写一份 `allocate_columns` + `ColumnNameGenerator` 的组合,两处逻辑将来会漂移。复用 `_allocate_group` 保证**构造上**一致。

**代价**:改动既有模块 `ddl_generator/generator.py` —— 但只是**新增**一个公开方法,不改任何既有行为。

### D7 — Verify `PostThreadGroup`:`SHOW STREAM` 状态断言 + 目标表行数断言

**决策**:Verify TG 排写入 TG 之后(仿 pub-sub),`delay = verify_delay_seconds`,两个 sampler:
1. `SHOW STREAM <name>` → 断言 `status` 含 `Enable` **且** `error_message` 为空
2. `select count(*) from <target>` → 断言 `>= expected_min_rows`

**为什么要有状态断言**:F21 是本轮实测踩到的真实坑 —— 建流 SQL 成功、流却 `Disable` 且带失败原因。**只**断言行数的话,这种"流没起来"的情况会表现为"目标表 0 行 → 行数断言失败",看起来像"没产出数据",但真实原因是"引擎起不来"。分开断言才能把两类失败区分开。这是 `pub_sub` 想做但没做成的事(见 Context 缺口 3)。

**为什么行数断言用 `>=` 而非 `==`**:F20 —— 写入停止后尾部窗口不再闭合,精确行数不可预期。故 `expected_min_rows` 是**下限**语义。

### D8 — `SHOW STREAM` 结果取值:`resultVariable` + `Store as Object` + 按列名取值

**决策**:`SHOW STREAM` sampler 设 `resultSetHandler="Store as Object"` + `resultVariable="stream_rows"`;JSR223Assertion 用 `vars.getObject('stream_rows')` 取 `ArrayList<HashMap>`,按 **map key(= 列标签)** 读 `status` / `error_message`。**不用** `variableNames`。

**为什么(基于 F22/F23)**:
- F22 实测:`variableNames` 的列数不匹配**不报错**,而是把变量名**静默错绑**到靠前的列(3 个名字对 10 列 → `status` 拿到第 2 列的 `target_table_name` 值)。这会让断言读到错列的值,而且**看起来是正常的**。列数一旦随服务端版本变化,断言会静默失效 —— 这是最坏的失败形态。
- F23 实测:`Store as Object` + `resultVariable` 得到 `ArrayList<HashMap<String,Object>>`,key 是列标签 → 按 `row.get('status')` 取值,**免疫列序 / 列数变化**。
- F26:流不存在时返回 0 行 → F23 方案可显式判 `rows.isEmpty()`,给出"流不存在"的准确报错;F22 方案只能拿到 null,报错信息含糊。

**代价**:断言脚本比 `vars.get('status_1')` 复杂(多一次集合操作)。可接受。

**注**:`select count(*)` 的 sampler 仍用 `variable_names="count"` → `vars.get('count_1')`(F22:单行单列,`count_1` 即该列第 1 行的值,无歧义)。这与仓库既有的 `pub_sub` count sampler 写法一致,不改。

### D9 — schemaless 路径:显式拒绝,不做静默忽略

**决策**:`stream_config` 存在且任一 `write_config.mode == "schemaless"` → 生成期报错。

**为什么**:schemaless 路径的 DDL 走 REST 端点(`generate_ddl_setup_http_thread_group`),`CREATE STREAM` 能否经 REST DDL 端点下发未经验证。与其"配了不生效"让用户以为在测流计算,不如直接报错说清不支持。

**与 pub-sub 的差异**:pub-sub 在 schemaless 下是**静默忽略**(其 `skeleton.py` 的 schemaless 分支没有 pub_sub hook)。本 change **不复制**这个行为 —— write-missing-data 阶段 0 的教训正是"配了参数却完全不生效"的静默失效比报错更危险。

---

## `stream_config` Pydantic 模型与 fixture 示例

### `StreamConfig` 字段清单

| 字段 | 类型 | 必填 | 默认 | 含义 / 约束 |
|---|---|---|---|---|
| `stream_name` | `str` | 是 | — | 流计算名称;非空;被 `DROP STREAM IF EXISTS` / `CREATE STREAM` / `SHOW STREAM` 三处引用 |
| `source_table` | `str` | 是 | — | 源时序表,`{db}.{table}` 形态;必须 ∈ `test_model.ts_dbs[*].tables[*]`;必须出现在 `write_config` 中(D5) |
| `target_table` | `str` | 是 | — | 目标时序表,`{db}.{table}` 形态;必须 ∈ `test_model.ts_dbs[*].tables[*]`;≠ `source_table`(D5) |
| `select_list` | `str` | 是 | — | 流查询输出列清单,逗号分隔(括号感知切分);前两项必须是 `window` 要求的窗口边界函数(D5);项数 == 目标表总列数(D5/D6) |
| `window` | `str` | 是 | — | 窗口函数调用,如 `TIME_WINDOW(ts, '1m')`(非滑动)/ `TIME_WINDOW(ts, '1m', '30s')`(滑动);本期只支持 `TIME_WINDOW`(NG2) |
| `group_by` | `str` | 否 | `""` | 分组列清单(逗号分隔);为空 → `GROUP BY <window>`;非空 → `GROUP BY <group_by>, <window>`(窗口恒在最后) |
| `options` | `Dict[str, str]` | 否 | `{}` | 流计算参数;原样透传给 `WITH OPTIONS (k = 'v', ...)`;**保持字典插入顺序**;key / value 的合法性由服务端在 `CREATE STREAM` 时校验(F15/F16),生成器**不做**白名单 |
| `expected_min_rows` | `int` | 否 | `1` | Verify TG 目标表行数**下限**;`ge=0`;`0` 走恒真(与 pub-sub 同语义) |
| `verify_delay_seconds` | `int` | 否 | `60` | Verify TG 的 `ThreadGroup.delay` 秒数;`ge=0` |

### `TestConfig` 字段挂载位置

`stream_config` 是 `TestConfig` 的**可选顶层字段**(与 `write_config` / `query_config` / `rest_api_config` / `pub_sub_config` 同级),挂 `test_cfg.yaml` 顶层。`TestConfig.stream_config: Optional[StreamConfig] = None`:段存在即启用,段不存在即整段不读。

### fixture 示例 — `test_model_stream.yaml`(节选)

```yaml
ts_dbs:
  - name: streamdb
    tables:
      # ── 源表:被 write_config 写入 ──────────────────────────────
      - name: t_src
        ts_col:
          name: ts
          type: timestamp
          ms_step: 1000
        primary_tag_count: 1
        primary_tags:
          - col_type: "varchar(64)"
            type_proportion: 1.0
        regular_tag_count: 0
        data_col_count: 2
        data_cols:
          - col_type: float8
            type_proportion: 0.5
            seed_num: 100
          - col_type: int8
            type_proportion: 0.5
            seed_num: 100

      # ── 目标表:只被流写,不进 write_config ───────────────────────
      #    列: ts(=first_row(ts)) / col_timestamptz_1(=last_row(ts))
      #         col_int8_1(=count(*)) / col_float8_1(=avg(...))
      #         + tag ptag_varchar_1(=dev)
      - name: t_src_1m_avg
        ts_col:
          name: ts
          type: timestamptz        # ← 必须 timestamptz(F12/F13)
          ms_step: 1000
        primary_tag_count: 1
        primary_tags:
          - col_type: "varchar(64)"
            type_proportion: 1.0
        regular_tag_count: 0
        data_col_count: 3
        data_cols:
          - col_type: timestamptz
            type_proportion: 0.34
            seed_num: 10
          - col_type: int8
            type_proportion: 0.33
            seed_num: 10
          - col_type: float8
            type_proportion: 0.33
            seed_num: 10
```

### fixture 示例 — `test_cfg_stream.yaml`

```yaml
conn_config:
  db_url: jdbc:kaiwudb://127.0.0.1:26257/defaultdb
  db_username: root
  db_password: ""
  test_duration: 120

write_config:
  - tbl_name: streamdb.t_src
    mode: prepare
    throughput: 1.0
    batch_lines: 60
    device_per_thread: 1
    num_threads: 1

stream_config:
  stream_name: t_src_1m_avg
  source_table: streamdb.t_src
  target_table: streamdb.t_src_1m_avg
  #        ts(=first_row(ts)) / col_timestamptz_1(=last_row(ts))
  #        col_int8_1(=count(*)) / col_float8_1(=avg(col_float8_1))
  #        ptag_varchar_1(=分组键)
  select_list: "first_row(ts), last_row(ts), count(*), avg(col_float8_1), ptag_varchar_1"
  group_by: "ptag_varchar_1"
  window: "TIME_WINDOW(ts, '1m')"
  options:
    sync_time: "0"          # 跳过排序:ts 一越过窗口尾即落库(F19)
    low_latency: "on"
  expected_min_rows: 1      # 下限语义,不是精确值(NG3 / F20)
  verify_delay_seconds: 90 # 需 ≥ 窗口闭合 + 落库延迟(R4)
```

---

## Module Layout

`src/stream_comp/` 子包,4 个 .py 模块 + 1 个 `__init__.py`,纯函数式 API(无 class)。`StreamConfig` 仍归 `src/config_parser/models.py`(与 `WriteConfig` / `PubSubConfig` 同位),不放在本子包。

### `src/stream_comp/__init__.py`

- **作用**:本子包的公开 API 入口;从内部模块导入函数,集中到 `__all__`
- **包含的函数**:无(纯导出文件)
- **导出列表**:
  - `build_drop_stream_sql`
  - `build_delete_target_sql`
  - `build_create_stream_sql`
  - `split_select_items`
  - `append_stream_to_setup_tg`
  - `generate_stream_verify_tg`
- **依赖**:3 个内部模块

### `src/stream_comp/stream_sql.py`

- **作用**:拼接流计算相关 SQL 字符串 + `select_list` 切分。纯函数,不执行 SQL,不连数据库
- **包含的函数**:
  - `build_drop_stream_sql(stream_name: str) -> str`
  - `build_delete_target_sql(target_table: str) -> str`
  - `build_create_stream_sql(stream_name, target_table, select_list, source_table, group_by, window, options) -> str`
  - `build_group_by_clause(group_by: str, window: str) -> str`
  - `split_select_items(select_list: str) -> List[str]`
- **依赖**:`config_parser.models.StreamConfig`(类型标注)

### `src/stream_comp/stream_setup_tg.py`

- **作用**:把建流三步链追加到既有 SetupTG 的 hashTree
- **包含的函数**:
  - `append_stream_to_setup_tg(setup_tg_element: ET.Element, stream_config: StreamConfig) -> None`
- **依赖**:`stream_comp.stream_sql`、`utils.xml_helpers.jdbc_sampler_element` / `empty_hash_tree`

### `src/stream_comp/stream_verify_tg.py`

- **作用**:装配 Verify `PostThreadGroup`(状态断言 + 行数断言)
- **包含的函数**:
  - `generate_stream_verify_tg(stream_config: StreamConfig) -> Tuple[ET.Element, ET.Element]`
  - `_build_show_stream_sampler(stream_name: str) -> Tuple[ET.Element, ET.Element]`(module-private)
  - `_build_count_sampler(target_table: str, expected_min_rows: int) -> Tuple[ET.Element, ET.Element]`(module-private)
- **依赖**:`utils.xml_helpers.jdbc_sampler_element` / `jsr223_assertion_element` / `teardown_thread_group_element` / `empty_hash_tree`

### 改动的既有模块

| 文件 | 改动 |
|---|---|
| `src/config_parser/models.py` | 新增 `StreamConfig` + `validate_stream_refs` |
| `src/config_parser/__init__.py` | 导出 `StreamConfig` / `validate_stream_refs` |
| `src/ddl_generator/generator.py` | 新增公开方法 `DDLGenerator.ts_table_column_count(table)`(D6) |
| `src/kwjdbc_svt/main.py` | 调 `validate_stream_refs`;`seed_csv_paths` 排除流目标表 |
| `src/jmx_skeleton_generator/generators/skeleton.py` | SetupTG 追加建流链;写入 TG 之后追加 Verify TG;schemaless 路径声明 `stream_config` 时抛错 |

---

## Key Function Pseudocode

### `split_select_items(select_list: str) -> List[str]`

```python
def split_select_items(select_list: str) -> List[str]:
    """按逗号切分 select_list,括号内的逗号不切。"""
    items: List[str] = []
    depth = 0
    cur: List[str] = []
    for ch in select_list:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        items.append("".join(cur).strip())
    return [i for i in items if i]
```

> 为什么要括号感知:`count(*)` 无逗号但 `date_trunc('day', ts)` 有,朴素 `split(",")` 会把后者数成两项 → 列数校验误报。

### `build_drop_stream_sql(stream_name) -> str`

```python
def build_drop_stream_sql(stream_name: str) -> str:
    return f"DROP STREAM IF EXISTS {stream_name}"
```

### `build_delete_target_sql(target_table) -> str`

```python
def build_delete_target_sql(target_table: str) -> str:
    return f"DELETE FROM {target_table}"
```

### `build_create_stream_sql(...) -> str`

```python
def build_create_stream_sql(
    stream_name: str,
    target_table: str,
    select_list: str,
    source_table: str,
    group_by: str,
    window: str,
    options: Optional[Dict[str, str]] = None,
) -> str:
    parts = [f"CREATE STREAM {stream_name}", f"INTO {target_table}"]
    if options:
        # 保持插入顺序(Python 3.7+ dict 迭代序)
        opts = ", ".join(f"{k} = '{v}'" for k, v in options.items())
        parts.append(f"WITH OPTIONS ({opts})")
    parts.append(f"AS SELECT {select_list}")
    parts.append(f"FROM {source_table}")
    parts.append(build_group_by_clause(group_by, window))
    return " ".join(parts)
```

### `build_group_by_clause(group_by, window) -> str`

```python
def build_group_by_clause(group_by: str, window: str) -> str:
    g = group_by.strip()
    if not g:
        return f"GROUP BY {window}"
    return f"GROUP BY {g}, {window}"      # 窗口函数恒在最后
```

### `append_stream_to_setup_tg(setup_tg_element, stream_config)`

```python
def append_stream_to_setup_tg(setup_tg_element, stream_config) -> None:
    # 1) DROP STREAM IF EXISTS —— 幂等(F3/F4)
    drop_sql = build_drop_stream_sql(stream_config.stream_name)
    s, h = jdbc_sampler_element(
        name=f"DropStream-{stream_config.stream_name}",
        query=drop_sql,
        query_type="Update Statement",
    )
    setup_tg_element.append(s)
    setup_tg_element.append(empty_hash_tree())

    # 2) DELETE FROM <target> —— 清掉上一轮残留,防假阳性(D4/F18)
    del_sql = build_delete_target_sql(stream_config.target_table)
    s, h = jdbc_sampler_element(
        name=f"DeleteTargetRows-{stream_config.target_table}",
        query=del_sql,
        query_type="Update Statement",
    )
    setup_tg_element.append(s)
    setup_tg_element.append(empty_hash_tree())

    # 3) CREATE STREAM —— 真正建流
    create_sql = build_create_stream_sql(...)
    s, h = jdbc_sampler_element(
        name=f"CreateStream-{stream_config.stream_name}",
        query=create_sql,
        query_type="Update Statement",
    )
    setup_tg_element.append(s)
    setup_tg_element.append(empty_hash_tree())
```

> JMeter schema:sampler 必须紧跟 paired empty hashTree(不加分隔 hashTree → 后续 sampler 被当 hashTree cast 报错)。与 `pub_sub_setup_tg` 同款。

### `generate_stream_verify_tg(stream_config) -> (tg, tg_hash)`

```python
def generate_stream_verify_tg(stream_config):
    samplers = []
    show_s, show_h = _build_show_stream_sampler(stream_config.stream_name)
    samplers.extend([show_s, show_h])
    cnt_s, cnt_h = _build_count_sampler(
        stream_config.target_table, stream_config.expected_min_rows
    )
    samplers.extend([cnt_s, cnt_h])
    return teardown_thread_group_element(
        name=f"VerifyTearDownTG-Stream-{stream_config.stream_name}",
        num_threads=1,
        ramp_time=1,
        delay=stream_config.verify_delay_seconds,
        children=samplers,
    )
```

### `_build_show_stream_sampler(stream_name)`

```python
def _build_show_stream_sampler(stream_name):
    sampler, sampler_hash = jdbc_sampler_element(
        name=f"ShowStream-{stream_name}",
        query=f"SHOW STREAM {stream_name}",
        query_type="Select Statement",
        result_variable="stream_rows",
        result_set_handler="Store as Object",   # F23:按列名取值,免疫列数变化
    )
    sampler_hash.append(jsr223_assertion_element(script="""
def rows = vars.getObject('stream_rows')
assert rows != null && !rows.isEmpty() : 'SHOW STREAM returned no row for the stream'
def row = rows.get(0)
def status = row.get('status')
def err = row.get('error_message')
assert status != null && status.contains('Enable') : 'stream is not enabled: status=' + status + ', error_message=' + err
assert err == null || err.toString().trim().isEmpty() : 'stream error_message is not empty: ' + err
"""))
    sampler_hash.append(empty_hash_tree())
    return sampler, sampler_hash
```

### `_build_count_sampler(target_table, expected_min_rows)`

```python
def _build_count_sampler(target_table, expected_min_rows):
    sampler, sampler_hash = jdbc_sampler_element(
        name=f"CountRows-{target_table}",
        query=f"select count(*) from {target_table}",
        query_type="Select Statement",
        variable_names="count",     # 单行单列 → vars.get('count_1')(F22)
    )
    sampler_hash.append(jsr223_assertion_element(script=f"""
def n = vars.get('count_1') as int
assert n >= {expected_min_rows} : 'row count ' + n + ' below threshold {expected_min_rows}'
"""))
    sampler_hash.append(empty_hash_tree())
    return sampler, sampler_hash
```

### `validate_stream_refs(model, test_config)`

```python
def validate_stream_refs(model, test_config) -> None:
    sc = test_config.stream_config
    if sc is None:
        return

    # 1) 源 / 目标表存在性
    ts_tables = {(db.name, t.name): t
                 for db in model.ts_dbs for t in db.tables}
    for label, fqn in (("source_table", sc.source_table),
                       ("target_table", sc.target_table)):
        db, _, tbl = fqn.partition(".")
        if (db, tbl) not in ts_tables:
            raise ConfigParserError(...)

    # 2) 源 ≠ 目标
    if sc.source_table == sc.target_table:
        raise ConfigParserError(...)

    # 3) 源表必须被写入
    if test_config.find_write_config(*sc.source_table.split(".", 1)) is None:
        raise ConfigParserError(...)

    # 4) select_list 窗口边界函数
    items = split_select_items(sc.select_list)
    required = _required_boundary_functions(sc.window)   # TIME_WINDOW → (first_row,last_row) / (first,last)
    if required:
        for idx, (item, fn) in enumerate(zip(items[:2], required)):
            if _item_fn(item) != fn:
                raise ConfigParserError(...)

    # 5) 输出列数 == 目标表总列数
    target = ts_tables[tuple(sc.target_table.split(".", 1))]
    expected = DDLGenerator(model).ts_table_column_count(target)
    if len(items) != expected:
        raise ConfigParserError(...)
```

---

## JMeter 5.6.3 Element Schema Reference

> 本节列出本 DCR 用到的 JMeter 元素 schema(对齐 JMeter 5.6.3 实测输出)。

### `<JDBCSampler>` — SetupTG 建流三步

```xml
<JDBCSampler testclass="JDBCSampler" testname="CreateStream-t_src_1m_avg" guiclass="TestBeanGUI" enabled="true">
  <stringProp name="dataSource">jdbcConfig</stringProp>
  <stringProp name="queryType">Update Statement</stringProp>
  <stringProp name="query">CREATE STREAM t_src_1m_avg INTO streamdb.t_src_1m_avg WITH OPTIONS (sync_time = '0', low_latency = 'on') AS SELECT first_row(ts), last_row(ts), count(*), avg(col_float8_1), ptag_varchar_1 FROM streamdb.t_src GROUP BY ptag_varchar_1, TIME_WINDOW(ts, '1m')</stringProp>
  <stringProp name="queryArguments"></stringProp>
  <stringProp name="queryArgumentsTypes"></stringProp>
  <stringProp name="variableNames"></stringProp>
  <stringProp name="resultVariable"></stringProp>
  <stringProp name="queryTimeout">60</stringProp>
  <stringProp name="resultSetMaxRows"></stringProp>
  <stringProp name="resultSetHandler">Store as String</stringProp>
</JDBCSampler>
```

**关键字段**:
- `queryType=Update Statement`:DDL / DML 用 `Update Statement`(与既有 `DDL-<n>` sampler 一致)
- `query` 无结尾分号 —— 一个 sampler 一条语句
- 三个建流 sampler 的 `query` 依次为:`DROP STREAM IF EXISTS <name>` / `DELETE FROM <target>` / `CREATE STREAM ...`

### `<JDBCSampler>` — Verify TG 的 `SHOW STREAM`

```xml
<JDBCSampler testclass="JDBCSampler" testname="ShowStream-t_src_1m_avg" guiclass="TestBeanGUI" enabled="true">
  <stringProp name="dataSource">jdbcConfig</stringProp>
  <stringProp name="queryType">Select Statement</stringProp>
  <stringProp name="query">SHOW STREAM t_src_1m_avg</stringProp>
  <stringProp name="variableNames"></stringProp>
  <stringProp name="resultVariable">stream_rows</stringProp>
  <stringProp name="resultSetHandler">Store as Object</stringProp>
</JDBCSampler>
```

**关键字段**:
- `resultSetHandler=Store as Object` + `resultVariable=stream_rows` → `vars.getObject('stream_rows')` 得到 `ArrayList<HashMap<String,Object>>`,key = 列标签(F23)
- **刻意不用** `variableNames`:列数不匹配会静默错绑(F22)

### `<JDBCSampler>` — Verify TG 的 `count(*)`

```xml
<JDBCSampler testclass="JDBCSampler" testname="CountRows-streamdb.t_src_1m_avg" guiclass="TestBeanGUI" enabled="true">
  <stringProp name="dataSource">jdbcConfig</stringProp>
  <stringProp name="queryType">Select Statement</stringProp>
  <stringProp name="query">select count(*) from streamdb.t_src_1m_avg</stringProp>
  <stringProp name="variableNames">count</stringProp>
  <stringProp name="resultVariable"></stringProp>
  <stringProp name="resultSetHandler">Store as String</stringProp>
</JDBCSampler>
```

**关键字段**:
- `variableNames=count` → `vars.get('count_1')`(单行单列,无歧义;与既有 `pub_sub` count sampler 写法一致)
- 目标表用 FQN → 无需切库

### `<JSR223Assertion>` — Verify TG 全部断言

```xml
<JSR223Assertion guiclass="TestBeanGUI" testclass="JSR223Assertion" testname="JSR223 Assertion">
  <stringProp name="cacheKey">true</stringProp>
  <stringProp name="filename"></stringProp>
  <stringProp name="parameters"></stringProp>
  <stringProp name="script">def rows = vars.getObject('stream_rows')
assert rows != null &amp;&amp; !rows.isEmpty() : 'SHOW STREAM returned no row for the stream'
def row = rows.get(0)
def status = row.get('status')
def err = row.get('error_message')
assert status != null &amp;&amp; status.contains('Enable') : 'stream is not enabled: status=' + status + ', error_message=' + err
assert err == null || err.toString().trim().isEmpty() : 'stream error_message is not empty: ' + err
</stringProp>
  <stringProp name="scriptLanguage">groovy</stringProp>
</JSR223Assertion>
```

**嵌套位置**:**作为 sampler 配对 hashTree 的子节点**(与 `pub_sub` 的 count assertion 同层)。

### `<JDBC Connection Configuration>`(沿用现有,本 DCR 不修改)

无变化;`${db_url}` UDV 沿用。

---

## Data Flow & Sequence

### 测试计划生成主流程

```
JMXSkeletonGenerator.generate(test_config, ...)
├── generate_ddl_setup_thread_group(ddl_statements, ...)   [现有]
│   └── ddl_elems[1] = SetupTG 的 paired <hashTree>
│       └── 当 stream_config 段存在:
│           └── stream_comp.stream_setup_tg.append_stream_to_setup_tg(
│                   ddl_elems[1], test_config.stream_config)
│               → 追加 3 个 sampler + 各自 paired hashTree:
│                   DropStream-<name> / DeleteTargetRows-<db>-<tbl> / CreateStream-<name>
├── generate_shared_memory_setup_thread_group(seed_csv_paths)  [现有]
│   └── seed_csv_paths 已排除流目标表(main.py 侧过滤)
├── generate_write_thread_groups(write_config, ...)             [现有]  ← 写源表
├── generate_query_thread_groups(query_config)                 [现有]
└── 当 stream_config 段存在:
    └── stream_comp.stream_verify_tg.generate_stream_verify_tg(test_config.stream_config)
        → PostThreadGroup "VerifyTearDownTG-Stream-<name>" + paired hashTree
          ShowStream-<name>(+ JSR223Assertion) / CountRows-<db>-<tbl>(+ JSR223Assertion)
```

### 运行期时序(JMeter)

```
SetupThreadGroup "DDL Setup"
  ├─ DDL-<n>            建库建表(含源表 + 目标表)
  ├─ DropStream-<name>  幂等删同名流
  ├─ DeleteTargetRows   清目标表残留
  └─ CreateStream-<name> 建流并启动引擎

ThreadGroup(写入源表)          ← ts = baseTime + r × ms_step,每 tick 重取 baseTime
  └─ 写入持续推进 ts → 水位线越过窗口尾 → 流落库到目标表

PostThreadGroup "VerifyTearDownTG-Stream-<name>"
  ├─ delay = verify_delay_seconds   ← 等最后一个已闭合窗口落库
  ├─ ShowStream-<name>   → 断言 status=Enable 且 error_message 空
  └─ CountRows-<target>  → 断言 count(*) >= expected_min_rows
```

---

## Risks / Trade-offs

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | `Store as Object` 的 `ArrayList<HashMap>` 是 JMeter 5.6.3 的实现细节 | JMeter 升级后取值方式可能变 | 已实测确认(F23);若失效,退化为 `vars.get('status_1')`(F22 路径)并在断言里加"列名存在性"检查;该退化会重新引入静默错绑风险,故优先修 JMeter 侧而非退化 |
| R2 | 输出列数校验依赖"目标表总列数"的准确计算 | 误报 → 用户被无意义的错误挡住 | 目标表列数复用 `DDLGenerator._allocate_group`(D6),与 `CREATE TABLE` 构造上同源;smoke 用真实表交叉核对 |
| R3 | 尾部窗口不闭合(F20) → 目标表行数少于"理论窗口数 × 设备数" | 用户按理论值设 `expected_min_rows` 会永远失败 | spec 明确定义 `expected_min_rows` 为**下限**语义;配置注释写明"尾部窗口不落库,不要按理论窗口数设阈值" |
| R4 | 流的落库延迟(实测 ≤ 12s)受 `CHECKPOINT_INTERVAL`(默认 10s)/ `HEARTBEAT_INTERVAL` 影响 | `verify_delay_seconds` 偏小 → 断言在落库前执行 | 默认 60s;配置注释说明"窗口越大、checkpoint 越长,延迟要相应放大" |
| R5 | 目标表 `ts_col.type` 若写成 `timestamp`(fixture 惯例)→ F12 类型不兼容 | 建流时报类型不兼容 | 配置注释 + reference 文档显式写明目标表须用 `timestamptz`;类型校验交给服务端(F11 错误信息带列名与两侧类型) |
| R6 | 目标表的列类型与流查询输出类型不匹配(F11) | 建流失败(SetupTG 阶段,早) | 服务端错误信息已足够定位;生成期类型推导见 NG7 |
| R7 | `DELETE FROM <target>` 在目标表很大时耗时 | SetupTG 变慢 | 目标表每轮只积累一个测试周期的数据量,可忽略;若未来目标表成为真实负载对象,需重新评估 |
| R8 | **TLS 模式**容器缺 `--advertise-addr` → 流 `Disable`(F21) | smoke 假失败,且报错信息不指向根因 | 本期 smoke 走 **insecure 容器**(F25:明文模式下流正常),与仓库全部 fixture 一致;TLS 场景需补 `--advertise-addr=127.0.0.1:26257`,写进 smoke skill §6.0 与 reference 文档 |
| R9 | 校验"源表必须在 `write_config` 中"可能过严 | 用户想用外部数据源测流 → 被挡 | 本期 NG 范围内没有外部数据源;该校验的错误信息说明"如何解除"(把表加进 `write_config`) |
| R10 | `find_write_config` 是**大小写敏感**的精确匹配(既有缺陷,阶段 1 已记) | cfg 里表名大小写与 model 不一致 → 源表"未写入"误报 | 本期沿用既有行为,错误信息里同时打印 cfg 与 model 的表名,便于用户定位;该既有缺陷不在本 change 范围 |

---

## Migration Plan

1. **无迁移**:本 change 是纯新增的可选能力。既有 YAML 不受影响。
2. **回滚**:删掉 `test_cfg.yaml` 的 `stream_config` 段 → 生成器回到基线行为(逐字节一致);代码回滚 = revert 本 change 的 commit,无数据迁移。
3. **落地顺序**:先落配置模型 + 校验(纯 Python,可单测),再落 SQL 生成(纯函数),再落 TG 装配,最后落 `main.py` / `skeleton.py` 的接线。
4. **smoke 环境**:insecure 容器(F25);若改用 TLS 容器,必须带 `--advertise-addr=127.0.0.1:26257`(F21)。

---

## Open Questions

| # | 问题 | 现状 | 何时回答 |
|---|---|---|---|
| Q1 | `SHOW STREAM` 是否应同时断言 `options` 与 `query` 回读一致(建流是否被服务端改写)? | 本期只断言 `status` + `error_message` | 用户提出"流计算配置回读"需求时 |
| Q2 | 是否需要支持多个流(一个 `stream_config` 段 → 数组)? | 本期单流(pub-sub 也是 1 pub : 1 sub) | 需求方提出多流场景时 |
| Q3 | `group_by` 为空(只有窗口、不分组)够用吗? | 允许;`GROUP BY <window>` 形态已实测建流通过 | — |
| Q4 | 是否需要"精确行数"断言? | NG3 不做 | 需求方提出精确断言时 |
| Q5 | 是否需要在 TLS 模式下也支持流计算(补 `--advertise-addr` 到 smoke skill)? | 本期 smoke 走 insecure;TLS 场景的问题已定位(F21) | 流水线切换到 TLS 容器时 |
