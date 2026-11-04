#!/usr/bin/env bash
# ============================================================================
# KaiwuDB bug 复现驱动脚本（interpolate() 多投影时 count() 投影串列）
#
# 用法：
#   # 容器内实例（默认）
#   ./interpolate_multi_projection_repro.sh [container_name]
#
#   # 本地实例（3.3.0 等）
#   REPRO_MODE=local \
#   KW_BIN=/path/to/kwbase \
#   CERTS_DIR=/path/to/certs \
#   HOST=127.0.0.1:26257 \
#   ./interpolate_multi_projection_repro.sh
#
#   # 本地 insecure 实例
#   REPRO_MODE=local INSECURE=1 ./interpolate_multi_projection_repro.sh
#
# 退出码：0 = 缺陷已复现；1 = 未复现或环境异常
# ============================================================================
set -uo pipefail

MODE="${REPRO_MODE:-docker}"          # docker | local
CONTAINER="${1:-kaiwudb-smoke}"
KW_BIN="${KW_BIN:-/kaiwudb/bin/kwbase}"
CERTS_DIR="${CERTS_DIR:-/kaiwudb/certs}"
HOST="${HOST:-127.0.0.1:26257}"
DB_USER="${DB_USER:-root}"
INSECURE="${INSECURE:-0}"

SQL="SELECT time_bucket_gapfill(ts,'10s') AS tb, %s FROM bug_interp.t1 GROUP BY tb ORDER BY tb;"

kw() {
  if [ "$MODE" = "docker" ]; then
    docker exec "$CONTAINER" "$KW_BIN" sql \
      --certs-dir="$CERTS_DIR" --host="$HOST" -u "$DB_USER" --format=table -e "$1" 2>&1
  else
    "$KW_BIN" sql \
      $([ "$INSECURE" = "1" ] && echo "--insecure" || echo "--certs-dir=$CERTS_DIR") \
      --host="$HOST" -u "$DB_USER" --format=table -e "$1" 2>&1
  fi
}

echo "=== 目标：mode=$MODE host=$HOST insecure=$INSECURE ==="

echo "=== 1/5 建库建表（每次重建，保证数据干净）==="
kw "CREATE TS DATABASE IF NOT EXISTS bug_interp; \
     DROP TABLE IF EXISTS bug_interp.t1; \
     CREATE TABLE bug_interp.t1 (ts timestamp not null, v1 float4) \
       TAGS (dev varchar(32) not null) PRIMARY TAGS (dev);" | tail -3

echo "=== 2/5 造数（30 行，跨 4 个 10s 桶）==="
kw "INSERT INTO bug_interp.t1 \
     SELECT '2026-11-03 08:10:00.667'::timestamp + s*interval '1 second', s::float4, 'dev1' \
     FROM generate_series(1,30) s;" | tail -1

echo
echo "=== 3/5 缺陷用例：同列 count() 在第二位（预期报错/空结果）==="
out=$(kw "$(printf "$SQL" "interpolate(avg(v1),PREV) AS a_avg, interpolate(count(v1),PREV) AS b_count")")
echo "$out"
rc=1
if echo "$out" | grep -q "ParseInt\|invalid syntax"; then
  echo ">>> 缺陷已复现：count 投影收到浮点补值，客户端解码失败"; rc=0
elif [ "$(echo "$out" | grep -c '^2026')" -eq 0 ]; then
  echo ">>> 缺陷已复现（表现为 0 行，无报错）"; rc=0
else
  echo ">>> 未复现，结果如下（请把该输出贴到工单）"
fi

echo
echo "=== 4/5 对照 A：仅调换投影顺序（count 在第一位，预期 4 行全对）==="
kw "$(printf "$SQL" "interpolate(count(v1),PREV) AS b_count, interpolate(avg(v1),PREV) AS a_avg")"

echo
echo "=== 5/5 对照 B：第二个换成 max（预期 4 行全对）==="
kw "$(printf "$SQL" "interpolate(avg(v1),PREV) AS a_avg, interpolate(max(v1),PREV) AS b_max")"

exit $rc
