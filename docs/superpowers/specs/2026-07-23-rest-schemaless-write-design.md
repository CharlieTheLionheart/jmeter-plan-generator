---
comet_change: rest-schemaless-write
role: technical-design
canonical_spec: openspec
status: final
---

# rest-schemaless-write — 深度技术设计

## 1. Context

`kwjdbc-svt` 当前所有写入路径都是 JDBC：`PreparedStatement INSERT` 走 `batch_prepared` / `single_insert` / `single_prepared` 模式。KaiwuDB 官方同时提供 **RESTful 无模式写入** 通道（`POST /restapi/influxdb` 等），允许 InfluxDB Line Protocol / OpenTSDB Telnet / OpenTSDB JSON 三种格式直接写入，服务端自动建表、自动扩列、自动调宽 VARCHAR。该通道是生产 ingestion 主流路径，但本仓库当前**零覆盖**：没有 HTTP Request sampler 模板、没有 SetupTG token 初始化、没有 DDL pre-create HTTP 编排、没有 `test_cfg.yaml` `rest_api` 配置段、没有对应的 JMeter JMX 产出路径。

约束（来自 reference doc + R&D 对齐）：

- `primary_tag VARCHAR(64)` 服务端黑盒 hash 主标签：研发明示是为「无 ptag 概念的用户业务」准备的兜底。**有 ptag 的场景必须先 DDL 预建表再用 InfluxDB API 写入**，tag key 与 ptag 同名时服务端写入已知 ptag 列而非生成 `primary_tag`。业务断言只落在命名列。
- token 共享：SetupTG Login 1 次拿 1 个长效 token，所有 TG 共享 `${__property(rest_token)}`。并发 ≤ 100 时无 server 警告（与现有 `batch_prepared` 共享语义一致）。
- HTTPS 双模式：`https_mode: insecure | tls` 由 `test_cfg.yaml` 切换，同端口 8080 同时支持 HTTP 与 HTTPS。
- DDL 失败处理：fail-fast，与现有 `ddl_setup.py` JDBC sampler 行为一致。
- **seed 数据复用**：现有 `seed_data_generator/orchestrator._generate_table_seeds` 已经按列烘焙 `seeds/{db}/{table}/{index}_{name}.csv` 文件，并在 `shared_memory_setup.py` SetupTG 中由 `SharedMemoryInitializerGenerator` 读 CSV 写 JMeter `props`（`__SHARED_MEM_{db}_{table}` + `_columns`）。JDBC 写入 TG 的 JSR223 PreProcessor 直接消费这些 props。**REST 路径沿用同一套 seed 文件 + 同一套 SharedMemory 加载机制**，只把 JSR223 PreProcessor 的「行 → JDBC batch」改为「行 → InfluxDB Line → `vars.put('request_body', line)`」。**`seed_data_generator` 与 `shared_memory_setup.py` 零改动**。

本 DCR 是 `design.md`（高层方案）+ `specs/rest-schemaless-write/spec.md`（6 Requirement / 11 Scenario）的**深度技术细化**，不重写上游；只补充实现层细节、模块边界、XML 结构、测试策略与边界条件。

## 2. Goals / Non-Goals

**Goals**

- 在 `mode: schemaless_influxdb` 下产出完整 JMeter JMX：SetupTG（Login + DDL pre-create）+ 至少 1 个写入 TG（HTTP POST `/restapi/influxdb` + Groovy PreProcessor 拼 InfluxDB Line body）+ 1 个 Query round-trip TG（HTTP POST `/restapi/query`）。
- 新增模块：`http_request_sampler_element`、`generate_ddl_setup_http_thread_group`、`rest_write_groups.py`（含 Groovy PreProcessor 模板）、`rest_query_groups.py`、`rest_api` config schema。
- 复用：`DDLGenerator.generate(...)` 输出、`setup_thread_group_element(...)` 外壳、`seed_data_generator/orchestrator._generate_table_seeds` 列烘焙、`shared_memory_setup.py` + `SharedMemoryInitializerGenerator` 的 SetupTG 加载机制、JMeter `props` 全局共享。**零 SQL 重写、零 SetupTG XML 重写、零 seed 文件生成重写、零 SharedMemory 加载重写**。
- 端到端 smoke：SetupTG Login + DDL `code==0` + 写入 `code==0` + `rows >= 1` + Query `rows >= 1` + DB `select count(*)` 一致 + `device_id` ptag 列非 NULL。

**Non-Goals**

- 不覆盖 OpenTSDB JSON / Telnet 协议（spec §0 P0 范围仅 InfluxDB Line）。
- 不覆盖 Basic Auth 与 token 续期（spec §9.4 #3 解决说明 → 功能测试范围）。
- 不新增 Python 第三方依赖；JMeter 内置 HTTP Request sampler + Groovy 已具备能力。
- 不重构 `DDLGenerator`、`seed_data_generator`、`shared_memory_setup.py`、`SharedMemoryInitializerGenerator` 与现有 `setup_thread_group_element(...)` 工具函数。

## 3. Architecture & Data Flow

### 3.1 模块边界

