# interpolate() 同一列多投影时 count() 投影结果异常：简单查询协议下串列取到前一个投影的浮点补值，预处理语句协议下报 cached plan must not change result type

## 摘要

在时序表上做 `time_bucket_gapfill()` 插值查询时，**同一列上放两个 `interpolate()` 且其中一个是 `count()`**，`count()` 投影得不到独立、稳定的补值结果。同一根因在两种客户端协议下表现为两种症状：

| 客户端协议 | 现象 |
| --- | --- |
| 简单查询（`kwbase sql` CLI） | `count()` 列**取到前一个投影的浮点补值**（如 `14.5`），服务端按 int8 返回，客户端按整数解码失败：`ERROR: pq: strconv.ParseInt: parsing "14.5": invalid syntax`；经 CLI 观察时表现为「0 行」或「部分结果 + 报错」 |
| 预处理语句（JDBC `PreparedStatement`） | 服务端自身的计划缓存类型校验先失败：`ERROR: cached plan must not change result type`（**任何投影顺序都失败**，连 CLI 下正确的顺序也一样） |

**这不是数据或过滤条件问题**：同一张表、同一批数据、同一 WHERE，仅把两个投影的顺序调换，CLI 下结果就完全正确（见下方对照）；异列、单个 `interpolate()`、第二个不是 `count()` 也都正常。

## 影响

* **JDBC 客户端（稳定性测试流水线走的就是这条路径）**：查询直接抛 `KSQLException: cached plan must not change result type`，sampler 失败。
* **`kwbase sql` CLI**：表现为 0 行或「部分结果 + 报错」，**不报错时最容易被误判为"没数据"**。
* 典型踩坑写法：一条 SQL 同时输出多个补值指标，例如
  `interpolate(avg(v), PREV) AS avg_v, interpolate(count(v), PREV) AS cnt`。

## 环境

| 项 | 值 |
| --- | --- |
| 复现版本 | **KaiwuDB 3.2.0**（CLI 复现）与 **V3.3.1-6-g54ecd336eb-dirty**（build 2026/11/03，CLI + JDBC 均复现）——**该缺陷在新版仍未修复** |
| 客户端 | `kwbase sql` CLI（Go/pq 栈，报错前缀 `pq:`）、`kaiwudb-jdbc-3.2.0.jar`（Java 栈，报错前缀 `com.kaiwudb.util.KSQLException`） |
| 表类型 | 时序表（`CREATE TS DATABASE`），单列 float4 数据列 + 单主标签 |
| 复现材料 | `docs/issues/interpolate_multi_projection_repro.sql`（可直接粘贴执行）、`docs/issues/interpolate_multi_projection_repro.sh`（一键复现，支持容器/本地、TLS/insecure） |

## 最小复现

```sql
CREATE TS DATABASE IF NOT EXISTS bug_interp;
CREATE TABLE IF NOT EXISTS bug_interp.t1 (
  ts timestamp not null,
  v1  float4
) TAGS (dev varchar(32) not null) PRIMARY TAGS (dev);

INSERT INTO bug_interp.t1
SELECT '2026-11-03 08:10:00.667'::timestamp + s * interval '1 second',
       s::float4, 'dev1'
FROM generate_series(1, 30) s;
```

### ① 缺陷用例（count 在第二位）

```sql
SELECT time_bucket_gapfill(ts, '10s') AS tb,
       interpolate(avg(v1), PREV)  AS a_avg,
       interpolate(count(v1), PREV) AS b_count
FROM bug_interp.t1
GROUP BY tb ORDER BY tb;
```

**CLI 实测输出**：

```
             tb             | a_avg | b_count
----------------------------+-------+----------
  2026-11-03 08:10:00+00:00 |     5 |       9
(1 row)
(error encountered after some results were delivered)
ERROR: pq: strconv.ParseInt: parsing "14.5": invalid syntax
```

正确结果应为 4 行：`a_avg = 5 / 14.5 / 24.5 / 30`，`b_count = 9 / 10 / 10 / 1`。

**关键观察**：报错的 `14.5` 正是第 2 个 10s 桶（行 `s=10..19`）的 `avg(v1)`。即 `b_count` 列拿到的是**另一个投影的浮点补值**。

**JDBC 实测输出**（同一段 SQL，用 `PreparedStatement`）：

```
=> 抛异常: com.kaiwudb.util.KSQLException: ERROR: cached plan must not change result type
```

### ② 对照：仅调换两个投影的顺序

```sql
SELECT time_bucket_gapfill(ts, '10s') AS tb,
       interpolate(count(v1), PREV) AS b_count,
       interpolate(avg(v1), PREV)  AS a_avg
FROM bug_interp.t1
GROUP BY tb ORDER BY tb;
```

