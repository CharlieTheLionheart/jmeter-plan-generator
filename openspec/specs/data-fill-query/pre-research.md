# 补值查询预研文档

> **2026-11-03 更正说明**：本文按 KaiwuDB 3.2.0 实测核对过一遍（容器 `kaiwudb-smoke`，真实 shig 表结构 + 种子数据 + JMeter 端到端），原文有 4 处表述与产品实况不符，已在正文就地更正，并追加「实测验证结论」一节记录证据。
> **用例条数由 8 + 6 = 14 调整为 7 + 6 = 13**（`diff` 不能进 `interpolate`，且 shig 表缺 INT8/FLOAT8 列，详见下文）。

## 目的
为KaiwuDB数据库稳定性场景测试增加插值查询用例

## 方案
开启在场景测试计划生成器测试配置中配置开启缺点写入的同时，增加一些插值查询用例

### 前提
完成场景测试计划生成器缺点写入(write-missing-data)功能 ✅ 已完成（2026-10-30 归档）

### 用例覆盖

1. time_bucket_gapfill() 和 interpolate() 函数组合用例
对interpolate补值算法中支持的所有聚合函数，在5种补值模式下 常量值（constant）、前值（prev）、后值（next）、线性值（linear）和 NULL ，3种可联合使用功能（LIMIT...OFFSET、JOIN、UNION）通过等价类划分和判定表驱动法等方法组合为多个查询语句，尽可能地在重工场景（shig）下全量覆盖插值查询用例

**【更正 1】`diff` 不是聚合函数，进不了 interpolate —— 聚合函数实为 7 种**

`diff()` 是窗口函数（`diff(expr) OVER (PARTITION BY <col> ORDER BY <ts>)`），不是聚合函数。实测两条路径都被服务端拒绝：

| 写法 | 服务端报错 |
| --- | --- |
| `interpolate(diff(col_float4_1) OVER (...), PREV)` | `ERROR: the first parameter of interpolate must be agg func` |
| `time_bucket_gapfill(ts,'1m') AS tb, diff(col_float4_1) OVER (...)` + `GROUP BY tb` | `ERROR: column "col_float4_1" must appear in the GROUP BY clause or be used in an aggregate function` / `ERROR: window functions are not allowed in GROUP BY` |

（`diff` 单独使用、套在子查询里再 `GROUP BY time_bucket_gapfill(ts,'1m')` 是可用的，但那已经不是插值查询。）

故 interpolate 维度实际可用的聚合函数为 **7 种：avg、count、max、min、sum、last、first**。

**【更正 2】联合使用功能实为 4 种，原文漏了「子查询」**

官方 `ts-data-query.md` 列的可联合使用功能是：LIMIT、LIMIT...OFFSET、**子查询**（非相关 FROM 子查询 / 相关与非相关 WHERE 子查询）、JOIN、UNION。本轮取 LIMIT...OFFSET / JOIN / UNION 三种落地；子查询形式（`select time_bucket_gapfill(tt, 2*86400) as c, interpolate(count(b), null) from (select ... group by tt) group by c`）实测可用，留待后续补。

不使用笛卡尔积方式组织用例，数据类型、聚合函数、补值模式和可联合使用功能取最大数集合量组织用例。**【更正 3】本轮组织 7 条 SQL 查询语句用例（原文写 8 条）**

原文的取数前提「时序数据类型中有 5 种数值类型」对 KaiwuDB 成立（INT2/INT4/INT8/FLOAT4/FLOAT8），但**在重工 shig 模型的表里只落地了 3 种数值列**：

| 表 | 数值列 |
| --- | --- |
| `db_shig.t_cnc` | `col_smallint_1..3`(INT2)、`col_int_1..2`(INT4)、`col_float4_1`(FLOAT4) |
| `db_shig.t_electmeter` | `col_smallint_1`(INT2)、`col_int_1..16`(INT4)、`col_float4_1..30`(FLOAT4) |