```
+-------------------------------------------------------------------+
| kwjdbc_svt/main.py (mode 路由)                                    |
|   mode=schemaless_influxdb → 调以下生成器                         |
+-------------------------------------------------------------------+
            |                |              |              |
            v                v              v              v
+--------------------+ +-----------------+ +-------------------+ +-------------------+
| DDLGenerator       | | generate_ddl_   | | generate_rest_    | | generate_rest_    |
| .generate(...)     | | setup_http_     | | write_thread_     | | query_thread_     |
| (现有, 零改动)     | | thread_group    | | group             | | group             |
+--------------------+ | (新增)          | | (新增, 含 Groovy) | | (新增)            |
                       +-----------------+ +-------------------+ +-------------------+
            |                |              |              |
            v                v              v              v
+-----------------------------------------------------------------------+
| utils/xml_helpers.py::http_request_sampler_element (新增, 4 个 TG 共用) |
+-----------------------------------------------------------------------+
            |
            v
+-----------------------------------------------------------------------+
| setup_thread_group_element(...) (现有, 零改动)                        |
+-----------------------------------------------------------------------+

+-----------------------------------------------------------------------+
| 复用现有 seed → SharedMemory 加载机制（零改动）                       |
|                                                                       |
| seed_data_generator/orchestrator._generate_table_seeds                 |
|   → 写 seeds/{db}/{table}/{index}_{name}.csv + seeds/{db}/{table}.csv |
|                                                                       |
| shared_memory_setup.generate_shared_memory_setup_thread_group          |
|   → SetupTG 内 JSR223 PreProcessor 读 CSV → 写 props                   |
|     (__SHARED_MEM_{db}_{table} + __SHARED_MEM_{db}_{table}_columns)   |
|                                                                       |
| 写入 TG 的 Groovy PreProcessor 直接读 props，按列 group 拼             |
| InfluxDB Line Protocol，写 vars.request_body                          |
+-----------------------------------------------------------------------+
```

数据流：

```
test_model.yaml + test_cfg.yaml
    │
    │ seed_data_generator/orchestrator._generate_table_seeds (现有)
    ▼
seeds/{db}/{table}/{index}_{name}.csv + seeds/{db}/{table}.csv
    │
    │ SharedMemoryInitializerGenerator (现有) 在 SetupTG 加载
    ▼
JMeter props: __SHARED_MEM_{db}_{table} + __SHARED_MEM_{db}_{table}_columns
    │
    ├─→ DDLGenerator.generate(test_model_config) → List[str] (DDL)
    │     │
    │     ├─→ generate_ddl_setup_http_thread_group → http_request_sampler_element × N (SetupTG 内)
    │     │
    │     └─→ generate_rest_query_thread_group → http_request_sampler_element × M (Query TG)
    │
    └─→ generate_rest_write_thread_group → M 个 sampler，每个 sampler 前置 1 个 Groovy PreProcessor
          │   读 props → 拼 InfluxDB Line → vars.put('request_body', line)
          └→   HTTPSamplerProxy body 引用 ${request_body}
```

### 3.2 SetupTG 启动序列

**显式锁定启动顺序**：Login → DDL pre-create → SharedMemory → （JMeter 调度到写入 TG）。语义上「先准备好 DB（DDL 建表）→ 再准备好数据（CSV → props）→ 再触发负载」。SharedMemory 不依赖 DB 表存在（仅预热 JMeter props），但显式顺序便于后续维护者推理。

```
[SetupTG, num_threads=1, scheduler, duration=1, ramp=1]
  │
  ├─[1] HTTPSamplerProxy (Login)
  │      GET /restapi/login
  │      Authorization: Basic base64(${rest_api.login_user}:${rest_api.login_password})
  │      → Response Assertion: HTTP 200
  │
  ├─[2] JSON Extractor (提取 token)
  │      responseBody → ${token} (JSONPath: $.token)
  │
  ├─[3] JSR223 PostProcessor (setProperty)
  │      ${__setProperty(rest_token, ${token})}
  │
  ├─[4] HTTPSamplerProxy (DDL pre-create) × N   ← 仅 pre_create_tables=true
  │      POST ${rest_api.ddl_url_path}
  │      Authorization: Basic ${__property(rest_token)}
  │      Body: <单条 DDL SQL>
  │      → Response Assertion: responseBody.code == 0
  │      → fail-fast on any non-zero code
  │
  ├─[5] SharedMemory SetupTG（独立 SetupTG, num_threads=1, scheduler, duration=60, loops=1）   ← 现有实现, 零改动
  │      JSR223PreProcessor (groovy) × N (per table) 读 seeds/{db}/{table}.csv → 写 props
  │      __SHARED_MEM_{db}_{table} + __SHARED_MEM_{db}_{table}_columns
  │
  └─[6] HTTPSamplerProxy (final assert)        ← 可选：检查 ${rest_token} 非空
```

### 3.3 写入 TG 模板（每 measurement）

