---
name: kwjdbc-jmx-smoke
description: >
  端到端 JMX smoke 测试 — kwjdbc-svt 经 `jmeter -n` 命令行模式跑通：
  用 `tests/kwjdbc_svt/fixtures/test_model.yaml` + `test_cfg.yaml` 调
  `python -m kwjdbc_svt.main` 生成 .jmx，再用 Apache JMeter 5.6+ 跑，
  报告 setup / loader 阶段错误。触发词："smoke", "jmeter -n",
  "端到端测试", "end-to-end", "JMX smoke", "跑 jmeter",
  "verify .jmx"。来源：2026-07-13 main-entry 落地 bug 修复会话。
---

# kwjdbc-jmx-smoke

kwjdbc-svt 端到端 smoke 测试。

跑 CLI 生成 `.jmx` 后用 `jmeter -n` 跑，把 JMX 层 bug **在进 CI 之前**拦截。

## 何时调用

- merge `main-entry` 后验证生成的 `.jmx` 能被 JMeter 加载
- 改 `jmx_skeleton_generator` / `write_groups` / `query_groups` /
  `shared_memory_initializer` / `jdbc_datasource` 后
- 任何会改 sampler / thread group 行为的 PR 前

## 何时**不**调

- 纯 Pydantic 模型改动 — 单测已覆盖
- 改 docstring / 注释
- 文档-only PR（`docs/`、`openspec/changes/*/design.md` 等）

## 前置 / 入参

调用前先备齐：

| 项 | 怎么找 |
| --- | --- |
| Apache JMeter 5.6+ 二进制 | `which jmeter` 或 `ls /home/liujin/workspace/tools/apache-jmeter-*/bin/jmeter` |
| JMeter lib（CSV/JDBC extras） | 同上 `lib/`，确认 `lib/ext/kaiwudb-jdbc-*.jar` 存在 |
| 项目 venv | `<repo>/venv/bin/activate` |
| 测试 fixture yaml | `ls tests/kwjdbc_svt/fixtures/`，已就位 |
| （可选）KaiwuDB 端点 | `-Jdb_url=jdbc:kaiwudb://<host>:<port>/defaultdb` |

> **JDBC URL 必须连 `defaultdb`**，**不可**连业务库（`iot_monitor` / `iot` 等）。
> setup 阶段第一件事就是 `CREATE DATABASE IF NOT EXISTS iot_monitor`——
> 这些时序库**执行 DDL 之前并不存在**，连业务库直接拒连 → 整个 setup 链炸。
> `defaultdb` 是 KaiwuDB 系统库，永远在；用它当 bootstrap 连接，建完库
> 之后 sampler 再切到 `iot_monitor` 写数据。同理 fixture `test_cfg.yaml`
> 里的 `db_url` 也必须填 `defaultdb`。

## 流程

### 1. 生成 JMX

```bash
source venv/bin/activate
rm -rf /tmp/jmeter-smoke/out && mkdir -p /tmp/jmeter-smoke
python -m kwjdbc_svt.main \
    tests/kwjdbc_svt/fixtures/test_model.yaml \
    tests/kwjdbc_svt/fixtures/test_cfg.yaml \
    -o /tmp/jmeter-smoke/out
```

预期 `rc = 0`，产出 `test_plan.jmx` + `seeds/` 子树。

非零不要进 JMeter——bug 在 `kwjdbc_svt.main`，不在 .jmx：

- `ConfigParserError` → fixture yaml schema 不匹配
- `SeedGenError` → seed 生成 schema 不匹配
- `DdlGenerationError` / `JmxGenerationError` → 生成层

### 2. 找 JMeter

```bash
JMETER=$(command -v jmeter || ls /home/liujin/workspace/tools/apache-jmeter-*/bin/jmeter | head -1)
test -x "$JMETER" || { echo "no jmeter found; smoke skipped"; exit 0; }
```

无 jmeter 跳过 3-5 步，只报"未跑 jmeter"。

### 3. 无 DB 跑（暴露非 DB bug）

```bash
cd /tmp/jmeter-smoke
rm -f jmeter.log
timeout 30 "$JMETER" -n -t /tmp/jmeter-smoke/out/test_plan.jmx \
    -Jtest_duration=3 -Jnum_threads=1 \
    -Jdevice_start=1 -Jdevice_per_thread=1 \
    -j /tmp/jmeter-smoke/jmeter.log 2>&1 | tail -10
```

**好信号**：

- `Created the tree successfully using …/test_plan.jmx` — JMX 加载成功
- `Starting standalone test @ …`
- `Starting setUp ThreadGroup: 1 : DDL Setup`
- `Starting setUp ThreadGroup: 2 : SharedMemory Setup`
- `summary = N in 00:00:0X …`（非零 sample 数 = 测试计划走完）

**常见 JMX 加载错误（一般性指导）**：

| log 模式 | 含义 | 排查方向 |
| --- | --- | --- |
| `unable to resolve class X` | Groovy 引用 JMeter classpath 没有的类 | 改 Groovy 用 JDK 内置类 |
| SyntaxError / MultipleCompilation from JSR223 | Groovy 表达式编译失败 | 看 script literal，查不对称大括号/引号转义 |
| `Cannot resolve external entity` from XML parser | .jmx 引用 `${...}` 在 parse 之前被 resolve | 改 `${__P(...)}` 形式或字面 |

无 DB 模式下唯一**可接受**错误：`ConnectException: Connection refused`
从 `kaiwudb.Driver.connect`（或等价 SocketException）— 表示测试计划走
过所有 setup 阶段，只在 JDBC driver 层失败。

### 4. （可选）连真 KaiwuDB 跑全链路

**容器镜像约定**（2026-07-22 确认）：

- 镜像默认 workdir 是 `/`，不是 `/kaiwudb/bin`
- `kwbase` 二进制在 `/kaiwudb/bin/kwbase`，**不在 `$PATH`**
- 调用时必须用**绝对路径** `/kaiwudb/bin/kwbase`
- 推荐镜像（按优先级）：
  1. `devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest`（nightly，F-17 已修）
  2. `kwdb/kwdb:latest`（F-17 仍触发，varchar rtag 静默丢 `""`）
- 避免用 `kwdb-x86_64-master-dbg` — F-17 会让 container 在 restart 时 segfault