**CLI 实测输出（完全正确）**：

```
             tb             | b_count | a_avg
----------------------------+---------+--------
  2026-11-03 08:10:00+00:00 |       9 |     5
  2026-11-03 08:10:10+00:00 |      10 |  14.5
  2026-11-03 08:10:20+00:00 |      10 |  24.5
  2026-11-03 08:10:30+00:00 |       1 |    30
(4 rows)
```

但**同一条 SQL 在 JDBC 下仍报** `cached plan must not change result type` —— 也就是说，"调换顺序"只在 CLI 下有效，JDBC 路径无解。

### ③ 对照：第二个换成 max

```sql
SELECT time_bucket_gapfill(ts, '10s') AS tb,
       interpolate(avg(v1), PREV) AS a_avg,
       interpolate(max(v1), PREV) AS b_max
FROM bug_interp.t1
GROUP BY tb ORDER BY tb;
```
CLI 与 JDBC 均正常返回 4 行 ⇒ 只在涉及 `count()` 时出问题。

### ④ 对照：两个 interpolate 取不同列

```sql
-- t3(ts timestamp, v1 float4, v2 float4)
SELECT time_bucket_gapfill(ts, '10s') AS tb,
       interpolate(avg(v1), PREV)  AS a_avg,
       interpolate(count(v2), PREV) AS b_count
FROM bug_interp.t3
GROUP BY tb ORDER BY tb;
```
CLI 与 JDBC 均正常返回 ⇒ 必须作用在同一列上才触发。

## 机制观察

* 同列两个 `interpolate()` 时，**`count()` 投影没有独立计算，而是复用同一组内前一个投影的补值结果，连补值模式一起复用**：
  - `interpolate(avg(v1), PREV)` + `interpolate(count(v1), NEXT)` → count 列拿到的是 **PREV 版的 avg 值**（14.5），而不是 NEXT 的结果。
* 因此 `count()` 投影的**返回类型在计划期与执行期之间不稳定**（计划按 int8、执行产出 float8）：
  - 简单查询协议：客户端按 int8 解码 → `strconv.ParseInt: parsing "14.5"`；
  - 预处理语句协议：服务端计划缓存校验先发现类型漂移 → `cached plan must not change result type`。
* `count()` 放在**第一位**时，CLI 下全部正确，但 JDBC 路径仍失败 —— 说明 count 投影的结果类型本身就不稳定，与顺序无关。

## 触发条件矩阵（均为实测）

| 组合（同一 SELECT 列表） | CLI | JDBC |
| --- | --- | --- |
| 同列 `avg(v1)` + `count(v1)`，`count` 在第二位 | **复现**（count 列收到浮点补值 → 解码失败） | **复现**（`cached plan must not change result type`） |
| 同列 `count(v1)` + `avg(v1)`，`count` 在第一位 | 正常 | **复现**（`cached plan must not change result type`） |
| 同列 `avg(v1)` + `max(v1)`（第二个不是 count） | 正常 | 正常 |
| **异列** `avg(v1)` + `count(v2)` | 正常 | 正常 |
| 单个 `interpolate()`（count 或 avg） | 正常 | 正常 |
| 单设备 / 多设备 | 均复现 | — |
| 时间戳整秒 / 带毫秒 | 均复现 | — |
| 带 WHERE（主标签 / 时间范围）/ 不带 WHERE | 均复现 | — |

归纳：**同一列上出现 ≥2 个 `interpolate()` 且其中含 `count()`** 即触发；异列、单个 `interpolate()`、不含 `count()` 均正常。

## 期望行为

1. 同一 SELECT 列表中多个 `interpolate()` 的结果不应互相串列 —— `count()` 投影应返回计数（int8），且其返回类型在计划期与执行期之间保持稳定。
2. 即便内部实现暂不支持同列多投影，也应**明确报错**（如 `not supported`），而不是把 float 值塞进 int8 结果列、让客户端解码失败，或让计划缓存类型校验在无关查询上炸掉。

## 规避方式（当前可用的绕法）

服务端修复前，同一条 SQL 里**只放一个 `interpolate()`**，其余指标拆成独立的查询执行。

注意：**"把 count 调换到投影第一位"这个绕法只在 CLI 下有效**，JDBC（预处理语句）路径下仍然失败，不要据此判断问题已规避。

## 附带发现（非缺陷，供参考）

`time_bucket_gapfill()` 的桶粒度必须**细于**时间轴上的数据空洞，否则空洞落在桶内部、桶不空 → gapfill 不会补出空桶、`interpolate()` 无从补起（**不报错，但不补任何东西**）。这属于「按桶补行」的设计语义，**不是缺陷**，但文档未说明，容易被误认为 interpolate 失效。