```
[ThreadGroup, num_threads=N, duration=test_duration, scheduler]
  │
  ├─ConstantThroughputTimer (cfg `wc.throughput` 字面量)
  │
  ├─JSR223PreProcessor (Groovy: 拼 InfluxDB Line body)   ← 新增
  │   读 globalProps.__SHARED_MEM_{db}_{table} (行列表) + _columns (header)
  │   按列 group 分 ptagNames / tagNames / fieldNames
  │   rowIdx = (ctx.getThreadNum() + iteration * threadCount) % rows.size()
  │   deviceStart / devicePerThread 注入 ptag 列 (first ptag 运行时填 device_<n>)
  │   ts = System.nanoTime()
  │   line = <measurement>,<ptag>=device_<n>,<tag>=<v> <field>=<v>,... <ts>
  │   vars.put('request_body', line)
  │
  ├─HTTPSamplerProxy (HTTP Write)
  │   Protocol: ${__P(rest_api.protocol)} (http | https)
  │   Server:   ${db_host} (从 db_url 解析)
  │   Port:     ${rest_api.http_port}
  │   Method:   POST
  │   Path:     ${rest_api.write_url_path}?db=${rest_api.default_db}&tz=${rest_api.timezone}
  │   Headers:
  │     Content-Type: text/plain
  │     Accept: application/json
  │     Authorization: Basic ${__property(rest_token)}
  │   Body: ${request_body}   ← 运行时由前置 Groovy 设置
  │   customizedSslContext: ${rest_api.ca_cert_path} (仅 https_mode=tls)
  │   → Response Assertion: responseBody.code == 0
  │
  └─ConstantThroughputTimer 维持 QPS
```

### 3.4 Query round-trip TG 模板

```
[ThreadGroup, num_threads=1, duration=run-once, scheduler, loops=1]
  │
  ├─HTTPSamplerProxy (Query) × M (per measurement)
  │   POST ${rest_api.query_url_path}
  │   Headers: 同写入 TG
  │   Body: select count(*) from <measurement>;
  │   → JSON Extractor: responseBody.rows → ${rows}
  │   → Response Assertion: ${rows} >= <expected_rows>
```

### 3.5 InfluxDB Line Protocol 序列化规则（**Groovy 运行时拼**）

**由写入 TG 的 JSR223 PreProcessor 在 JMeter 运行时执行**（不是生成阶段）。`seed_data_generator` 与 `shared_memory_setup.py` 零改动。

**转义表**（Groovy 内 `escapeLineValue(s: String) -> String` 函数）：

| 字符 | 规则 |
|------|------|
| 空格 | `\` 前缀转义为 `\ ` |
| 逗号 | `\,` |
| 等号 | `\=` |
| 换行 | `\n` |
| 字符串字段值 | 必加双引号 `"..."`；内部 `"` 转义为 `\"` |
| 数值字段值 | 不加引号；Float 含 `.`、Integer 无 `.` |
| timestamp | 显式纳秒（`System.nanoTime()`，13 位 epoch × 10⁶ 整数） |
| tag value | 必为字符串；同样 `escapeLineValue` 转义 |
| field value (bool) | `t` / `f` 字面量 |

**Line 格式**（Groovy `buildLine(measurement, ptagNames, tagNames, fieldNames, row, deviceStart, devicePerThread, rowIdx, ts) -> String`）：

```
<measurement>,<ptag>=<device_n>,<tag>=<v> <field>=<v>,... <ts>
```

- `ptagNames` 第一个 ptag：值为 `device_<deviceStart + (rowIdx % devicePerThread)>`（与现有 JDBC 路径 PreProcessor 的 device_code 注入逻辑一致）
- `tagNames` 按 `test_model.yaml` 中 `regular_tags` 列顺序
- `fieldNames` 按 `test_model.yaml` 中 `data_cols` 列顺序
- `tag_set` 多个 `tag_key=tag_value` 用 `,` 分隔
- `field_set` 多个 `field_key=field_value` 用 `,` 分隔
- 三段之间用半角空格

`tag_set` 中 tag key **必须**与 DDL pre-create 中 ptag / tag 列名同名 → 服务端把 tag 值写入已知列；若 tag key 不在 DDL 中 → 服务端自动 `ALTER TABLE ADD TAG`（spec 允许，spec §9.4 #2 接受限流暴露）。

## 4. Implementation Details

### 4.1 `http_request_sampler_element`（`utils/xml_helpers.py` 新增）

签名：

```python
def http_request_sampler_element(
    method: str,                    # GET | POST | PUT | DELETE
    path: str,                      # 完整路径，含 query string
    headers: Dict[str, str],        # 标准 HeaderManager 字典
    body: Optional[str],            # POST/PUT/PATCH body；GET/DELETE 传 None
    ssl_context: Optional[str],     # CA 证书路径；None 表示 insecure
    *,
    name: str,
    testname: str,
    follow_redirects: bool = True,
) -> Tuple[Element, Element]:
    """返回 (sampler_xml, hashTree)。"""
```

实现要点：

- 产出 `HTTPSamplerProxy` 元素（JMeter 5.6+ 标准 HTTP Request sampler 类），属性 `HTTPSampler.method`、`HTTPSampler.path`、`HTTPSampler.follow_redirects=auto`、`HTTPSampler.use_keepalive=true`、`HTTPSampler.postBodyRaw=true`（当 body 非空）；`protocol` / `port` / `domain` 由 caller 在 sampler properties 子树显式注入（沿用 `HTTPSampler.protocol` / `.port` / `.domain` 三种 stringProp 约定），函数本体不写。详见 `docs/refs/jmx-components-references.md` §HTTPSamplerProxy 与 `docs/refs/jmeter-testplan-reference.md` §18.1 HTTP Request。
- HeaderManager 作为子 `hashTree`，每行 header 一个 `HeaderManager.header` 元素。
- `ssl_context` 非空时产出 `HTTPSampler.customizedSslContext=${ssl_context}` 与 `JMeterproperty: ssl.keystore.file=${ssl_context}`（JMeter 5.6+ 同时需要两个属性才能正确加载证书）。
- body 非空时产出 `HTTPSampler.postBodyRaw=true` + `<stringProp name="Argument.value">${body}</stringProp>` 在 `Arguments` 子树中（**JMeter 默认无 CDATA 包裹**，与 JDBC Sampler 写法一致；详见 `docs/refs/jmx-components-references.md` §HTTPSamplerProxy）。
- 当 body 是 Groovy 变量引用（如 `${request_body}`）时，JMeter 运行时自动展开，无需生成阶段求值。

