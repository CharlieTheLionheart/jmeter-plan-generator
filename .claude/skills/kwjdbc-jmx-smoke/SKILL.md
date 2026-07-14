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
| （可选）KaiwuDB 端点 | `-Jdb_url=jdbc:kaiwudb://<host>:<port>/<db>` |

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

**真 bug（必须修）**：

| log 模式 | 真 bug | 修法 |
| --- | --- | --- |
| `NumberFormatException: For input string: "${conn_pool_size}"` | JDBCDataSourceElement.initPool 在 UDV 函数评估**之前** parseInt poolMax | `pool_max = str(int(conn_pool_size))` 在 `jdbc_data_source_generator.py` |
| `unable to resolve class CSVReader` | shared_memory_initializer Groovy 用 OpenCSV，JMeter lib/ext 无 opencsv.jar | 用 Groovy `line.split(',')` 替 `new CSVReader(...)` |
| 其他 `unable to resolve class X` | Groovy 引用 JMeter classpath 没有的类 | 改 Groovy 用 JDK 内置类 |
| SyntaxError / MultipleCompilation from JSR223 | Groovy 表达式编译失败 | 看 script literal，查不对称大括号/引号转义 |
| `Cannot resolve external entity` from XML parser | .jmx 引用 `${...}` 在 parse 之前被 resolve | 改 `${__P(...)}` 形式或字面 |

无 DB 模式下唯一**可接受**错误：`ConnectException: Connection refused`
从 `kaiwudb.Driver.connect`（或等价 SocketException）— 表示测试计划走
过所有 setup 阶段，只在 JDBC driver 层失败。

### 4. （可选）连真 KaiwuDB 跑全链路

```bash
docker run -d --name kaiwudb-smoke -p 26257:26257 kaiwudb/kaiwudb:3.2.0 \
    --cluster-name=test-single

"$JMETER" -n -t /tmp/jmeter-smoke/out/test_plan.jmx \
    -Jtest_duration=5 -Jnum_threads=1 \
    -Jdb_url=jdbc:kaiwudb://localhost:26257/test \
    -Jdb_username=root \
    -Jwrite_throughput=120 \
    -j /tmp/jmeter-smoke/jmeter-live.log 2>&1 | tail -10
```

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
- 真 bug 数:        N
- 结论:             全绿 / 具体回归
```

非全绿时列出每个失败阶段 + 生成器 file:line + 最小修复草图。

## 已知真 bug fixtures（要 catch 的回归）

2026-07-13 smoke 会话抓到的真 bug；任一重新出现 = 回归：

1. `NumberFormatException: For input string: "${conn_pool_size}"`
   位置：`src/jdbc_datasource/jdbc_data_source_generator.py:84`
2. `unable to resolve class CSVReader`
   位置：`src/shared_memory_initializer/shared_memory_initializer.py:118`

回归时查 `git log -p c1b50f7` 看修复。

## 交叉引用

- `tests/kwjdbc_svt/test_main.py::TestEndToEnd` — 程序内等价 smoke，快迭代
- `openspec/changes/main-entry/{design,tasks,review}.md` — review §1/§3 是
  本 skill 验证的边界条件清单