```bash
docker run -d --name kaiwudb-smoke -p 26257:26257 -p 8081:8080 \
    --ulimit nofile=65536 \
    devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest \
    /kaiwudb/bin/kwbase start-single-node \
    --insecure --listen-addr=0.0.0.0:26257 --http-addr=0.0.0.0:8080

# 等 kwbase ready（端口监听）
# 命令格式与容器内 PATH 注意事项见 docs/refs/kaiwudb-kwbase-sql-reference.md §4.1 / §6。
for i in $(seq 1 30); do
    docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --insecure -e "select 1" >/dev/null 2>&1 && break
    sleep 1
done

"$JMETER" -n -t /tmp/jmeter-smoke/out/test_plan.jmx \
    -Jtest_duration=5 -Jnum_threads=1 \
    -Jdb_url=jdbc:kaiwudb://localhost:26257/defaultdb \
    -Jdb_username=root \
    -j /tmp/jmeter-smoke/jmeter-live.log 2>&1 | tail -10
```

**注意**：

- 别用 `docker start kaiwudb-smoke` 复用旧容器 — 老容器可能是 `kwdb/kwdb:latest` 或 `kwdb-x86_64-master-dbg`，仍带 F-17 bug。重建用 `docker rm -f kaiwudb-smoke` + `docker run`
- 容器内所有 `kwbase sql ...` 调用必须用**绝对路径** `/kaiwudb/bin/kwbase`，因为 `PATH` 里没有
- HTTP 端口用 8081（避免与本地其他服务冲突），但 JDBC 仍走 26257
- 容器起来后用 for 循环轮询 `select 1` 等待 kwbase ready（避免 sleep 固定时长误判）
- F-17 issue 详情见 `docs/issues/F17.md`

预期：setup/write/query 三阶段 `Err: 0 (0.00%)`，`jmeter-live.log`
加载后无 `ERROR`。

## 输出格式

smoke 收尾给结构化总结：

```markdown
## kwjdbc-jmx-smoke 总结
- JMX 加载:        pass/fail
- Setup 阶段:      DDL pass/fail + SharedMemory pass/fail
- Sampler 阶段:    write pass/fail/na + query pass/fail/na
- DB 连接:         跳过/拒绝/连通
- 结论:             全绿 / 具体回归
```

非全绿时列出每个失败阶段 + 生成器 file:line + 最小修复草图。

## 6. RESTful schemaless path（insecure / TLS 双模式）

> **模式限制（2026-07-27 行为变更）**：schemaless Login **必须**走 TLS 模式。
> 原因：Login 强制非空密码用户，`--insecure` 启动的 KaiwuDB 容器不支持
> `ALTER USER ... PASSWORD`（SQLSTATE 28P01），insecure 路径 Login 始终报
> `"the provided username and password did not match"`。
> 因此 `RestApiConfig.https_mode` Literal 收紧为 `["tls"]`（仅约束 schemaless
> 路径；JDBC 路径 §1-§5 仍可用 insecure，不受影响）。
> insecure fixture `tests/kwjdbc_svt/fixtures/test_cfg_schemaless.yaml`
> 已删除，TLS fixture `test_cfg_schemaless_tls.yaml` 是 schemaless 唯一入口。
> 详见 `docs/refs/kaiwudb-schemaless-write-reference.md` §6.3 +
> openspec/changes/rest-schemaless-write/design.md Decision 2。

`mode: schemaless` 路径走 REST API（`/restapi/login` + `/restapi/ddl` + `/restapi/influxdb` + `/restapi/query`），不复用 §1-§5 的 JDBC sampler。

### 6.0 容器前置（必须 TLS 重建才能跑 schemaless smoke）

JDBC 路径 (§1-§5) 沿用 §4 insecure 容器即可；schemaless 路径需重建 TLS 容器。
完整证书体系 + 命令说明见 `docs/refs/kaiwudb-tls-cert-reference.md` §3。

```bash
# 1) rm 旧容器（insecure 模式无 `/kaiwudb/certs/`，与 schemaless 不兼容）
docker rm -f kaiwudb-smoke

# 2) 新容器，先只起 /kaiwudb/bin/kwbase cert 流程（**不**直接 start-single-node）
docker run -d --name kaiwudb-smoke -p 26257:26257 -p 8081:8080 \
    --ulimit nofile=65536 \
    devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest \
    tail -f /dev/null

# 3) 在容器内生成 cert 集（CA + node + 客户端 root）
#    注意：--ca-cert 不是 kwbase cert create-ca 的 flag，
#    CA 证书自动写到 <certs-dir>/ca.crt；只需 --ca-key。
#    客户端 cert（client.root.crt/key）是 §6.0 step 5/6 免密登录 root 的前提，
#    缺它会导致 `kwbase sql` 卡在 `Enter password:`
#    （参见 §6.4.6）。
docker exec kaiwudb-smoke mkdir -p /kaiwudb/certs
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase cert create-ca \
    --certs-dir=/kaiwudb/certs \
    --ca-key=/kaiwudb/certs/ca.key
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase cert create-node \
    localhost $(hostname) 127.0.0.1 \
    --certs-dir=/kaiwudb/certs \
    --ca-key=/kaiwudb/certs/ca.key
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase cert create-client root \
    --certs-dir=/kaiwudb/certs \
    --ca-key=/kaiwudb/certs/ca.key

# 4) 拷 certs 到宿主机 + rm tail 容器 + 重建（PID 1 = kwbase）
#    **必须同时挂载 certs 和 data，否则用户/数据全部丢失**：
#      - /kaiwudb/certs        → cert 集（只读：:ro）
#      - /kwbase-data          → kwbase 数据目录（读写，**不在 /kaiwudb 下**）
#    旧版曾用 `docker exec -d` 在 tail 容器内启动 kwbase（保留 certs 但 PID 1 = tail，
#    docker ps COMMAND 列误导），现在改用 rm + 重建，PID 1 = kwbase 进程。
mkdir -p /tmp/kaiwudb-certs /tmp/kaiwudb-data
docker cp kaiwudb-smoke:/kaiwudb/certs/. /tmp/kaiwudb-certs/
docker cp kaiwudb-smoke:/kwbase-data/.   /tmp/kaiwudb-data/
docker rm -f kaiwudb-smoke
docker run -d --name kaiwudb-smoke -p 26257:26257 -p 8081:8080 \
    --ulimit nofile=65536 \
    -v /tmp/kaiwudb-certs:/kaiwudb/certs:ro \
    -v /tmp/kaiwudb-data:/kwbase-data \
    devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest \
    /kaiwudb/bin/kwbase start-single-node \
    --listen-addr=0.0.0.0:26257 --http-addr=0.0.0.0:8080 \
    --certs-dir=/kaiwudb/certs
#    重建后 `docker ps` COMMAND 列显示 `/kaiwudb/bin/kwbase…`，即 PID 1 = kwbase。

# 5) 等 kwbase ready（用 client.root cert 免密登录 root）
for i in $(seq 1 30); do
    docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
        -e "select 1" >/dev/null 2>&1 && break
    sleep 1
done

# 6) 建非空密码 root（**关键**：insecure 模式 ALTER USER PASSWORD 不支持）
#    此处用 step 3 生成的 client.root.crt/key 做 client cert 认证，
#    无需输入密码。语法见 docs/refs/kaiwudb-user-management-reference.md §3，
#    命令格式见 docs/refs/kaiwudb-kwbase-sql-reference.md §4.1。
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "CREATE USER root WITH PASSWORD 'root123'"

# 7) 拷 CA 证书到 fixtures（JMeter HTTPSampler.customizedSslContext 用）
docker cp kaiwudb-smoke:/kaiwudb/certs/ca.crt tests/kwjdbc_svt/fixtures/ca.crt
```