### 4.2 `generate_ddl_setup_http_thread_group`（`jmx_skeleton_generator/generators/ddl_setup.py` 新增）

签名（与现有 `generate_ddl_setup_thread_group` 对齐）：

```python
def generate_ddl_setup_http_thread_group(
    ddl_statements: List[str],
    *,
    name: str = "DDL Setup (REST)",
    num_threads: int = 1,
    rel_init_specs: Optional[Sequence[Dict[str, Any]]] = None,
    rest_api_config: Dict[str, Any],  # {https_mode, login_url_path, ddl_url_path, http_port, ca_cert_path}
) -> List:
    """返回 [SetupThreadGroup, hashTree]，含 Login + DDL pre-create HTTP samplers。"""
```

实现要点：

- **Step A**：生成 Login HTTP sampler（`GET ${rest_api_config[login_url_path]}` + `Authorization: Basic base64(login_user:login_password)`）。
- **Step B**：生成 JSON Extractor（`$.token` → `${token}`）+ JSR223 PostProcessor（`${__setProperty(rest_token, ${token})}`）。
- **Step C**：当 `rest_api_config[pre_create_tables]=true` 时遍历 `ddl_statements`，每条生成 DDL HTTP sampler（`POST ${rest_api_config[ddl_url_path]}` + `Authorization: Basic ${__property(rest_token)}` + body 为该 SQL）。
- **Step D**：调用现有 `setup_thread_group_element(name=testname, num_threads=1, ramp_time=1, duration=1, delay=0, loops=1, scheduler=True, children=children)`。
- 每个 sampler 配 Response Assertion 子节点（JSR223 Assertion，断言 `code==0`）—— **fail-fast** 实现。
- **不**触碰现有 `generate_ddl_setup_thread_group` 函数。

### 4.3 `generate_rest_write_thread_group`（`jmx_skeleton_generator/generators/rest_write_groups.py` 新增）

签名：

```python
def generate_rest_write_thread_group(
    test_model_config: TestModelConfig,
    rest_api_config: Dict[str, Any],
    *,
    name: str = "REST Write",
    throughput_qps: Optional[float] = None,  # 烤死为 cfg 字面数值（无 UDV 入口）
) -> List:
    """返回 [ThreadGroup, hashTree]。"""
```

实现要点：

- 对 `test_model_config` 每个 measurement 生成 1 个 sampler 单元（`JSR223PreProcessor` + `HTTPSamplerProxy` 一对）。
- **每个 measurement 的种子文件已由 `seed_data_generator/orchestrator._generate_table_seeds` 烘焙**（路径透传到主入口；REST 路径不重写）。SharedMemory SetupTG 由 `shared_memory_setup.generate_shared_memory_setup_thread_group(seed_csv_paths, ...)` 生成，**沿用现有逻辑**。
- **Groovy PreProcessor**：从 `globalProps.__SHARED_MEM_{db}_{table}` + `_columns` 读行 + 列名；按 `test_model_config` 的列 group（ptag / regular_tags / data_cols）拆分；运行时拼 InfluxDB Line（`escapeLineValue` + `buildLine`）；`vars.put('request_body', line)`。详见 §4.7 Groovy 模板。
- HTTPSamplerProxy Path：`${rest_api.write_url_path}?db=${rest_api.default_db}` + 当 `rest_api.timezone` 非空时追加 `&tz=${rest_api.timezone}`。
- Header：`Content-Type: text/plain`、`Accept: application/json`、`Authorization: Basic ${__property(rest_token)}`。
- Body：`${request_body}`（Groovy PreProcessor 运行时设置）。
- `ssl_context`：`${rest_api.ca_cert_path}` 仅当 `https_mode=tls`。
- 沿用现有 `ConstantThroughputTimer`，cfg `wc.throughput` 字面量烤死。
- 每个 sampler 配 Response Assertion（`code==0`）。

### 4.4 `generate_rest_query_thread_group`（`jmx_skeleton_generator/generators/rest_query_groups.py` 新增）

签名：

```python
def generate_rest_query_thread_group(
    test_model_config: TestModelConfig,
    rest_api_config: Dict[str, Any],
    *,
    name: str = "REST Query Round-Trip",
) -> List:
    """返回 [ThreadGroup, hashTree]。"""
```

实现要点：

- 每个 measurement 生成 1 个 HTTP sampler，body `select count(*) from <measurement>;`。
- JSON Extractor：`responseBody.rows` → `${rows}`（JSONPath `$.rows`）。
- Response Assertion：`${rows} >= <expected_rows>`（expected_rows 由 `test_model_config` 的 `seed_num` / `device_per_thread` 推导）。
- **不**对 `primary_tag` 列做断言（`pre_create_tables=true` 时该列不存在；`false` 时值不可预测）。
- 沿用 `ConstantThroughputTimer` + `query_throughput` UDV。

### 4.5 `rest_api` 配置 schema（`src/config_parser/`）

新增 `rest_api` 段 schema：