**INT8 / FLOAT8 在两表里都没有列**，要覆盖得先扩模型（见「实测验证结论」的覆盖缺口）。按最大集合量取数：聚合函数(7) > 补值模式(5) > 数值类型(3) = 联合使用(3)，**最大集合是聚合函数 → 7 条**，其他维度只要在某一条SQL语句中出现即认为已覆盖。

2. FILL子句查询用例
设计若干查询语句覆盖各时序数据类型的 EXACT、PREVIOUS、NEXT、CLOSER、CONSTANT、LINEAR 六种 FILL 子句插值模式，每种模式生成一条查询语句（6 Query SQL）

**【更正 4】FILL 子句受类型矩阵约束，且 WHERE 只能是「全主标签 + 常量 ts」**

| 约束 | 实测结论 |
| --- | --- |
| 类型支持矩阵 | INT2/INT4/INT8、FLOAT4/FLOAT8 支持全部 6 种模式；BOOL、CHAR/NCHAR/VARCHAR/NVARCHAR、VARBYTES 支持 5 种（**无 LINEAR**，字符串类型对 LINEAR 返回 NULL） |
| WHERE 条件 | 必须给全**所有**主标签 + ts，且只能是精确匹配。少给一个主标签即报 `the conditions of FILL clause must only be ts col and pTag` |
| ts 取值 | 必须是**常量**：`now()` / `current_timestamp` / `NOW() - INTERVAL` 均报 `the conditions of FILL clause only supports single column and constant` |
| 投影列数 | 文档正文写「只允许单列」，实测多列也可（如 `SELECT ts, col_float4_1 ... FILL(EXACT)` 能跑）；本轮按单列落地（更保守） |
| 常量填充 | `FILL(CONSTANT, 7)` 的常量与列类型不兼容时该列返回 NULL |

### 计划编排设计

使用并发线程组，每个查询使用一个独立线程组，查询频率设置在15min以上一次，各个用例之间使用互质数的查询间隔以尽可能避免多个查询同时请求KaiwuDB形成查询热点

落地口径（`ConstantThroughputTimer.throughput` 的单位是 **次/分钟**，故 1 次/15min = 0.066666667）：13 条用例的间隔取 13 个互不相同的素数分钟数

```
17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67   （分钟）
```

两两互质 → 不会撞点；全部 ≥ 15min → 满足频率上限。

## 实测验证结论（2026-11-03）

> 验证环境：容器 `kaiwudb-smoke`（KaiwuDB 3.2.0，TLS）、真实 `db_shig` 表结构（由 `test_model_shig_eximport.yaml` 生成 DDL）+ 含人为缺口的种子数据、JMeter 5.6.3 端到端。

### 一、已验证可用（用例即按此落地）

