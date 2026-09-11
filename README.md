# kwjdbc-svt: KaiwuDB SVT 测试计划生成器

通用 JMeter 测试计划生成器。`test_model.yaml` 定义数据库 schema（关系库 + 时序库），`test_cfg.yaml` 定义写入/查询配置，CLI 产出标准 `.jmx` + 列种子缓存文件，丢进 JMeter 5.6+ 跑就能对 KaiwuDB 端到端压测。

**规格：** [`docs/specs/kwdb-svt-test-plan-generator-spec.md`](docs/specs/kwdb-svt-test-plan-generator-spec.md)

---

## 1. 安装

```bash
# 依赖：Python 3.12+, JMeter 5.6+
git clone <repo>
cd quality-test-pipelines/kwjdbc-svt
python3.12 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"   # 含 pytest + rstr + hypothesis
```

**JMeter 准备**（一次性）：
- 下载 [Apache JMeter 5.6+](https://jmeter.apache.org/download_jmeter.cgi)
- 把 KaiwuDB JDBC 驱动（`kaiwudb-jdbc-*.jar`）丢到 `$JMETER_HOME/lib/ext/`
- 验证：`jmeter --version` 输出版本号

**KaiwuDB 端点**（可选项 1，跑 smoke 必须）：
- 启动容器（推荐 nightly，规避 F-17）：
  ```bash
  docker rm -f kaiwudb-smoke
  docker run -d --name kaiwudb-smoke -p 26257:26257 -p 8081:8080 \
      --ulimit nofile=65536 \
      devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest \
      /kaiwudb/bin/kwbase start-single-node \
      --insecure --listen-addr=0.0.0.0:26257 --http-addr=0.0.0.0:8080
  # 容器内 kwbase 绝对路径为 /kaiwudb/bin/kwbase (workdir 是 /，不在 $PATH)
  for i in $(seq 1 30); do
      docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql --insecure -e "select 1" >/dev/null 2>&1 && break
      sleep 1
  done
  ```
- 旧镜像 `kwdb/kwdb:latest` 与 `kwdb-x86_64-master-dbg` 仍含 F-17 bug — 详见 [docs/issues/F17.md](docs/issues/F17.md)

---

## 2. 快速开始

```bash
# 1. 跑通单测（633 passed）
source venv/bin/activate
python -m pytest tests/        # ~30s

# 2. 用最小 fixture 生成 JMX
python -m kwjdbc_svt.main \
    tests/kwjdbc_svt/fixtures/test_model.yaml \
    tests/kwjdbc_svt/fixtures/test_cfg.yaml \
    -o /tmp/jmeter-out
# 产出：/tmp/jmeter-out/test_plan.jmx + /tmp/jmeter-out/seeds/{db}/{table}/

# 3. 用 shig fixture 跑（带 FK 关系 + 多 rtag）
python -m kwjdbc_svt.main \
    tests/kwjdbc_svt/fixtures/test_model_shig.yaml \
    tests/kwjdbc_svt/fixtures/test_cfg_shig.yaml \
    -o /tmp/jmeter-shig
```

---

## 3. CLI

```bash
python -m kwjdbc_svt.main <test_model.yaml> <test_cfg.yaml> [-o OUTPUT_DIR] [-v|-vv]
```

| 参数 | 说明 |
| --- | --- |
| `test_model` (positional) | 数据库 schema 定义，必填 |
| `test_cfg` (positional) | 写入/查询配置，必填 |
| `-o, --output-dir` | 输出目录（默认 cwd） |
| `-v` / `-vv` | WARNING→INFO→DEBUG |

**退出码**：

| code | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 通用未捕获异常 |
| 2 | `ConfigParserError`（fixture yaml schema 不匹配） |
| 3 | `SeedGenError`（seed 生成 schema 不匹配） |
| 4 | `DdlGenerationError`（DDL 生成失败） |
| 5 | `JmxGenerationError`（JMX 生成失败） |
| 6 | 依赖错误（`requires_prepared_insert_templates`） |

---

## 4. 配置文件 schema

### 4.1 `test_model.yaml` — 数据库 schema

完整字段参考 [`docs/specs/kwdb-svt-test-plan-generator-spec.md` §2.0](docs/specs/kwdb-svt-test-plan-generator-spec.md#20-配置字段定义)。最小示例：

```yaml
rel_dbs:
  - name: iot_metadata
    if_not_exists: true
    with_encoding: utf-8
    tables:
      - name: t_workshop
        primary_key_count: 1
        data_col_count: 2
        primary_keys:
          - col_type: int8
            type_proportion: 1.0
            val_range: ">=1"
            seed_num: 5
        data_cols:
          - col_type: varchar(16)
            type_proportion: 0.5
            val_range: "^[A-Za-z0-9]{2,10}$"
            seed_num: 5
ts_dbs:
  - name: iot_monitor
    if_not_exists: true
    retentions: 3d
    partition_interval: 1d
    tables:
      - name: t_cnc
        with_hash: 4
        ts_col: {name: ts, type: timestamp, ms_step: 1000}
        primary_tag_count: 2
        regular_tag_count: 2
        data_col_count: 4000
        primary_tags:
          - {col_type: float8, type_proportion: 0.5, val_range: ">=1", seed_num: 10}
          - {col_type: int8,  type_proportion: 0.5, val_range: "ref:iot_metadata.t_workshop.pk_int8_1", seed_num: 5}
        regular_tags:
          - {col_type: varchar(10), type_proportion: 1.0, val_range: "^[A-Za-z0-9]{2,10}$", seed_num: 2}
        data_cols: [...]
```

**`val_range` 语法**：

| 形式 | 含义 | 示例 |
| --- | --- | --- |
| 区间 | 数值范围（含端点 `[]`、不含 `( )`） | `[0, 100)`、`(1.5, 2.5]` |
| 比较 | `<` / `<=` / `>` / `>=` / `=` | `>=1`、`=42` |
| enum | 顺序循环选取 | `enum:M1,M2,M3` |
| regex | 正则（`[]一-鿿a-zA-Z0-9-_`） | `^[A-Z][0-9]{3}$` |
| ref | 外键引用：`ref:库名.表名.列名` | `ref:iot_metadata.t_workshop.pk_int8_1` |

**`ref:`** 自动生成 DDL 约束 `REFERENCES db.table(col)`（关系库）并让生成器从被引用表的主键种子中采样取值。跨时序库/关系库引用可正常工作。

### 4.2 `test_cfg.yaml` — 压测配置

```yaml
conn_config:
  db_url: jdbc:kaiwudb://localhost:26257/defaultdb   # 必须 defaultdb，业务库未建
  db_username: root
  db_password: ""
  conn_pool_size: 4
  device_start: 1                                  # 多端协同基准
  test_duration: 30                                # ThreadGroup.duration (秒)
write_config:                                      # 每张表一条，可分表独立配置
  - tbl_name: iot_monitor.t_cnc
    throughput: 60.0                                # 每写入线程目标吞吐（次/分钟）
    mode: batch_prepared                            # single_insert/batch_insert/single_prepared/batch_prepared
    batch_lines: 5                                  # 每次 batch 行数
    device_per_thread: 2                            # 每线程负责设备数
    num_threads: 4                                  # 写入线程数
query_config:                                      # 每查询一条
  - query: "select last(col_float4_1) from iot_monitor.t_cnc where iot_monitor.t_cnc.ptag_varchar_1=?"
    throughput: 4.0                                # 每查询线程目标吞吐（次/分钟）
    num_threads: 2
  - query: "select count(1) from iot_monitor.t_cnc where rtag_varchar_1=? group by rtag_varchar_1"
    throughput: 2.0
    num_threads: 1
```

**吞吐语义**（2026-07-22 修正）：
- `ConstantThroughputTimer` 配 `calcMode=0`（This thread only）
- `throughput` 值直接作为每线程目标，**不**除以 `num_threads`
- 线程组总吞吐 = `throughput × num_threads`；集群总 = `throughput × num_threads × 端数`

**多表 `num_threads` 约束**：当前版本 `write_config` 分条目配置多表时各表 `num_threads` 必须相同（避免 JMeter 全局同名 UDV 冲突），详见 spec §1.6 修订历史。

---

## 5. 跑 JMeter

```bash
# 必须连 defaultdb（建库前系统库永远在）；setup 阶段会 CREATE DATABASE IF NOT EXISTS
cd /tmp/jmeter-shig
jmeter -n -t test_plan.jmx \
    -Jtest_duration=30 -Jnum_threads=4 \
    -Jdevice_start=1 -Jdevice_per_thread=2 \
    -Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb \
    -l /tmp/r.jtl -j /tmp/jmeter.log

# 出 HTML 报告
jmeter -g /tmp/r.jtl -o /tmp/jmeter-report
open /tmp/jmeter-report/index.html
```

**通过 `-J` 覆盖的 UDV**（spec §2.0）：

| UDV | 默认 | 说明 |
| --- | --- | --- |
| `test_duration` | 30 | ThreadGroup.duration (s) |
| `num_threads` | 4 | 写入/查询线程数 |
| `device_start` | 1 | 多端协同设备号基准 |
| `device_per_thread` | 1 | 每线程设备数 |
| `conn_pool_size` | 4 | 连接池大小 |
| `db_url` | - | JDBC URL（必须 `defaultdb`） |
| `db_username` | root | DB 用户名 |
| `db_password` | "" | DB 密码 |

> **写入线程组吞吐量**：自 2026-09-11 cfg-write-throughput-literal 起，写入 `ConstantThroughputTimer.throughput` 直接烤死 cfg `write_config[].throughput` 字面数值（samples/min/thread）。**没有** `-Jwrite_throughput=N` 入口 — 修改 cfg 后重生成 JMX 即生效。

---

## 6. 端到端 smoke 测试

`.claude/skills/kwjdbc-jmx-smoke/SKILL.md` 提供了 1.5h smoke 流程，包括：

- 容器启动 / 健康检查
- JMX 生成（无 DB 模式 + 连真 DB 模式）
- 常见 JMX 加载错误排查
- 容器镜像约定（workdir / kwbase 绝对路径 / F-17 镜像选择）

触发词：`smoke` / `jmeter -n` / `端到端测试` / `JMX smoke` / `跑 jmeter` / `verify .jmx`

最近一次 1.5h smoke（2026-07-22 11:10 → 12:40）：

| 类别 | 实际 | 配置 | 偏差 |
| --- | --- | --- | --- |
| t_cnc 写入 (4 thread × 120/min) | 479.87/min | 480/min | -0.03% |
| t_electmeter 写入 | 479.87/min | 480/min | -0.03% |
| 12 个查询 (0.017 ~ 4/min) | 12.14/min 总和 | 12.12/min 总和 | ±0.0% |
| 总样本 87,433 | 0 err | - | - |

报告：`/tmp/jmeter-report-90min/index.html`（HTML Dashboard），原始 JTL `/tmp/r-90min.jtl`（87,434 行，9.2 MB）

---

## 7. 项目结构

```
src/
├── kwjdbc_svt/              # CLI 入口（main.py）
├── config_parser/           # YAML → Pydantic 模型
├── column_namer/            # 列名生成 (col_int8_1 / ptag_varchar_1 / rtag_int4_5)
├── ddl_generator/           # 关系库/时序库 DDL 生成
├── seed_data_generator/     # 列种子 + 行种子总集生成
├── jdbc_datasource/         # JDBC Connection Configuration
├── shared_memory_initializer/ # SetupTG 加载种子到 JMeter 共享内存
├── prepared_insert_template/ # T1 PreparedStatement 模板
├── direct_insert_write/    # T0 单条/批量 INSERT 模板
├── write_strategies/        # 写入策略模式 (T0/T1/T2)
├── throughput_control/      # ConstantThroughputTimer 配置
├── jmx_skeleton_generator/  # JMX 装配（SetupTG/WriteTG/QueryTG）
└── utils/                   # 通用工具

tests/                       # 633 pytest + 1 smoke fixture 对
docs/
├── specs/                   # 主规格 + 历史 review
├── issues/                  # F-17 issue + 最小 Java repro
└── changelogs/              # （保留位）
openspec/changes/            # DCR 归档
.claude/skills/
└── kwjdbc-jmx-smoke/       # 端到端 smoke 流程 skill
```

---

## 8. 常见问题

**Q: 跑 `jmeter -n` 报 `NumberFormatException: For input string: "${conn_pool_size}"`**
A: UDV 解析顺序问题。`pool_max = str(int(conn_pool_size))` 在 `JDBC Configuration` 之前求值。F-15 已修。

**Q: 报 `unable to resolve class CSVReader`**
A: JMeter lib/ext 无 opencsv.jar。生成器用 Groovy `line.split(',')` 替 `new CSVReader(...)`。F-12 已修。

**Q: `kwdb: ERROR: target database or schema does not exist`**
A: `db_url` 必须连 `defaultdb`（系统库永远在），不能连业务库（建库前不存在）。

**Q: `rtag_varchar_1` 在 DB 里全是 `""`（容器用 `kwdb/kwdb:latest` 或 `kwdb-x86_64-master-dbg`）**
A: F-17 server bug。换 `kwdb-x86_64-master:latest` (nightly)，详见 [docs/issues/F17.md](docs/issues/F17.md)。

**Q: 吞吐实测与 config 不符**
A: 自 2026-09-11 cfg-write-throughput-literal 起，写入 timer 的 `timeout` 直接烤死 cfg `write_config[].throughput` 字面量；`-Jwrite_throughput` 已**移除**（不会生效）。`throughput` 是**每线程**目标，线程组总 = `throughput × num_threads`。要调整写入速率：改 cfg `write_config[].throughput` 后重生成 JMX。

---

## 9. 参考

- 规格：[`docs/specs/kwdb-svt-test-plan-generator-spec.md`](docs/specs/kwdb-svt-test-plan-generator-spec.md)
- 修订历史：[`docs/specs/spec_review-2026-06-02.md`](docs/specs/spec_review-2026-06-02.md)
- 已知 issue：[`docs/issues/F17.md`](docs/issues/F17.md) + [`F17Repro.java`](docs/issues/F17Repro.java)
- DCR 归档：[`openspec/changes/`](openspec/changes/)（query-naming、throughput-control、main-entry 等）
- 进度跟踪：[`todolist.md`](todolist.md)（F-9..F-16 + R-1..R-3-续 + F-17 全部完成）

---

**License：** Internal use only. 依赖 KaiwuDB 商业产品，遵循 KaiwuDB 最终用户许可协议。