```python
@dataclass
class RestApiConfig:
    https_mode: Literal["insecure", "tls"]
    http_port: int                              # 默认 8080
    ca_cert_path: Optional[str]                 # https_mode=tls 时必填
    login_user: str                             # 默认 "root"
    login_password: str                         # 默认 ""
    login_url_path: str                         # 默认 "/restapi/login"
    ddl_url_path: str                           # 默认 "/restapi/ddl"
    write_url_path: str                         # 默认 "/restapi/influxdb"
    query_url_path: str                         # 默认 "/restapi/query"
    default_db: str                             # 默认 "defaultdb"
    timezone: Optional[str]                     # 可选
    pre_create_tables: bool                     # 默认 True
```

校验规则：

- `https_mode` 不在 `{insecure, tls}` → `RestConfigError`。
- `https_mode=tls` 且 `ca_cert_path` 空 → `RestConfigError`（fail-fast）。
- `mode: schemaless_influxdb` 但 `test_cfg.yaml` 无 `rest_api` 段 → `RestConfigError`。
- `mode` 不为 `schemaless_influxdb` 但 `rest_api` 段存在 → 静默忽略（向后兼容）。
- `http_port` 不在 `[1, 65535]` → `RestConfigError`。

### 4.6 mode 路由（`kwjdbc_svt/main.py`）

新增分支（在现有 `batch_prepared` / `single_insert` / `single_prepared` / `schemaless` 占位报错 之后）：

```python
elif mode == "schemaless_influxdb":
    from ddl_generator.generator import DDLGenerator
    from jmx_skeleton_generator.generators.ddl_setup import generate_ddl_setup_http_thread_group
    from jmx_skeleton_generator.generators.rest_write_groups import generate_rest_write_thread_group
    from jmx_skeleton_generator.generators.rest_query_groups import generate_rest_query_thread_group

    ddl_gen = DDLGenerator(test_model_config, test_cfg)
    ddl_statements = ddl_gen.generate()

    # seed_data_generator 已生成 seeds/{db}/{table}/*.csv (现有实现, 零改动)
    # SharedMemory SetupTG 由 generate_shared_memory_setup_thread_group 装配 (现有, 零改动)
    seed_csv_paths = ...  # 从 seed_data_generator 输出路径解析

    # SetupTG 装配顺序: DDL pre-create (HTTP) → SharedMemory (CSV→props) → 写入 TG (Groovy 拼 line)
    setup_tg = generate_ddl_setup_http_thread_group(
        ddl_statements,
        rel_init_specs=_build_relational_init_specs(test_model_config),
        rest_api_config=rest_api_config,
    )
    shared_mem_tg = generate_shared_memory_setup_thread_group(seed_csv_paths)
    write_tg = generate_rest_write_thread_group(test_model_config, rest_api_config)
    query_tg = generate_rest_query_thread_group(test_model_config, rest_api_config)

    elements.extend([*setup_tg, *shared_mem_tg, *write_tg, *query_tg])
```

**不**调任何 JDBC sampler 生成函数（`jdbc_sampler_element`、`generate_ddl_setup_thread_group` 旧版、现有 `write_groups.py` 写入逻辑）。`rest_write_groups.py` 只产出 HTTP sampler + Groovy PreProcessor，**不**走 `write_groups.py` 现有 `format_jdbc_values`。

### 4.7 Groovy PreProcessor 模板（`rest_write_groups.py` 内联）

Groovy 脚本骨架（注入到每个 measurement 写入 sampler 的前置 JSR223PreProcessor）：

```groovy
// JSR223PreProcessor (groovy): REST Write 拼 InfluxDB Line body
def tableName = "db.meters"          // 由生成器按 measurement 注入
def ptagNames = ["device_id"]        // 从 test_model_config.primary_tags (first ptag 用于 device_<n>)
def tagNames  = ["location"]         // 从 test_model_config.regular_tags
def fieldNames = ["current","voltage","phase"]  // 从 test_model_config.data_cols

// 1. 读 SharedMemory props（由 SharedMemory SetupTG 预填）
def rowsKey = "__SHARED_MEM_" + tableName.replace('.', '_')
def rows = globalProps.get(rowsKey) as ArrayList
def columnNames = globalProps.get(rowsKey + "_columns") as ArrayList
if (rows == null || rows.isEmpty()) {
    log.error("REST Write: shared rows empty for " + tableName)
    throw new IllegalStateException("empty shared rows")
}

// 2. 选行
def threadCount = ctx.getThreadGroup().getNumThreads()
int rowIdx = (ctx.getThreadNum() + iteration * threadCount) % rows.size()
def row = rows[rowIdx]

// 3. device_start / device_per_thread 注入 first ptag
def deviceStart = Long.parseLong(vars.get("device_start") ?: "1")
def devicePerThread = Integer.parseInt(vars.get("device_per_thread") ?: "1")

// 4. 按列 group 拼 tag_set / field_set + 转义
def ts = System.nanoTime()
def measurement = tableName.substring(tableName.indexOf('.') + 1)
def sb = new StringBuilder()
sb.append(measurement)

// ptag section: first ptag → device_<n>
if (ptagNames && ptagNames.size() > 0) {
    def firstPtag = ptagNames[0]
    sb.append(',').append(firstPtag).append('=device_').append(deviceStart + (rowIdx % devicePerThread))
}
// remaining ptag + regular_tags from row
ptagNames.drop(1).each { name ->
    int csvIdx = columnNames.indexOf(name)
    if (csvIdx < 0 || csvIdx >= row.size()) return
    def raw = row.get(csvIdx)?.toString() ?: ""
    sb.append(',').append(name).append('=').append(escapeLineValue(raw))
}
tagNames.each { name ->
    int csvIdx = columnNames.indexOf(name)
    if (csvIdx < 0 || csvIdx >= row.size()) return
    def raw = row.get(csvIdx)?.toString() ?: ""
    sb.append(',').append(name).append('=').append(escapeLineValue(raw))
}

// field section
sb.append(' ')
fieldNames.each { name ->
    int csvIdx = columnNames.indexOf(name)
    if (csvIdx < 0 || csvIdx >= row.size()) return
    def raw = row.get(csvIdx)?.toString() ?: ""
    sb.append(name).append('=').append(formatFieldValue(name, raw))
    sb.append(',')
}
if (sb.charAt(sb.length() - 1) == ',') sb.deleteCharAt(sb.length() - 1)
sb.append(' ').append(ts)

vars.put("request_body", sb.toString())

// --- helpers ---
String escapeLineValue(String s) {
    if (s == null) return ""
    return s.replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=").replace("\n", "\\n")
}
String formatFieldValue(String fieldName, String raw) {
    if (raw == null || raw.isEmpty()) return "\"\""
    // 启发式: 含 '.' → float; 全数字 → int; 否则 string
    if (raw ==~ /^-?\d+$/) return raw
    if (raw ==~ /^-?\d+\.\d+$/) return raw
    if (raw == "true" || raw == "false") return raw
    return "\"" + raw.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
}
```