#### 6.0.2 建其他 SQL 用户（test / app / 等）

§6.0 step 6 用 client cert 登录 root 后，可继续建业务用户（典型场景：
schemaless / JDBC 测试 fixture 用非 root 账号）。**所有非 root 用户必须在
TLS 模式下用 `CREATE USER ... WITH PASSWORD` 创建**（insecure 模式
`ALTER USER PASSWORD` 报 SQLSTATE 28P01，参见 §6.4.1）。

```bash
# 1) 用 client.root cert 登录，建 test 用户（密码含 # 时 shell 用单引号包 SQL，
#    URL 形式登录时 # 必须 URL-encode 为 %23，参见下方验证步骤）
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "CREATE USER test WITH PASSWORD 'Znbase#1234'"

# 2) 列出所有用户（注意 SHOW USERS 不显示 PASSWORD 字段；
#    无法用 SQL 自检密码是否设置，必须用 REST / JDBC 实连验证）
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "SHOW USERS"
# → username  options    member_of
#   admin     CREATEROLE {}
#   root      CREATEROLE {admin}
#   test      ""         {}

# 3) 验证 test 用户可用密码登录（kwbase sql --url 形式，
#    postgresql://user:password@host:port/db?sslmode=require&sslrootcert=<ca.crt>）
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql \
    --url "postgresql://test:Znbase%231234@localhost:26257/defaultdb?sslmode=require&sslrootcert=/kaiwudb/certs/ca.crt" \
    -e "SELECT current_user"
# → current_user
#   test
```

> 若后续 fixture（`test_cfg.yaml` 等）需要用 test 用户跑 JDBC sampler，
> 同步更新其 `db_username` / `db_password` 字段，并跑一遍 §6.3 断言确认
> SetupTG / WriteTG / QueryTG 全绿。

> 完整 TLS 容器配置 + 调试见 `docs/refs/kaiwudb-tls-cert-reference.md`。
> KaiwuDB TLS 无官方调试文档；本 skill §6.4 调试条目随 smoke 实跑逐条增量。

#### 6.0.1 容器 ↔ 宿主机隔离陷阱（cert + data 生命周期）

> **易错点**：容器内 `/kaiwudb/certs/` 与宿主机文件系统**默认隔离**。
> JMeter 在宿主机跑，**无法**直接读容器路径。处理：

1. **`docker cp` 必须每次重做**（§6.0 step 7）：容器重建（步骤 1-2）会重新生成 ca.crt，旧 `tests/kwjdbc_svt/fixtures/ca.crt` 失效。JMeter 仍引用旧证书 → TLS 握手 fail（症状：DDL Login 100% 失败但无明确 cert mismatch 提示）。**容器重建 → 必须 docker cp 重做**。
2. **`.gitignore` 已包含 `tests/kwjdbc_svt/fixtures/*.crt`**（per-env 不可入库）：本地 fixture 误 commit 会让其他人共享一个不可复用的证书。
3. **`ca.crt` SAN 必须包含 JMeter 连接的目标**：§6.0 step 3 `kwbase cert create-node` 的参数列表决定 SAN。如果 JMeter 通过 `127.0.0.1:8081` 连，必须含 `127.0.0.1`；通过容器 IP 连需先 `docker inspect kaiwudb-smoke | grep IPAddress` 取 IP 加到 create-node。SAN 不匹配 → TLS handshake fail 但 JTL 不直接报（看 `jmeter-schemaless.log` 里 `SSLHandshakeException` / `certificate_unknown`）。
4. **`ca.key` / `node.crt` / `node.key` 永远留在容器**：只 `docker cp` 出 `ca.crt`，私钥不外传（即便测试环境）。
5. **`hostname` 在容器内 = 容器 hostname**（如 `bd8c95fcb0d1`）：§6.0 step 3 用 `$(hostname)` 取的是**宿主机** hostname（在 `docker exec` 时由宿主机解析），不是容器 hostname。两侧 SAN 含义不同——若 JMeter 用容器 hostname 连会 fail；用宿主机 hostname 连也 fail（因为容器内 hostname 与宿主机 hostname 一般不同）。**安全做法**：create-node 只传 `localhost 127.0.0.1 <docker-host-ip>` 三段，JMeter 一律用 `127.0.0.1:8081` 连。
6. **数据目录 `/kwbase-data` 不在 `/kaiwudb/` 下**（容易猜错）：kwbase 默认 store 路径是 `/kwbase-data`，**不是** `/kaiwudb/data`。§6.0 step 4 重建容器时**必须挂载 `-v /tmp/kaiwudb-data:/kwbase-data`**，否则用户、表、数据全部丢失（容器用空白状态启动，`SHOW USERS` 只剩 admin/root）。`docker cp` + `-v` 流程确保 certs + data 双持久化。

### 6.1 调用（schemaless 走 TLS fixture）

```bash
source .venv/bin/activate
docker start kaiwudb-smoke 2>&1 | head -1
curl -sk -o /dev/null -w "%{http_code}\n" https://127.0.0.1:8081/restapi/login -m 5
# 期望 200（接受无 token）或 401（缺 token），不能 connection refused。

rm -rf /tmp/jmeter-smoke/schemaless-out && mkdir -p /tmp/jmeter-smoke
python -m kwjdbc_svt.main \
    tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml \
    tests/kwjdbc_svt/fixtures/test_cfg_schemaless_tls.yaml \
    -o /tmp/jmeter-smoke/schemaless-out
```

