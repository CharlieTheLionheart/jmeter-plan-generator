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
    -Jwrite_throughput=60 \
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
for i in $(seq 1 30); do
    docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --insecure -e "select 1" >/dev/null 2>&1 && break
    sleep 1
done

"$JMETER" -n -t /tmp/jmeter-smoke/out/test_plan.jmx \
    -Jtest_duration=5 -Jnum_threads=1 \
    -Jdb_url=jdbc:kaiwudb://localhost:26257/defaultdb \
    -Jdb_username=root \
    -Jwrite_throughput=120 \
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

## 交叉引用

- `tests/kwjdbc_svt/test_main.py::TestEndToEnd` — 程序内等价 smoke，快迭代
- `openspec/changes/main-entry/{design,tasks,review}.md` — review §1/§3 是
  本 skill 验证的边界条件清单
