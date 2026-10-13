# KaiwuDB 发布订阅 (Pub-Sub) Reference

> 项目内部 reference (OpenSpec change `pub-sub-end-to-end`, 2026-10-12)
> 用途: 为 §3.5 `append_pub_sub_to_setup_tg` 生成 DDL + §3.6 `generate_pub_sub_verify_tg`
> 校验逻辑 + smoke skill 修订提供权威参考

## 0. Scope (本 DCR 范围)

- 同集群两库 (`<publisher_db>` + `<publisher_db>_sub` 派生) — per design.md D5 锁定
- 表级 / 列子集 / WHERE 三种发布粒度 — per D1
- publication-side + subscription-side options 7-key 全集 — per F-009
- 不覆盖: 跨集群 / HA / 断点续传 / ALTER PUBLICATION 完整生命周期 / DROP IF EXISTS

数据库清理归属: **由流水线侧负责**(`DROP SUBSCRIPTION` / `DROP PUBLICATION` /
`DROP DATABASE`, generator **不** 生成 tearDown 清理 — per design.md Context 锁定)。

## 1. KaiwuDB SQL example (KaiwuDB 官方文档摘录)

以下是在一个真实部署的KaiwuDB数据库下执行发布本地库benchmark的cpu表并在sub_bench库的sub_cpu订阅此表的insert数据的示例操作流程:
```
root@192.168.124.159:26257/defaultdb> CREATE TS DATABASE benchmark;
CREATE TS DATABASE

Time: 301.624439ms

root@192.168.124.159:26257/defaultdb> CREATE TABLE benchmark.cpu (k_timestamp TIMESTAMPTZ NOT NULL, usage_user INT8 NOT NULL, usage_system INT8 NOT NULL, usage_idle INT8 NOT NULL) TAGS (id INT8 NOT NULL, hostname VARCHAR NOT NULL, region VARCHAR NOT NULL, datacenter VARCHAR NOT NULL) PRIMARY TAGS (id);
CREATE TABLE

Time: 881.813223ms

root@192.168.124.159:26257/defaultdb> CREATE PUBLICATION cpu_filtered FOR TABLE benchmark.cpu (usage_user, usage_system, id);
CREATE PUBLICATION

Time: 1.276182668s

root@192.168.124.159:26257/defaultdb> create ts database sub_bench;
CREATE TS DATABASE

Time: 473.053467ms

root@192.168.124.159:26257/defaultdb> CREATE TABLE sub_bench.sub_cpu (k_timestamp TIMESTAMPTZ NOT NULL, usage_user INT8 NOT NULL, usage_system INT8 NOT NULL, usage_idle INT8 NOT NULL) TAGS (id
INT8 NOT NULL, hostname VARCHAR NOT NULL, region VARCHAR NOT NULL, datacenter VARCHAR NOT NULL) PRIMARY TAGS (id);

CREATE TABLE

Time: 509.158419ms

root@192.168.124.159:26257/defaultdb> CREATE SUBSCRIPTION sub_cpu CONNECTION 'postgresql://root1:Znbase%231234@192.168.124.159:26257/benchmark?ssl=disable' PUBLICATION cpu_filtered WITH OPTIONS
 (target='{"benchmark.public.cpu":"sub_bench.public.sub_cpu"}');
CREATE SUBSCRIPTION

Time: 17.072114226s
```

## 2. `test_cfg.yaml::pub_sub_config` 字段 → 生成 DDL / JMX 元素映射表