KaiwuDB REST 端口默认 8081（容器内 HTTP 服务端口；TLS 模式 HTTPS 同端口，参考 `docs/refs/kaiwudb-schemaless-write-reference.md` §6.3）。

> **§6.1.0 数据库类型约束（2026-07-31 落定，**[**ref §2.0**](../../docs/refs/kaiwudb-schemaless-write-reference.md#20-数据库类型约束关键)）**：
>
> - **schemaless write 仅作用于时序表**；**KaiwuDB 拒绝在关系库里建时序表**。
> - 系统默认库 `defaultdb` / `postgres` / `system` 全是 `engine_type=RELATIONAL`，**不能**作为 schemaless 写入目标。
> - schemaless fixture `test_model_schemaless.yaml` 必须把 `ts_dbs[0].name` 改成时序库名（典型 `iot_monitor`），DDL-1 才会真正 `CREATE TS DATABASE`；DDL-2 才会真正 `CREATE TIMESERIES TABLE <tsdb>.meters`。
> - `test_cfg_schemaless_tls.yaml` 的 `rest_api_config.default_db` / `write_config[].tbl_name` / `query_config[].query` 必须全部对齐到同一个时序库名。
> - 当前 fixture 若三个字段仍是 `defaultdb`，smoke 必败 `pq: can not create timeseries table in relational database "defaultdb"`（DDL-2 拒，Query 缺表 → NumberFormatException 链）。
>
> **§6.1.1 时间戳精度约束（2026-09-09 落定）**：
>
> - **InfluxDB Line `<timestamp>` 字段单位是纳秒**（19 位整数，如 `1788859817368000000`），schemaless 生成器在 `_build_rest_write_preprocessor_script` 把 `baseTime + b*msStep` 乘以 `1000 * 1000` 拼到 line tail。
> - KaiwuDB **DDL `timestamp` 默认是 `TIMESTAMPTZ(3)`（ms 精度）**，19 位 ns 会被 server 拒：`pq: value "<ns>" out of range for type TIMESTAMPTZ(3)`（每条 Write 100% err）。
> - schemaless fixture `test_model_*.yaml` 必须把 `ts_col.type` 显式声明为 `timestamp(9)`（=`TIMESTAMPTZ(9)` ns 精度），DDL-2 才会 `CREATE ... k_timestamp TIMESTAMP(9) NOT NULL`，与 InfluxDB Line ns timestamp 匹配。`TsColConfig.type` Literal 已扩到 8 个：`timestamp` / `timestamptz` / `timestamp(3|6|9)` / `timestamptz(3|6|9)`。
> - 实测（curl）：ms 时间戳 `1788859817368` → `code:0, rows:1` ✓；ns 时间戳 `1788859817368000000` → `code:-1, out of range` ✗。
> - **JDBC 路径不受影响**：JDBC bind path 用 `PreparedStatement.setTimestamp()` 传 `Timestamp` 对象（java.sql 精度自适应），不涉及 line tail 数值。

### 6.2 跑 jmeter

```bash
cd /tmp/jmeter-smoke
timeout 60 jmeter -n -t /tmp/jmeter-smoke/schemaless-out/test_plan.jmx \
    -Jtest_duration=30 -Jnum_threads=2 -Jdevice_start=1 -Jdevice_per_thread=5 \
    -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
    -Jrest_api.hostname=127.0.0.1 \
    -Jrest_api.http_port=8081 \
    -Jrest_api.ca_cert_path=/abs/path/to/ca.crt \
    -j /tmp/jmeter-smoke/jmeter-schemaless.log 2>&1 | tail -10
```

> **`-Jrest_api.ca_cert_path` 必须为绝对路径**（容器内 `/kaiwudb/certs/ca.crt`
> 经 `docker cp` 到宿主机的位置，如 `tests/kwjdbc_svt/fixtures/ca.crt`）。JMX
> 用 `${__P(rest_api.ca_cert_path,)}` UDV 引用，不接受相对路径 —— JMeter 进程
> cwd 与 fixture 路径解析不在同一根。详见 §6.0.1 第 1 项。

### 6.3 断言（OpenSpec §6.5 (a)-(e)）

| 断言 | 验证手段 |
|------|----------|
| (a) SetupTG Login/DDL `code==0` | JTL 中 DDL Setup (REST) sample response code 字段 |
| (b) 写入 TG `code==0` + `rows >= 1` | JTL response body 解析 `{"code":0,"rows":N}` |
| (c) Query round-trip `rows >= 1` | 同 (b)，query TG sample |
| (d) DB `count(*) from meters` 匹配 | `docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs -e "select count(*) from defaultdb.meters"` |
| (e) `device_id` ptag 列非 NULL + 范围 `device_1..device_10` | `select distinct device_id from defaultdb.meters` |

> **⚠️ cfg-write-throughput-literal (2026-09-11)**：`-Jwrite_throughput=N` 已**失效**（`${write_throughput}` UDV 已移除）。如需调整 sampler 速率，改 cfg `write_config[].throughput` 后重生成 JMX。

### 6.4 调试 / 排错（TLS smoke 中增量补充）

> KaiwuDB TLS / cert 无官方调试文档（除 §6.0 引用 `kaiwudb-tls-cert-reference.md`
> 涵盖正常路径）。本节**逐次 TLS smoke 中遇到的具体错误 → 排查路径 →
> 修复**逐条记录，新发现追加到末尾，不覆盖。

- **格式约定**：每条记 `<症状> → <定位命令> → <根因> → <修复>`。

#### 6.4.1 Root user 无密码 → REST Login 200 + `can not find Basic attribute`

**症状**：smoke 一开始所有 HTTPSampler 看似连通（TCP 层），但 DDL Setup 的
JSON Extractor 抽 `$.token` 拿到空字符串 → 后续 DDL/Query/Write 的
`Authorization: Basic ${__property(rest_token)}` 解析为 `Basic ` →
服务端 200 OK 但 response body = `{"code":-1,"desc":"can not find Basic attribute, please check"}`。

**定位命令**：

```bash
# 1. 容器内 /restapi/login 不带任何 Authorization
docker exec kaiwudb-smoke curl -sk https://127.0.0.1:8081/restapi/login
# → {"code":-1,"desc":"can not find Basic attribute, please check"}

# 2. 容器内用 client cert 登录 kwbase sql 也无密码
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "show users"
# → root | CREATEROLE | {admin}     ← 没有 PASSWORD 字段

# 3. ALTER USER 后 SHOW USERS 仍然不显示 PASSWORD（PASSWORD 不被 SHOW USERS 输出）
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "ALTER USER root WITH PASSWORD 'root123'"
# kwbase sql -u root 不带 --password 仍能进（client cert 优先）→ 验证无效
# 真正的验证：REST /restapi/login
curl -sk -u root:root123 https://127.0.0.1:8081/restapi/login
# → {"code":0,"token":"..."}
```

**根因**：容器以 TLS 模式启动但未建非空密码 `root` 用户。REST API 鉴权层
要求非空密码，client cert 仅供节点 / JDBC 直连登录。`SHOW USERS` 不显示
PASSWORD 字段（与 `login-password` 一致时），无法用 SQL 自检密码是否设置。
参见 [docs/refs/kaiwudb-user-management-reference.md §1](../docs/refs/kaiwudb-user-management-reference.md#1-概述)。

**修复**：

```bash
# 必须 TLS 模式 + ALTER USER / CREATE USER PASSWORD（insecure 模式 SQLSTATE 28P01）
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "ALTER USER root WITH PASSWORD 'root123'"

# 验证：REST /restapi/login 必须返回 {"code":0,"token":"..."}
curl -sk -u root:root123 https://127.0.0.1:8081/restapi/login
```

JMeter 侧无需改动（fixture `test_cfg_schemaless_tls.yaml` 已是
`login_password: root123`）。重跑 smoke：DDL Login 200 OK，
`responseData` 包含 `"code":0,"token":"..."`。

#### 6.4.2 DDL-2 偶发回 `can not find Basic attribute`（DDL-1 正常）

**症状**：第二次及之后 smoke 跑，DDL Setup 阶段 DDL-1（create ts database）
返回 200 OK + 通过 assertion，但 DDL-2（create table）返回 200 OK +
assertion 失败，failureMessage = `DDL failed: {"code":-1,"desc":"can not find Basic attribute, please check"}`。
JMeter 日志同样报 `JSR223Assertion: Problem in JSR223 script: DDL-2_assert`。

但 curl 单独跑 `Authorization: Basic $TOKEN` POST DDL 时返回 `{"code":0,...}` —— 服务端鉴权逻辑正确。

**定位命令**：

```bash
# 1. JTL 字段对齐（CSV reader 解析 responseData）
python3 -c "
import csv
with open('/tmp/jmeter-schemaless3.jtl') as f:
    r = csv.reader(f)
    h = next(r)
    for row in r:
        d = dict(zip(h, row))
        if d['label'] in ('DDL Login','DDL-1','DDL-2'):
            print(d['label'], d['URL'], d['success'], d.get('failureMessage','')[:120])
"
# → DDL Login https://127.0.0.1:8081/restapi/login  True  ''
#   DDL-1     https://127.0.0.1:8081/restapi/ddl     True  ''
#   DDL-2     https://127.0.0.1:8081/restapi/ddl     False 'DDL failed: {"code":-1,"desc":"can not find Basic attribute, please check"}'

# 2. 确认 DDL-2 的实际 HTTP 请求 URL/Method 是对的
# 3. 观察 DDL-2 实际发出去的 Authorization header：
#    在 HTTPSamplerProxy 旁加一个 JSR223PreProcessor 打印 ${__property(rest_token)}
#    输出会发现 DDL-2 取到的 property 是空字符串
```

**根因**：JSR223PostProcessor 设置 `rest_token` property 用 `props.put("rest_token", vars.get("token"))`。
JMeter 中 `props.put(K, null)` 会清空 property（不是设置成空字符串）。
若 `vars.get("token")` 因为任何原因（JSON Extractor 竞态、PostProcessor
执行顺序、definition_holder 生命周期）返回 null，则 DDL-1 拿到的是 setup
线程组**上一轮的残留值**（第一次跑为定义默认值，恢复为 `Basic `），
DDL-2 拿到 set 之后的 null/空字符串。
服务端 `Basic ` 不识别 → 200 + Login 协议层的 `can not find Basic attribute` 错误 body。
参见 [docs/refs/kaiwudb-kwbase-sql-reference.md §4.1](../docs/refs/kaiwudb-kwbase-sql-reference.md#4-典型用法)
（连接 / 鉴权层 — 与本 bug 间接相关）。

**修复（workaround，推荐）**：在 JSR223PostProcessor 脚本中**先判 null
再赋值**，并把 `__property(rest_token)` 改成 `__property(rest_token,)`+
**JSR223 同步写**：

```groovy
// src/jmx_skeleton_generator/generators/ddl_setup.py:367
// 原文：setprop_script = 'props.put("rest_token", vars.get("token"))\nreturn'
setprop_script = (
    'def t = vars.get("token") as String\n'
    'if (t != null && t.length() > 0) { props.put("rest_token", t) }\n'
    'return'
)
```

试改后 DDL-1 / DDL-2 的 Authorization header 在连续两次 smoke 间稳定。

**根因（深层）**：`props.put(K, null)` 在 JMeter 5.6.3 行为是把 key 绑定
成 null，后续 `__property(K)` 解析为字符串 `null`（Groovy `String.valueOf(null)`）
不是空串。DDL-2 之前实测取到 `Basic null`（确认未截断），HTTP 头非法
但服务端将其识别为缺 Basic 头。**该 bug 当前在生成器侧仅靠上述
workaround 规避，待生成器层调研 `props.setProperty` / `JMeterProperty` 直接
API 后根治**。

#### 6.4.3 Query round-trip 失败 — 表不存在导致 `NumberFormatException`

**症状**：REST_Query_meters sample 200 OK 但 assertion 失败：
`NumberFormatException: For input string: ""`。
KaiwuDB 校验：表 `defaultdb.meters` 不存在。

**定位命令**：

```bash
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "show tables from defaultdb;"
# → ERROR: relation "defaultdb.meters" does not exist
```

**根因**：DDL-2 已失败（§6.4.2），表未建。Query 命中不存在的表 → 服务端
返回 200 + 空 body → assertion 解析 `Integer.parseInt("")` 抛
`NumberFormatException`。

**修复**：先解决 §6.4.2 DDL-2 失败；表建好后 Query 自动恢复。无独立补丁。

#### 6.4.4 端口 8080 vs 8081：`-Jrest_api.http_port=8081` 是否生效

**症状**：smoke 早期一次跑 JTL 行 2-3 报 `Connect to 127.0.0.1:8080 [/127.0.0.1] failed: 连接被拒绝` —— 端口用了 JMX 默认 8080 而非用户传入 8081。

**定位命令**：

```bash
# 1. JMeter 日志确认 property 已 set
grep "Setting JMeter property" /tmp/jmeter-schemaless.log
# → rest_api.http_port=8081
# → rest_api.ca_cert_path=/abs/path/ca.crt
# → rest_api.hostname=127.0.0.1

# 2. JMX 确认 sampler 用的是 ${__P(rest_api.http_port,8080)}
grep "HTTPSampler.port" /tmp/jmeter-schemaless-out/test_plan.jmx
# → 全部 ${__P(rest_api.http_port,8080)}
```

**根因**：首次失败发生在改 fixture 编号尚未同步的旧 JMX（§6.1 旧一次跑
覆盖）。后续 run 用新生成的 JMX，property 解析为 8081。
**没有真实 bug** —— 复测时已恢复。容器端口映射 `-p 8081:8080`（host 8081 → container 8080），
所有 `127.0.0.1:8080` 拒绝连接是 host 端口 8080 没东西在听，不是 KaiwuDB 错。

**修复 / 预防**：

- 容器启动用 `-p 8081:8080`（参考 §6.0 step 2），host 端用 8081
- sampler 自动从 `-Jrest_api.http_port=8081` 解析
- 误以为需要改 JMX hardcoded 端口 8080 —— 实际不改，UDV 链路已生效

#### 6.4.5 Write sampler 发空 body → server `invalid request body`

**症状**：smoke v15（§6.4.2 B1 落地后）跑出 30 write samples，20 失败
`{"code":-1,"desc":"invalid request body"}`；DB count 远小于 JMeter
write sample 数。SetupTG / Query 全 pass，仅 Write TG 假失败。

**定位命令**：

```bash
# 1. 看 JTL 的 Write TG failureMessage（应用 B1 后才能看到 server 真正响应）
awk -F',' 'NR>1 && $3=="REST_Write_meters" && $8=="false" {print substr($9,1,120)}' /tmp/jmeter-*.jtl
# → javax.script.ScriptException: java.lang.RuntimeException: Write failed: {"code":-1,"desc":"invalid request body"}

# 2. 看 JMeter log 找 prep 报错
grep "REST_Write_meters_prep" /tmp/jmeter-*.log | grep -i "warn\|empty\|rows"
# → REST_Write_meters_prep: rows empty (rowsKey=...), iteration skipped
#   （rows 10 行耗尽后 prep 进入 rows-empty 分支）

# 3. curl 复现：空 body POST /restapi/influxdb?db=iot_monitor
# → HTTP 200 body {"code":-1,"desc":"invalid request body"}
```

**根因**：

smoke 设计：SharedMemory SetupTG 一次性加载 seed CSV 到 JMeter global
property（典型 10 行）；Write TG 的 JSR223PreProcessor 每迭代从该 list
`rows.remove(0)` 取一行。`rows.remove(0)` 不循环 — 耗尽后 list 为空。

prep script 处理 rows 空时的代码：

```groovy
if (rows == null || rows.isEmpty() || columns == null) {
    ctx.setStopThread(true)   // <-- BUG: JMeter 5.6.3 Groovy 不存在
    return
}
```

`ctx.setStopThread(boolean)` 在 JMeter 5.6.3 Groovy 上下文抛
`MissingMethodException: No signature of method:
org.apache.jmeter.threads.JMeterContext.setStopThread() is applicable for
argument types: (Boolean) values: [true]`。

抛错后 JSR223PreProcessor 提前返回（异常被 JSR223 吞），但
`vars.put('request_body', line)` 未执行 → JMeterVariables 中
`request_body` 为空 → sampler 仍执行，发**空 body** POST →
server 返 HTTP 200 + `code:-1 invalid request body` → B1 assertion
（§6.4.2 锁 J）正确捕获 → JTL `success=false` → DB 无新行。

**真因不在 assertion（B1 是正确的检测器），在 prep rows-empty 兜底
逻辑用错了不存在的 API**。

**修复（§6.4.2 锁 K，2026-07-31）**：

```groovy
if (rows == null || rows.isEmpty() || columns == null) {
    log.warn('REST_Write_meters_prep: rows empty (rowsKey=' + rowsKey + '), stopping thread')
    ctx.stopThread()    // <-- JMeter 5.6.3 提供，无参版本
    return
}
```

`JMeterContext.stopThread()`（无参）存在；`JMeterContext.setStopThread(boolean)`
只在某些版本存在，JMeter 5.6.3 Groovy 上下文缺。验证：smoke v17 干净态
（drop iot_monitor + meters 后）§6.3 (a)-(e) 全绿：
- (a) SetupTG 3/3 success
- (b) Write 10/10 success（rows 10 行耗尽后 `ctx.stopThread()` 触发 thread
  退出，**不再发空 body**）
- (c) Query 1/1 success
- (d) DB `count(*) from iot_monitor.meters` = 10
- (e) ptag `device_1+device_2` 各 5 行（device_per_thread=2 全覆盖）

**反例 / 防退化**：

- `ctx.setStopThread(boolean)` 任何参数版 — 5.6.3 Groovy 必抛
  `MissingMethodException`
- `SampleResult.setIgnore()` — PreProcessor 中 SampleResult 未绑定
  （`MissingPropertyException: No such property: SampleResult`）
- 仅 `log.warn` 不停 thread — sampler 会发空 body 触发 20+ fake failure
  （B1 正确捕获但其实是 prep bug）

**相关 commit**：`fee6986`（§6.4.2 主线，含 duration 1s→test_duration +
null/empty token guard + defaultdb→iot_monitor + SharedMemory 加回）、
`a6d079a`（B1 锁 J + B5 锁 K stopThread）。

#### 6.4.6 `kwbase sql` 卡在 `Enter password: ERROR: inappropriate ioctl for device` — 缺 client.root cert

**症状**：执行 §6.0 step 5/6 的 `docker exec kaiwudb-smoke kwbase sql --certs-dir=/kaiwudb/certs -e "select 1"` 输出：

```
Enter password: ERROR: inappropriate ioctl for device
Failed running "sql"
```

进程退出码非 0，step 5 轮询 30s 后仍不 ready。

**定位命令**：

```bash
# 1. 容器内 certs 目录是否有 client.root.crt/key
docker exec kaiwudb-smoke ls -la /kaiwudb/certs/
# 预期正常：ca.crt/ca.key + node.crt/node.key + client.root.crt/client.root.key
# 缺 client.*  → §6.0 step 3 漏跑

# 2. 容器内 kwbase 是否监听 26257
docker exec kaiwudb-smoke bash -c "cat /proc/net/tcp | awk 'NR>1 {print \$2}' | sort -u"
# 0000:0000:A339 / 0000:0000:1F90  → 26257 / 8080 都 LISTENING → kwbase 已 ready
# 仅 8080 而无 26257 → kwbase 还没启动或绑错地址

# 3. 用 curl 直接探 REST 端口
curl -sk -o /dev/null -w "%{http_code}\n" https://127.0.0.1:8081/ -m 5
# → 200/404/401 → kwbase 已就绪，问题仅在 kwbase sql 客户端认证
```

**根因**：KaiwuDB TLS 模式下 `kwbase sql` 必须有客户端证书才能认证 root 用户。
CLI 在没有可用 client cert、root 用户又无密码时会进入交互式密码读取——
`docker exec` 不分配 tty，导致 `inappropriate ioctl for device` 错误。
**§6.0 step 3 必须显式跑 `kwbase cert create-client root`** 生成
`client.root.crt` / `client.root.key`，CLI 才会自动用它做 mTLS 认证。

旧版 SKILL §6.0 step 3 注释里写"客户端 cert —— REST 客户端 ca.crt 足够"是
误导（ca.crt 仅做 server 验证，client 侧认证仍需 client.*）。

**修复**：

```bash
# 1. 补 client.root cert
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase cert create-client root \
    --certs-dir=/kaiwudb/certs \
    --ca-key=/kaiwudb/certs/ca.key

# 2. 验证免密登录
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --certs-dir=/kaiwudb/certs \
    -e "select 1"
# → ?column?
#   1

# 3. 然后继续 §6.0 step 6 建 root 密码 + §6.0.2 建其他用户
```

`SHOW USERS` 不显示 PASSWORD 字段（参见 §6.4.1 / §6.0.2 第 2 步）——
非 root 用户的密码是否生效必须用 §6.0.2 第 3 步的 `--url` 实连验证，
或在 fixture 里替换 `db_username`/`db_password` 后跑 §6.3 断言。

**防退化**：

- §6.0 step 3 的命令注释写"客户端 cert —— REST 客户端 ca.crt 足够" 已替换为
  明确生成 client.root cert 的命令，CI 重跑不应再触发此症状。
- 若后续 kwbase 升级或换镜像，client cert 仍**必须**与 server 共用同一 CA
  才能 mTLS 成功 —— 重建容器（§6.0.1 隔离陷阱）后必须重跑全套 §6.0 step 1-7。

## 7. pub_sub smoke（insecure 容器, 端到端 DCR）

> OpenSpec change `pub-sub-end-to-end` (§3-§5 落地后): pub-sub 端到端 smoke
> 验证 (SetupTG 注入 create publication / create subscription + Verify
> TG 注入 show subscription status + count(*) 断言).
>
> **关键差异** (vs §6 schemaless):
> - **不需要 TLS 容器** — pub_sub 走 `?sslmode=disable` insecure 容器即可
>   (per proposal.md 备注; pub_sub_config.conninfo 字段是字面值, 不像
>   db_url 那样被 `-J` 覆盖, 所以 conninfo 需要自己保证 insecure)
> - **不依赖** REST API / client cert / user creation (per §6.0 step 6-7)
> - 复用现有 insecure 容器即可 (§3 步骤 1-5 起容器 → 跑 smoke)

### 7.0 容器前置

- **不**需要重建容器 — §3 步骤 1-5 起的 insecure 容器直接可用
- 确认容器内 `db_url` UDV 默认值指向 `defaultdb`:
  ```bash
  # 容器内 kaiwudb 进程 listen on 26257, defaultdb 是 SQL 默认入口
  grep db_url /data/jmeter-*/test_plan.jmx | head -1
  # 期望: <stringProp name="db_url">jdbc:kaiwudb://127.0.0.1:26257/defaultdb</stringProp>
  ```
- 确认 insecure (no TLS) — kwbase insecure 启动已满足, no `sslmode=require`

### 7.1 调用: 两次端到端 invocation templates

**(a) 整库模式 + 默认阈值** (`test_cfg_pub_sub.yaml`):
```bash
# 容器内 (KaiwuDB listen on 127.0.0.1:26257)
python -m kwjdbc_svt.main -o /data/jmeter-int \
    /data/fixtures/test_model.yaml \
    /data/fixtures/test_cfg_pub_sub.yaml
jmeter -n -t /data/jmeter-int/test_plan.jmx \
    -J db_url="jdbc:kaiwudb://127.0.0.1:26257/defaultdb" \
    -J test_duration=30 \
    -l /data/jmeter-int/result.csv \
    -e -o /data/jmeter-int/report
```

**(b) 表级 + 列子集 + WHERE + `expected_min_rows=0` 恒真**
(`test_cfg_pub_sub_tables.yaml`):
```bash
python -m kwjdbc_svt.main -o /data/jmeter-int-tables \
    /data/fixtures/test_model.yaml \
    /data/fixtures/test_cfg_pub_sub_tables.yaml
jmeter -n -t /data/jmeter-int-tables/test_plan.jmx \
    -J db_url="jdbc:kaiwudb://127.0.0.1:26257/defaultdb" \
    -J test_duration=30 \
    -l /data/jmeter-int-tables/result.csv \
    -e -o /data/jmeter-int-tables/report
```

### 7.2 断言 checklist (匹配 SetupTG / Write TG / Verify TG lifecycle)

| 阶段 | 断言 | 通过条件 |
|---|---|---|
| SetupTG (含 pub_sub 注入的 3 个 sampler) | SetupTG 全部 sampler `code==0` | jtl 中 `s:assertionResult` 全空 |
| Write TG (主线程写 iot_monitor.t_cnc) | Write TG JTL 100% 成功 (无 error) | jtl 中 `s:success=true` 100% |
| Verify TG PostThreadGroup (60s delay 后) | SHOW SUBSCRIPTION status 含 `running` | jtl 中 JSR223Assertion script 输出 `"subscription not running"` 不出现 |
| Verify TG (per-table count sampler) | `count(*) >= expected_min_rows` | jtl 中 JSR223Assertion script 输出 `"below threshold"` 不出现 |
| **特殊**: publication 用 WHERE 过滤 | `expected_min_rows` 必须设 `0` (走恒真) | 否则 count(*) 可能为 0 → Verify TG fail (设计警告, per design.md D3 段) |

**注意**:
- `test_cfg_pub_sub.yaml` 走**默认** 1 阈值;`test_cfg_pub_sub_tables.yaml` 走**显式 0 阈值** (恒真)
- 两份 fixture 都必须跑通, 不能只跑一份

### 7.3 Troubleshooting

- **`<publisher_db>_sub` 已存在 from prior run**:
  - 症状: `create ts database if not exists iot_monitor_sub` 报"already exists" 或
    主线程 Insert 报"duplicate"
  - 修: 让流水线侧 DROP DATABASE (per §7.4 cleanup 责任), 或调
    `ddl_statements` 让 `create ts database` 走 `if not exists`(per §3.5 设计)
- **conninfo sslmode mismatch**:
  - 症状: `CREATE SUBSCRIPTION` 报 `SSL not enabled` 或 `SSL required`
  - 修: 检查 fixture `pub_sub_config.conninfo` 是否含 `?sslmode=disable` (insecure
    容器必须);pipeline `-J` 覆盖 `db_url` 时**不**覆盖 `conninfo` (per F-016
    锁定, conninfo 是字面)
- **`count(*)=0` likely causes**:
  - 症状: Verify TG 报 `"row count 0 below threshold 1"`
  - 修: (1) 检查主 TG 是否真写了数据 (jtl 中 Write TG success count); (2) 检查
    subscription 同步延迟 (per design.md F-010: 60s delay 覆盖
    `2-5s 连接建立 + ~10s 数据同步延迟 + 2s CDC 周期 + 多次同步周期累计`);
    (3) 考虑用 WHERE 过滤 fixture 时设 `expected_min_rows=0` 走恒真
- **WHERE clause rejected by server at CREATE PUBLICATION execution time**:
  - 症状: SetupTG 报 `syntax error at or near "where"` (KaiwuDB 不支持
    多表 WHERE / 部分列子集 WHERE 等)
  - 修: (1) 确认 fixture `tables` 是单表 + 单表 WHERE 合法; (2) Pydantic
    校验已阻止多表 columns/where (per §1), 但 WHERE 语法不 parse
    (per design.md line 50 + §6.3 段)
- **SHOW SUBSCRIPTION status 不含 `running`**:
  - 症状: Verify TG 第一条 sampler (SHOW SUBSCRIPTION) 的
    JSR223Assertion 报 `"subscription not running, status=<status>"`
  - 修: 查 subscription 真实 status (SHOW SUBSCRIPTION 走 defaultdb
    连接, per D5 per-cluster); 常见 cause: subscription enable='off',
    conninfo 鉴权失败, subscription 还没连上 publisher

### 7.4 Database cleanup (operator-side 责任)

> **重要**: generator **不**生成 tearDown DROP DDL, 数据库清理由**流水线
> 侧**负责. 这是 design.md Context 锁定 ("DROP 操作稳定性属功能测试
> 范畴; 测试计划仅在流水线内集成, 数据库清理由流水线侧负责").

#### 7.4.1 重跑前必须清理之前的状态 (insecure 容器复用场景)

> **关键**: insecure 容器 (per §7.0) 没有 TLS, **不**支持自动重置状态; **同一
> 容器**反复跑 pub_sub smoke **之前**, 必须**手动**先 DROP 之前创建的
> `iot_monitor` / `iot_monitor_sub` db + publication + subscription + 内部
> 表, 否则下一轮 SetupTG 会因 `create ts database if not exists iot_monitor`
> (已存在) 或 `create publication` (已存在) 失败。

按下面 §7.4.2 顺序 DROP 之前的状态, 再跑下一轮 smoke。

#### 7.4.2 推荐 operator-side cleanup 顺序 (per §0 scope 锁定)

```sql
-- 1. drop subscription (先停 CDC 拉取)
DROP SUBSCRIPTION sub_iot;
DROP SUBSCRIPTION sub_iot_tables;  -- 第二份 fixture 的 subscription

-- 2. drop publication (停 publisher 端 CDC 输出)
DROP PUBLICATION pub_iot;
DROP PUBLICATION pub_iot_tables;    -- 第二份 fixture 的 publication

-- 3. drop subscriber db (清理 subscriber 端表 + db)
DROP DATABASE iot_monitor_sub;

-- 4. drop publisher db (清理 publisher 端表 + db)
DROP DATABASE iot_monitor;
```

**注意**: 上述 `DROP SUBSCRIPTION` / `DROP PUBLICATION` 文档未明确支持 `IF EXISTS`,
按 design.md Context 锁定, generator **不**生成 IF EXISTS 幂等 DROP, 流水线
直接调 DROP(失败时手动介入)。

## 交叉引用

- `tests/kwjdbc_svt/test_main.py::TestEndToEnd` — 程序内等价 smoke，快迭代
- `openspec/changes/main-entry/{design,tasks,review}.md` — review §1/§3 是
  本 skill 验证的边界条件清单
- `docs/refs/kaiwudb-kwbase-sql-reference.md` — `kwbase sql` 命令全参数、连接
  参数（`--certs-dir` / `--insecure` / `--url`）、输出格式速查；§4 / §6.0 step 5-6
  的 `kwbase sql` 调用均以此为准
- `docs/refs/kaiwudb-user-management-reference.md` — `CREATE/ALTER/DROP USER`
  + `SHOW USERS` 语法与权限模型；§6.0 step 6 建非空密码 root 与 §5.2 部署后
  标准化建用户流程均引用此文
- `docs/refs/kaiwudb-tls-cert-reference.md` — TLS 证书体系 + `kwbase cert`
  子命令；§6.0 / §6.0.1 容器 TLS 重建以此为准
- `docs/refs/kaiwudb-schemaless-write-reference.md` — schemaless REST 协议
  参考；§6.1-§6.3 断言列的协议细节引用此文 §6.3