**关键点**：

- `globalProps` 是 JMeter `JMeterProperties` 单例（在 SetupTG JSR223 与写入 TG JSR223 间共享）；与现有 JDBC PreProcessor 一致（`write_groups.py:469`）。
- `device_<n>` 注入逻辑与 JDBC 路径完全一致（参考 `write_groups.py:505`）。
- `escapeLineValue` + `formatFieldValue` 在 Groovy 脚本内联定义（不依赖外部 Java 类，避免 JMeter 类路径问题）。
- `vars.put('request_body', ...)` 写入 per-thread context；HTTPSamplerProxy body 引用 `${request_body}` 运行时展开。

## 5. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `JMeter 5.6+ HTTPSampler.customizedSslContext` 属性 schema 严格 | TLS 模式 sampler 被 JMeter 加载时失败 | `tests/jmx_skeleton_generator/test_http_request_sampler_element.py` 用 XSD 校验；端到端 smoke 跑两次（insecure + tls）确保 JMeter 5.6+ 可加载 |
| token 60 分钟过期 vs 长 test_duration | 超 60 分钟 token 失效，写入失败 | spec §9.4 #3 解决：token 续期归功能测试；P0 默认 `test_duration < 60min` |
| `pre_create_tables=false` 时服务端 `primary_tag VARCHAR(64)` 不可断言 | 对照 fixture 断言设计复杂 | spec §9.3 行 #10：仅断言 `SHOW CREATE TABLE meters` 包含 `primary_tag` 列存在，不读其值 |
| Groovy `escapeLineValue` / `formatFieldValue` 转义不充分导致服务端解析错误 | 服务端把空格后字符当作下一列 | `tests/jmx_skeleton_generator/test_groovy_influxdb_line_template.py` 单测：空格、逗号、等号、换行、引号各自转义；`escapeLineValue` 单元化后可直接 Groovy `evaluate` 验证；smoke 用包含特殊字符的 seed 值验证 |
| Groovy 脚本依赖 `globalProps` 生命周期 | SetupTG 结束后 `props` 销毁 | `JMeterProperties` 单例生命周期 = JVM，跨 TG 持久；现有 `write_groups.py:469` 已验证 |
| `vars.put('request_body', ...)` 在 HTTPSampler 之前未生效 | body 为空字符串发送 | PreProcessor **必须**在 HTTPSampler 之前（JSR223PreProcessor 作用域）；JMeter XML 编排保证 |
| DDL pre-create 重复跑同 fixture 时表已存在 | SetupTG DDL sampler 返回 `code=-1` → fail-fast → 写入 TG 不启动 | spec §6.1 已声明重复跑需手动清库；fixture 模板示例 `default_db` 鼓励含运行时间戳；build 阶段在 `kwjdbc-jmx-smoke` skill SKILL.md 加「smoke 前清库」前置 |
| `rest_conn_pool_size` 与 `conn_pool_size` 默认值绑定 | 一个 UDV 改动影响两个 pool | spec §6.3 Decision 2：两个 pool 独立但默认同值；`test_cfg.yaml` 显式分开配置 |
| 多 measurement DDL pre-create 顺序与 FK 依赖 | FK 引用表未建先建被引用表 → 服务端报错 | `DDLGenerator.generate(...)` 已按依赖顺序输出 DDL（参考 R-3 FK 实现）；HTTP 路径沿用同源 |
| `HTTPClient` 长连接 + 服务端 TLS 重协商 | TLS sampler 偶发握手失败 | JMeter `httpclient4.idle_timeout` 与 `httpclient4.validate_after_inactivity_period` 用 HTTPClient 默认值；smoke 跑 ≥ 10 次取平均 |
| `rest_api` 配置段缺失但 `mode != schemaless_influxdb` | 向后兼容破坏 | spec §6.3 + §4.5 校验规则：`mode != schemaless_influxdb` 时 `rest_api` 段静默忽略 |
| 现有 `seed_data_generator` + `shared_memory_setup.py` 改动引入回归 | shig 等已有 fixture smoke 失败 | **零改动原则**：seed 文件生成 + SharedMemory 加载机制完全沿用；只在 `main.py` mode 路由分流；回归测试 `tests/kwjdbc_svt/test_main_routes_schemaless_influxdb.py` 加 `mode: batch_prepared` + 无 `rest_api` → 不报错用例 |
| Groovy `JMeterProperties` vs `props` 命名混淆 | PreProcessor 读不到 props | 严格沿用现有 `write_groups.py:469` 用法；`props` 是 JSR223 per-context，`JMeterProperties` 单例 = `globalProps`；写 Groovy 模板时显式注释 |