| fixture 字段 | 类型 | 必填 | 默认 | 生成 DDL / JMX 元素 | 备注 |
|---|---|---|---|---|---|
| `publisher_db` | `str` | 是 | — | 1) `CREATE PUBLICATION ... FOR {DATABASE|TABLE} <pub_db>`;2) `CREATE TS DATABASE <pub_db>_sub`;3) 4 个 sampler 的 `query` 都引用 `pub_db` / `<pub_db>_sub` | 必须在 `test_model.ts_dbs[*].name` 中(§1 Pydantic 校验) |
| `publication_name` | `str` | 是 | — | sampler `name="CreatePublication-<name>"` + `query="CREATE PUBLICATION <name> ..."` | publication 名,SHOW SUBSCRIPTION 输出关联 |
| `subscription_name` | `str` | 是 | — | sampler `name="CreateSubscription-<name>"` + `query="CREATE SUBSCRIPTION <name> ..."` + Verify TG `testname="VerifyTearDownTG-PubSub-<name>"` | subscription 名,SHOW SUBSCRIPTION status 断言用 |
| `conninfo` | `str` | 是 | — | sampler `query="CREATE SUBSCRIPTION ... CONNECTION '<conninfo>' ..."` | libpq 格式,user 显式提供(per F-016),**不**从 `db_url` 派生;pipeline 可通过 `-J` 覆盖? (待确认 — 目前 `db_url` 是 JMeter UDV, `conninfo` 是字面) |
| `tables` | `Optional[List[PublicationTableEntry]]` | 否 | `None` | 整库模式 `FOR DATABASE` vs 表级 `FOR TABLE ...` (per D1 6 形态) | `None` / `[]` → 整库;非空 → 表级 |
| `expected_min_rows` | `Optional[int]` | 否 | `None` | Verify TG `count(*) >= expected_min_rows` (JSR223Assertion script 内联) | `None` → 兜底 1;`0` → 恒真 (WHERE 过滤场景, per D3) |
| `options` | `Dict[str, str]` | 是 | — | split by F-009 caller 过滤契约: publication-side keys → `build_publication_sql` (CREATE PUBLICATION WITH OPTIONS); subscription-side keys → `build_create_subscription_sql` (CREATE SUBSCRIPTION WITH OPTIONS) | 7-key 白名单: `{buffer_size, retrieve_tags, publish, target, enable, ignore_history, retry}` |

**派生字段** (不作为 fixture 输入, generator 内部硬约定):
- `subscriber_db = f"{publisher_db}_sub"` — per D5

## 3. `tables` 校验规则

`pub_sub_config.tables` 字段在 Pydantic 层校验(§1 `PubSubConfig` / `PublicationTableEntry`):

1. **多表不可用 columns/where**:
   - `len(tables) > 1` 时每项 `columns` 必须为 `None`/`[]` + `where` 必须为 `None`
   - per design.md D1 段: KaiwuDB pub-sub 文档不支持 multi-table 列子集 / WHERE
   - 触发 `ValidationError`

2. **单表 columns 必须含所有 primary_tag** (per D2 + §1 cross-ref validator):
   - `tables[i].columns` 每个元素必须 ∈ `primary_tags + regular_tags + data_cols` 名称集合
   - `tables[i].columns` 必须**包含** `tables[i].primary_tags` 所有列名 (ptag `nullable=false` 隐式必含)
   - `tables[i].name` 必须 ∈ `test_model.ts_dbs[*].tables[*].name`
   - 触发 `ValidationError`

3. **where 字符串不语法校验**:
   - `where` 字符串**只**做非空校验(Pydantic `field_validator`)
   - 语法 / 聚合 / 类型转换 / 排序规则 / 系统列引用 / 非不可变函数合法性由 KaiwuDB 服务端在 CREATE PUBLICATION 执行时报错
   - 不在 Pydantic 层 parse

4. **`conninfo` 是独立字段,不是从 `db_url` 派生** (per F-016):
   - generator 不做 `${db_url}` → `conninfo` 字符串重写
   - user **必须**保证 `conninfo` 的 username / password / host / port 与 `${db_url}` 一致
   - 当前 db_url 是 JMeter UDV (`${db_url}`, pipeline 通过 `jmeter -J db_url=...` 覆盖 — 见
     `integration-test/.../test_write.sh:70`), conninfo 是字面值

## 4. conninfo 与 `${db_url}` 一致性(per F-016 锁定)

`conninfo` 跟 `db_url` 是**独立**字段, generator 不派生。但 user 需保证:
- `conninfo` 的 username = `${db_url}` 的 username
- `conninfo` 的 password = `${db_url}` 的 password
- `conninfo` 的 host = `${db_url}` 的 host
- `conninfo` 的 port = `${db_url}` 的 port
- 仅 **db_name** 不同: `${db_url}` 指向 `defaultdb` (per D5: 连接时 tsdb 不存在会失败);
  `conninfo` 指向 `<publisher_db>` (subscription 拉取数据用)

## 5. 与现有 doc 交叉引用

- `docs/refs/jmx-components-references.md` §PostThreadGroup — Verify TG 类型约束
- `docs/refs/jmeter-testplan-reference.md` — JMeter 整体参考
- `docs/refs/kaiwudb-schemaless-write-reference.md` — 无模式写入参考(不重叠, 独立)
- `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` — smoke test 流程, §7 修订会引用本 doc