| 结论 | 证据 |
| --- | --- |
| `interpolate()` 5 种补值模式全部可用：constant / prev / next / linear / NULL | 缺口设备上实测：PREV→前值、NEXT→后值、LINEAR→按时间距离线性插值（10/20/30/40/50）、NULL→缺口为 NULL、constant→常量 |
| `interpolate()` 支持 7 种聚合函数 avg/count/max/min/sum/last/first | 逐个实测通过 |
| `time_bucket_gapfill()` 必须配 `GROUP BY`；**外层 GROUP BY 不能用 SELECT 别名**，要重复写完整表达式 | `GROUP BY tb` → `ERROR: column "tb" does not exist`；`GROUP BY time_bucket_gapfill(tt, 2*60)` 可通过 |
| `FILL` 子句 6 种模式全部可用 | PREVIOUS→`V1Z`、NEXT→`242694`、CLOSER→`C0A`、LINEAR→`2666.520020`、CONSTANT→`7`、EXACT→NULL（秒精度点无行，属正确语义） |
| `FILL` 的 WHERE 需给全所有主标签 + 常量 ts | 少给主标签 → `the conditions of FILL clause must only be ts col and pTag`；`now()` 类表达式 → `only supports single column and constant` |
| **JMeter 的 JDBC sampler 会替换查询文本里的 `${}` 函数** | A/B 实测：`ts = '${__time(yyyy-MM-dd HH:mm:ss)}'` 正常执行；`ts = 'ZZZ-not-a-timestamp'` 60/60 报错。**⇒ FILL 的 ts 可用 JMeter 内置函数动态取值，无需改生成器** |
| JDBC 会话时区跟随客户端 JVM 时区 | JVM `-Duser.timezone=UTC` → `SHOW TIME ZONE` 返回 UTC。⇒ `${__time()}`（JVM 本地时刻）、写入路径时间戳、FILL 字面量三者同一时钟 |
| **`time_bucket_gapfill()` 的桶粒度必须细于时间轴空洞** | 空洞 30s 时用 `'1m'` 桶：空洞落在桶内部 → 桶不空 → gapfill 不补桶、interpolate 无从补起（**不报错，只是白查**）。改 `'10s'` 桶后，30s 空洞正好切出 3 个空桶并被填上 |
| **同一 SELECT 列表里同一列上放两个 `interpolate()` 且其中含 `count()`** | `count()` 投影没有独立计算，会复用同组内前一个投影的补值结果（连模式一起），返回类型在计划期与执行期之间漂移（int8 ↔ float8）。① 简单查询协议（`kwbase sql`）：count 列取到前一个投影的浮点补值（如 14.5），客户端解码失败 `ERROR: strconv.ParseInt: parsing "14.5": invalid syntax`，CLI 观察为「0 行」或「部分结果 + 报错」；② 预处理语句协议（JDBC）：服务端计划缓存类型校验先失败 `ERROR: cached plan must not change result type`（**任何投影顺序都失败**）。对照：异列、单个 `interpolate()`、不含 `count()` 均正常 ⇒ 每条查询的 SELECT 只用一个 `interpolate()`。**3.2.0 与 3.3.1 均复现**；工单材料见 `docs/issues/interpolate-multi-projection-count.md` |

### 二、生成器侧硬约束（决定了用例只能这么写）

| 约束 | 实测报错 / 机制 | 用例里的规避方式 |
| --- | --- | --- |
| `?` 一律按 VARCHAR 绑定 | `float4/int2/int4 = varchar` → `ERROR: unsupported comparison operator` | `?` 只绑 varchar 列 |
| 首主标签没有种子文件 | `ptag_varchar_1 = ?` 落到兜底值 `device_1`，恒不匹配 | 过滤列改用 `ptag_varchar_2` / `rtag_varchar_1`（有种子） |
| `ts = ?` 走不通 | VARCHAR 绑参 → `unsupported comparison operator: <timestamptz(3)> = <varchar>` | ts 走字面量 `${__time(...)}` |
| FILL 需要全部主标签，而首主标签只能写字面量 | 首主标签由写路径 runtime 派生为 `{threadNum}_{deviceIndex}` | 取 `'0_1'`（对应 `device_start=1` / `num_threads=20` / `device_per_thread=50`），多端扩展改 `device_start` 时需同步 |

### 三、覆盖缺口（待决策，本轮按「保持现状」处理）

- **时序数据类型全集**（`sql-reference/data-type/data-type-ts-db.md`）：时间戳列 TIMESTAMP / TIMESTAMPTZ；数据列类型 **12 种** —— INT2、INT4、INT8、FLOAT4、FLOAT8、BOOL、CHAR、NCHAR、VARCHAR、NVARCHAR、VARBYTES、GEOMETRY。
- **shig 两表合并覆盖 5 种**：CHAR、VARCHAR、INT2、INT4、FLOAT4。
- **缺口 7 种**：INT8、FLOAT8、BOOL、NCHAR、NVARCHAR、VARBYTES、GEOMETRY（GEOMETRY 不在 FILL 的类型支持矩阵内，补值维度不涉及）。
  - 对 interpolate 组：数值类型只覆盖 3/5（缺 INT8、FLOAT8）—— 这也是本轮该组按 7 条（而非 8 条）定数的直接原因。
  - 对 FILL 组：BOOL / NCHAR / NVARCHAR / VARBYTES 无列可查。
- 补齐的前置条件（尚未验证）：① 生成器 `config_parser/models.py:50` 禁止 primary_tags 用 `float4/float8/nvarchar`，这些只能落 data_cols；② 种子生成器已确认支持 INT8/FLOAT8（`seed_data_generator/adapter.py:39-42`），但 **BOOL / VARBYTES / NCHAR / NVARCHAR / GEOMETRY 的 `val_range` 生成路径未验证**。