## 6. Test Strategy

### 6.1 单元测试

- `tests/utils/test_http_request_sampler_element.py`
  - GET 无 body、POST 有 body、PUT/DELETE method 切换
  - HeaderManager 子节点正确产出
  - `ssl_context` 非空 → 产出 `HTTPSampler.customizedSslContext` + `JMeterproperty: ssl.keystore.file`
  - `ssl_context` None → 不产出 ssl 节点
  - `body` 注入到 `Arguments` 子树 `postBodyRaw=true`
  - `body="${request_body}"` 变量引用 → 产出 `${request_body}` 字面量（JMeter 运行时展开）
  - 返回 `(sampler, hashTree)` 配对正确
- `tests/jmx_skeleton_generator/test_ddl_setup_http_thread_group.py`
  - `pre_create_tables=true` → SetupTG 含 Login + DDL sampler 列表
  - `pre_create_tables=false` → SetupTG 仅含 Login sampler
  - `https_mode=tls` + `ca_cert_path` 缺失 → `RestConfigError`
  - `https_mode=insecure` → DDL sampler 不带 `customizedSslContext`
  - 多个 DDL statements → SetupTG 含 N 个 DDL sampler
  - `rel_init_specs` 透传（保持现有 JDBC 路径 RelInit 行为）
- `tests/jmx_skeleton_generator/test_rest_write_groups.py`
  - 单 measurement 输出 1 个 sampler 单元（JSR223PreProcessor + HTTPSamplerProxy）
  - 多 measurement 输出 N 个 sampler 单元
  - `tag_set` key 与 DDL ptag 对齐 → PreProcessor 拼出的 line 正确格式
  - 验证 sampler body 为 `${request_body}` 变量引用（不是烘焙的字符串）
  - 验证 PreProcessor 内 Groovy 脚本含 `escapeLineValue` + `formatFieldValue` + `buildLine` 关键调用
  - Path 拼接 `?db=` + 可选 `?tz=` 正确
  - `https_mode=tls` → `customizedSslContext` 注入
  - `https_mode=insecure` → 不带 ssl
