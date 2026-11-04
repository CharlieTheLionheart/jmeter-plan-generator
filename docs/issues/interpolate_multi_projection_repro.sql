-- ============================================================================
-- KaiwuDB bug 最小复现脚本
--
-- 缺陷：同一列上放两个 interpolate()，且 count() 不在 SELECT 列表第一位时，
--       count() 投影拿到的是前一个投影的浮点补值（而不是计数），
--       客户端按 int8 解码失败：
--         ERROR: pq: strconv.ParseInt: parsing "14.5": invalid syntax
--       经 kwbase sql 观察时表现为「0 行」或「部分结果 + 报错」。
--
-- 环境：KaiwuDB 3.2.0（TLS 单节点，26257）
-- 运行：
--   docker cp interpolate_multi_projection_repro.sql <container>:/tmp/
--   docker exec <container> sh -c '/kaiwudb/bin/kwbase sql \
--       --certs-dir=/kaiwudb/certs --host=127.0.0.1:26257 -u root \
--       --format=table -e "$(cat /tmp/interpolate_multi_projection_repro.sql)"'
--
--   注：① 与 ② 分开执行 —— ① 会报错中断脚本。
-- ============================================================================

-- ---------- 建表 + 造数 ----------
CREATE TS DATABASE IF NOT EXISTS bug_interp;
CREATE TABLE IF NOT EXISTS bug_interp.t1 (
  ts timestamp not null,
  v1  float4
) TAGS (dev varchar(32) not null) PRIMARY TAGS (dev);

-- 30 行连续数据，跨 4 个 10s 桶
INSERT INTO bug_interp.t1
SELECT '2026-11-03 08:10:00.667'::timestamp + s * interval '1 second',
       s::float4, 'dev1'
FROM generate_series(1, 30) s;

-- ---------- ① 缺陷用例：count() 在第二位 ----------
SELECT time_bucket_gapfill(ts, '10s') AS tb,
       interpolate(avg(v1), PREV)  AS a_avg,
       interpolate(count(v1), PREV) AS b_count
FROM bug_interp.t1
GROUP BY tb ORDER BY tb;
-- 期望（正确行为）：a_avg=5/14.5/24.5/30，b_count=9/10/10/1
-- 实测：第一行输出正确，随后
--   ERROR: pq: strconv.ParseInt: parsing "14.5": invalid syntax
--   （b_count 列收到的是 a_avg 的浮点补值 14.5，客户端按 int8 解码失败）

-- ---------- ② 对照：仅把两个投影调换顺序（count 在第一位） ----------
SELECT time_bucket_gapfill(ts, '10s') AS tb,
       interpolate(count(v1), PREV) AS b_count,
       interpolate(avg(v1), PREV)  AS a_avg
FROM bug_interp.t1
GROUP BY tb ORDER BY tb;
-- CLI 实测：4 行全部正确
--   tb                   | b_count | a_avg
--   2026-11-03 08:10:00 |       9 |     5
--   2026-11-03 08:10:10 |      10 |  14.5
--   2026-11-03 08:10:20 |      10 |  24.5
--   2026-11-03 08:10:30 |       1 |    30
-- 两条 SQL 的 WHERE / GROUP BY / 数据完全相同，仅投影顺序不同，结果却一个错一个对。
--
-- ⚠ 但同一条 SQL 用 JDBC PreparedStatement 执行时仍然失败：
--     com.kaiwudb.util.KSQLException: ERROR: cached plan must not change result type
--   ⇒ "把 count 调到第一位" 只是 CLI 下的绕法，JDBC（预处理语句）路径无解。

-- ---------- ③ 对照：第二个换成 max（不是 count）----------
SELECT time_bucket_gapfill(ts, '10s') AS tb,
       interpolate(avg(v1), PREV) AS a_avg,
       interpolate(max(v1), PREV) AS b_max
FROM bug_interp.t1
GROUP BY tb ORDER BY tb;
-- 实测：4 行全部正确 ⇒ 只在第二个是 count() 时出问题

-- ---------- ④ 对照：两个 interpolate 取不同列 ----------
CREATE TABLE IF NOT EXISTS bug_interp.t3 (
  ts timestamp not null,
  v1  float4,
  v2  float4
) TAGS (dev varchar(32) not null) PRIMARY TAGS (dev);
INSERT INTO bug_interp.t3
SELECT '2026-11-03 10:10:00'::timestamp + s * interval '1 second',
       s::float4, s * 100::float4, 'dev1'
FROM generate_series(1, 30) s;

SELECT time_bucket_gapfill(ts, '10s') AS tb,
       interpolate(avg(v1), PREV)  AS a_avg,
       interpolate(count(v2), PREV) AS b_count
FROM bug_interp.t3
GROUP BY tb ORDER BY tb;
-- 实测：4 行全部正确 ⇒ 必须作用在同一列上才会触发