### 四、落地形态

- 配置文件：`docs/confs/test_cfg_shig_missing_fill.yaml`（配套 `docs/confs/test_model_shig_missing_fill.yaml`），基线是 **不带 eximport 的 shig 配置**（`integration-test/configs/test_cfg_shig.yaml` + `test_model_shig.yaml`），原 12 条查询与 pub_sub_config 原样保留，追加 **13 条补值用例**。
- 13 条 = interpolate/gapfill 组 7 条（每种聚合函数一条）+ FILL 子句组 6 条（每种模式一条）。
- **缺值写入配置与补值用例的适配**（write_config 的 `missing` 段）：

  | 参数 | 取值 | 理由 |
  | --- | --- | --- |
  | `probability` | 0.5 | 一半批次有缺口、一半完整，完整数据与缺口数据两条路径都覆盖 |
  | `ts_count` | 30 | 写入节奏 60s/批（throughput=1.0 次/分钟）、`batch_lines=60`×`ms_step=1s` ⇒ 每批本应覆盖 60s；截掉尾部 30 个时间戳后该批只覆盖 30s，与下一批之间留下 **约 30s 的时间轴空洞**，正是补值要跨的缺口 |
  | `device_count` | 0 | 缺失语义是「尾部截断 + 交集」：两维都配时只有**尾部设备**才有空洞，非尾部设备时间轴完整。而 interpolate 组按 `ptag_varchar_1` 分组、FILL 组固定查单台设备，要让它们稳定命中缺口就必须让时间戳维度覆盖全部设备 ⇒ 设备维度不配（count=0 = 该维度不参与判定，时间戳维度作用于全部设备） |

  实测（`probability=1.0` 确定性变体，真实 shig 模型 + JMeter 端到端）：设备 `0_1` 的时间轴稳态为 **每批 30 行、批间缺口 30.9s**；空洞正中间（`2026-11-03 07:50:10`，两侧分别有 `07:49:54.437` 与 `07:50:25.353`）做 FILL：`EXACT→NULL`、`PREVIOUS→47064.02`（空洞前）、`NEXT→1145.46`（空洞后）、`CLOSER→1145.46`（就近）、`LINEAR→23948.79`（跨 31s 空洞插值）——**补值确实跨过了 write-missing-data 造出的缺口**。
- 验证：`jmeter -n` 跑真实 shig 模型（写入并发进行），13 条补值用例 **0 失败**；`pytest tests/` 951 passed / 11 skipped。
- 未纳入本轮：`diff` 相关用例（服务端不支持）、子查询联合形式的用例、FILL 组的设备维度缺口场景（因 `device_count=0` 设备维度未参与）。

## 参考资料
聚合函数：
官网：https://www.kaiwudb.com/docs/#/sql-reference/functions/functions-ts-db.html#%E8%81%9A%E5%90%88%E5%87%BD%E6%95%B0
本地文档：/home/liujin/workspace/kwbase-docs/docs_kaiwuDB/sql-reference/functions/functions-ts-db.md#%E8%81%9A%E5%90%88%E5%87%BD%E6%95%B0
插值查询：
官网：https://www.kaiwudb.com/docs/#/db-administration/data-query/ts-data-query.html#%E6%8F%92%E5%80%BC%E6%9F%A5%E8%AF%A2
本地文档：/home/liujin/workspace/kwbase-docs/docs_kaiwuDB/db-administration/data-query/ts-data-query.md#%E6%8F%92%E5%80%BC%E6%9F%A5%E8%AF%A2
FILL 子句语法（ts-select.md「插值查询」一节，含类型支持矩阵）：
本地文档：/home/liujin/workspace/kwbase-docs/docs_kaiwuDB/sql-reference/dml/ts-db/ts-select.md
时序数据类型全集：
本地文档：/home/liujin/workspace/kwbase-docs/docs_kaiwuDB/sql-reference/data-type/data-type-ts-db.md