- `tests/jmx_skeleton_generator/test_groovy_influxdb_line_template.py`
  - `escapeLineValue` Groovy 函数：空格 → `\ `、逗号 → `\,`、等号 → `\=`、换行 → `\n`、引号 → `\"`、`\` → `\\`
  - `formatFieldValue` 启发式：纯数字 → int；含 `.` → float；`true`/`false` → bool；其他 → quoted string
  - `buildLine` 完整 line：`<measurement>,<ptag>=device_<n>,<tag>=<v> <field>=<v>,... <ts>`
  - first ptag 注入 `device_<deviceStart + (rowIdx % devicePerThread)>`
  - 行索引用模 `rows.size()` 循环
  - **测试方式：纯 Python `unittest` 镜像实现覆盖关键转义 + 行拼接逻辑**（**不**依赖 groovy CLI / JDK；零新 CI 依赖；Groovy 语义 drift 由 smoke 二次校准）
- `tests/jmx_skeleton_generator/test_rest_query_groups.py`
  - 每个 measurement 生成 1 个 Query sampler
  - `Authorization` 头正确
  - JSON Extractor 路径 `$.rows` 正确
  - Response Assertion 阈值正确
  - 断言**不**含 `primary_tag` 字段
- `tests/config_parser/test_rest_api_config.py`
  - 各字段必填 / 类型 / enum 校验
  - `https_mode=tls` + `ca_cert_path` 空 → `RestConfigError`
  - `https_mode` 非法值 → `RestConfigError`
- `tests/kwjdbc_svt/test_main_routes_schemaless_influxdb.py`
  - `mode: schemaless_influxdb` + 合法 `rest_api` → 生成完整 JMX（SetupTG + SharedMemory TG + 写入 TG + Query TG）
  - 缺 `rest_api` 段 → `RestConfigError`
  - `mode: batch_prepared` + 缺 `rest_api` 段 → 不报错（向后兼容）
  - `mode: schemaless_influxdb` + `https_mode=tls` + 缺 `ca_cert_path` → `RestConfigError`
  - `mode: schemaless`（占位报错）+ `rest_api` 段 → 仍按 spec §7 报错
  - 验证 `mode: schemaless_influxdb` 输出**不含**任何 `jdbc_sampler_element` / `generate_ddl_setup_thread_group` JDBC 元素

### 6.2 端到端 fixture

- `tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml`：单 measurement `meters`、ptag `device_id`、2 tag、3 field。
- `tests/kwjdbc_svt/fixtures/test_cfg_schemaless.yaml`：`mode: schemaless_influxdb` + `rest_api.https_mode=insecure` + `pre_create_tables=true`、默认值齐全。
- `tests/kwjdbc_svt/fixtures/test_model_schemaless_noptag.yaml`（对照）：`pre_create_tables=false`，验证 `primary_tag VARCHAR(64)` 黑盒列存在但不读其值。

### 6.3 smoke（kwjdbc-jmx-smoke skill）

- 跑 `tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml` + `test_cfg_schemaless.yaml`：
  1. SetupTG Login → 响应 `code==0` + `${rest_token}` 非空
  2. SetupTG DDL pre-create → 所有 DDL 响应 `code==0`
  3. SharedMemory SetupTG → seeds/*.csv 加载完成
  4. 写入 TG JTL response → `code==0` 且 `rows >= 1`；第一条 sample 的 `requestBody`（JMeter View Results Tree 可见）符合 InfluxDB Line 格式 + `device_id=device_<n>` ptag 注入正确
  5. Query round-trip TG → `rows >= 1`
  6. DB 内 `select count(*) from meters` 行数与 JMeter 写入一致
  7. `device_id` ptag 列非 NULL 且采样值在 `device_<start>..device_<start+num_threads*device_per_thread>` 范围
- 第二次跑（`https_mode=tls` + 真实 `ca_cert_path`）：验证 TLS 通道完整。`ca.crt` 生成与拷贝流程参考 [`docs/refs/kaiwudb-tls-cert-reference.md`](../refs/kaiwudb-tls-cert-reference.md) §3 / §5；`kwjdbc-jmx-smoke` skill SKILL.md 加 `--tls` 可选模式分支（build 阶段任务 6.4；不改 insecure 默认行为）
- 记录两次 smoke 的 QPS / latency 差到 `docs/refs/kaiwudb-schemaless-write-reference.md` §9.5

### 6.4 回归保护

- 全量 `python -m pytest tests/ -q`：新增测试 + 现有 633 个测试全 pass（参考 `ddl-generator` change 完成态）
- `tests/kwjdbc_svt/test_main_routes_schemaless_influxdb.py` 加 `mode: batch_prepared` + 无 `rest_api` 段 → 不报错的回归用例
- 跑 shig canonical smoke 一次（`tests/kwjdbc_svt/fixtures/test_model_shig.yaml` + `test_cfg_shig.yaml`）：验证 JDBC 路径不受 schemaless_influxdb mode 路由分流影响

## 7. Open Questions

无。所有决策已落地：

- token 60 分钟过期 vs 长 test_duration：spec §9.4 #3 已解决（P0 默认短测不验），不在 P0 范围
- `rest_conn_pool_size` 默认值：与 `conn_pool_size` 默认值绑定，两个 pool 独立但配置同值（brainstorm 决策）
- DDL pre-create Response Assertion 细节：用 JSR223 Assertion 断言 `responseBody.code == 0`（brainstorm 决策）
- Query round-trip TG `ConstantThroughputTimer`：沿用 `query_throughput` UDV，与现有 query TGs 一致
- HTTP `content-encoding` header：spec §4.1 默认 `text/plain`，与 InfluxDB Line 一致；不另行指定 gzip
- Groovy 脚本测试方式：Python 镜像实现（无 groovy CLI 依赖）
- TLS `ca_cert_path` 来源：参考 [`docs/refs/kaiwudb-tls-cert-reference.md`](../refs/kaiwudb-tls-cert-reference.md) §3 / §5
- SetupTG 启动顺序：Login → DDL pre-create → SharedMemory（§3.2）
- smoke skill TLS 模式：build 阶段任务 6.4（不改 insecure 默认行为；保留现有调用）

## 8. 引用

- 上游 OpenSpec 产物：`openspec/changes/rest-schemaless-write/{proposal,design,tasks,review}.md` + `specs/rest-schemaless-write/spec.md`
- 参考文档：
  - `docs/refs/kaiwudb-schemaless-write-reference.md`（无模式写入 REST API + 协议格式）
  - `docs/refs/kaiwudb-tls-cert-reference.md`（TLS 证书生成与使用）
- Brainstorm 检查点：`openspec/changes/rest-schemaless-write/.comet/handoff/brainstorm-summary.md`
- 现有 DDL 生成器（复用）：`src/ddl_generator/generator.py::DDLGenerator.generate(...)`
- 现有 SetupTG 外壳（复用）：`src/jmx_skeleton_generator/generators/ddl_setup.py::setup_thread_group_element(...)`
- **现有 seed 生成器（复用，零改动）**：`src/seed_data_generator/orchestrator.py::_generate_table_seeds` → 输出 `seeds/{db}/{table}/{index}_{name}.csv` + `seeds/{db}/{table}.csv`
- **现有 SharedMemory 加载机制（复用，零改动）**：`src/jmx_skeleton_generator/generators/shared_memory_setup.py::generate_shared_memory_setup_thread_group` + `src/shared_memory_initializer/` → 写 `props.__SHARED_MEM_{db}_{table}` + `_columns`
- 现有写入 TG 写入逻辑（参考模板）：`src/jmx_skeleton_generator/generators/write_groups.py` 中 JSR223 PreProcessor 读 `globalProps` + Groovy 行展开（device_<n> 注入 / columnNames 索引 / rowCopy）