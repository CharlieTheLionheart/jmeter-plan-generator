# KaiwuDB 无模式写入（Schemaless Writing）REST API 参考

> 来源：[无模式写入](https://doc.kaiwudb.com/template_version/pc/doc/development/restful-api/schemaless-writing.html) + [RESTful API](https://doc.kaiwudb.com/template_version/pc/doc/development/restful-api/connect-restful-api.html)
>
> 版本基线：dev（与 v3.2.x 一致的企业版文档树）
>
> 用途：为无模式写入（Schemaless Writing）DCR 提供协议规范、端点、报文格式、类型映射、行为边界参考资料。

## 0. 本 DCR 的 P0 范围（边界声明）

| 维度 | P0 决定 | 留待 P1+ |
|------|---------|----------|
| 支持协议 | **InfluxDB Line**（`POST /restapi/influxdb`） | OpenTSDB JSON、OpenTSDB Telnet |
| 认证方式 | **Token 认证**（`GET /restapi/login` 拿长效 token） | Basic Auth（每次临时令牌） |
| Token 生命周期 | Setup ThreadGroup 调用 `/restapi/login` 一次，写入共享变量；后续 ThreadGroup 共享；过期前重取 | — |
| HTTPS 模式 | **insecure**（HTTP 明文，跳过证书校验）/ **TLS**（HTTPS + CA 证书），由 `test_cfg.yaml` 配置项切换 | mTLS |
| 接入入口 | `POST /restapi/influxdb?db=<db_name>` | 其他端点 |
| 时序表类型 | 普通时序表（服务端默认） | 稀疏时序表 |

> 文档中标注 **「P1+」** 的小节为未来扩展的参考资料，**不** 在本次 DCR 实现范围。

## 1. 什么是无模式写入

无模式写入（Schemaless Writing）= 用户不预定义表结构，直接把 InfluxDB Line / OpenTSDB Telnet / OpenTSDB JSON 三种格式的数据通过 HTTP POST 给 KaiwuDB，服务器自动：

1. 按协议解析得到 **表名 / 标签列 / 数据列 / 数据值 / 类型**。
2. 生成对应 SQL。
3. 执行 `INSERT`。表不存在就自动 `CREATE TABLE`，列/标签缺失就 `ALTER TABLE ... ADD COLUMN / ADD TAG`，VARCHAR 宽度不足自动补齐。

写入范围与边界：

| 维度 | 行为 |
|------|------|
| 表名 | 大小写敏感，支持数字 / 特殊符号开头。解析时用双引号包裹 |
| 列名 / 标签名 | 大小写敏感，支持数字 / 特殊符号开头，解析时用双引号包裹 |
| 自动建表 | 目标表不存在时自动创建 |
| 自动扩列 | 表存在但列 / 标签缺失 → `ALTER TABLE ADD COLUMN / ADD TAG` |
| VARCHAR 扩宽 | 输入值宽度 > 当前列宽 → 自动 `ALTER TABLE` 调宽 |
| 类型不匹配 | 输入类型与已存在列类型不一致 → 服务端报错（不会隐式转型） |
| 默认时序表类型 | 普通时序表。稀疏时序表需先建表，无模式写入不创建稀疏表 |
| 主标签 | 服务端自动新增 `primary_tag VARCHAR(64) NOT NULL` 列作主标签，并生成主标签值 |

## 2. 三种协议格式总览

| 协议 | Content-Type | Body 形式 | 一行示例 | DCR 阶段 |
|------|--------------|-----------|----------|----------|
| **InfluxDB Line** | `text/plain` | 单行 / 多行 Line Protocol | `meters,location=Beijing current=17.01,voltage=220,phase=0.29` | **P0** |
| OpenTSDB Telnet | `text/plain` | 单行 / 多行 Telnet put | `meters.current 1648432611250 11.3 location=California.LosAngeles groupid=3` | P1+ |
| OpenTSDB JSON | `text/plain` | JSON 数组（单行也必须包成数组） | `[{ "metric": "sys.cpu.usage", "timestamp": 1654567205, "value": 0.5, "tags": {"host":"server1","dc":"1"} }]` | P1+ |

## 3. 端点清单

URL 格式：`https://<hostname>:<port>/<endpoint>?[tz=<timezone>][db=<db_name>]`

- `hostname`：KaiwuDB 节点 IP / FQDN。
- `port`：HTTP 服务端口，默认 `8080`。
- `tz`：可选。优先用请求时区，否则回退到集群参数 `server.restful_service.default_request_timezone`。
- `db`：可选。目标时序库。省略时落到 `defaultdb`。库名解析时双引号包裹。
- HTTPS：默认所有请求走 HTTPS；并发连接数 ≤ 150。**insecure 模式** 见 §6.3。

| 接口 | 用途 | Method | Endpoint | DCR 阶段 |
|------|------|--------|----------|----------|
| Login | 获取认证令牌 | `GET` | `/restapi/login` | **P0** |
| **InfluxDB** | **无模式写入 InfluxDB Line** | `POST` | `/restapi/influxdb` | **P0** |
| DDL | DDL 语句执行 | `POST` | `/restapi/ddl` | 背景 |
| Insert | 标准 `INSERT`（EMQX 兼容） | `POST` | `/restapi/insert` | 背景 |
| Query | `SELECT` / `SHOW CREATE TABLE` / `SHOW` | `POST` | `/restapi/query` | **P0（round-trip 校验）** |
| Telegraf | InfluxDB Line（表必须提前建好） | `POST` | `/restapi/telegraf` | P1+ |
| OpenTSDB JSON | 无模式写入 OpenTSDB JSON | `POST` | `/restapi/opentsdbjson` | P1+ |
| OpenTSDB Telnet | 无模式写入 OpenTSDB Telnet | `POST` | `/restapi/opentsdbtelnet` | P1+ |
| Session | 会话查看 / 删除 | `GET` / `DELETE` | `/restapi/session` | 背景 |

## 4. 端点的请求/响应（P0：InfluxDB）

### 4.1 P0 — InfluxDB `POST /restapi/influxdb`

请求头：

| Header | Value |
|--------|-------|
| `Content-Type` | `text/plain` |
| `Accept` | `application/json` |
| `Authorization` | `Basic <token>` |

请求体（一行或多行 InfluxDB Line，**db 通过 query string `?db=<db_name>` 指定，不写 body**）：

```
myMeasurement,tag1=value1,tag2=value2 fieldKey="fieldValue" 1556813561098
```

成功响应（HTTP 200）：

```json
{ "code": 0, "desc": null, "rows": 1, "time": 0.002 }
```

失败响应（HTTP 401 等）：

```json
{ "code": -1, "desc": "Incorrect authentication token", "rows": null, "time": null }
```

### 4.2 P0 — Query（round-trip 校验）`POST /restapi/query`

DCR 范围：在写入 ThreadGroup 跑完后用 Query 接口拉数据做断言（spec §6.1）。

请求体（`SELECT` / `SHOW` / `SHOW CREATE TABLE`，**支持多条语句用 `;` 分隔**）：

```
select * from myMeasurement;
```

成功响应：

```json
{
  "code": 0, "desc": null, "time": 0.022829285,
  "column_meta": [["ts","TIMESTAMP",8],["id","VARCHAR",128],["electricity","FLOAT",8]],
  "data": [["2023-07-30T06:44:40.32Z","198352498",0.31]],
  "rows": 1
}
```

`column_meta` 项格式：`[column_name, column_type, type_length]`，`type_length` 单位字节。Query 响应体上限 **5 MB**，超出截断。

---

### 4.3 P1+ — OpenTSDB JSON `POST /restapi/opentsdbjson`

> 不在 P0 范围，保留作为未来扩展参考。

请求体（JSON 数组。单行也必须包成数组）：

```json
[
  { "metric": "sys.cpu.usage", "timestamp": 1654567205, "value": 0.5,
    "tags": { "host": "server1", "dc": "1" } }
]
```

成功响应：

```json
{ "code": 0, "desc": "success;success;", "time": 0.088146837, "rows": 1 }
```

### 4.4 P1+ — OpenTSDB Telnet `POST /restapi/opentsdbtelnet`

> 不在 P0 范围，保留作为未来扩展参考。

请求体（空格分隔的单行 put）：

```
meters.current 1648432611250 11.3 location=California.LosAngeles groupid=3 extraTag=value
```

成功响应：

```json
{ "code": 0, "desc": "success;", "time": 1.279927072, "rows": 1 }
```

## 5. P0 协议格式：InfluxDB Line

### 5.1 报文结构

```
<measurement>,<tag_set> <field_set> <timestamp>
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `measurement` | 是 | 时序表名。`measurement` 与 `tag_set` 之间用英文逗号 `,` 分隔 |
| `tag_set` | 否 | 格式 `tag_key=tag_value,tag_key=tag_value,...`。多个标签之间用 `,`。`tag_set` 与 `field_set` 之间用**半角空格** |
| `field_set` | 是 | 格式 `field_key=field_value,field_key=field_value,...`。`field_set` 与 `timestamp` 之间用**半角空格** |
| `timestamp` | 否 | Unix 时间戳。支持毫秒 / 微秒 / 纳秒，**默认纳秒**。省略则取服务端主机 UTC 系统时间 |

### 5.2 类型映射（InfluxDB → KaiwuDB）

| InfluxDB 字面量 | 识别规则 | KaiwuDB |
|-----------------|----------|---------|
| Float | 含 `.` 或科学计数 | FLOAT8 |
| Integer | 仅数字，无 `.` | INT8 |
| UInteger | 仅数字，无 `.` | INT8 |
| String | 双引号包裹 `"..."` | VARCHAR |
| Boolean | `t`/`T`/`true`/`TRUE`/`f`/`F`/`false`/`FALSE` | BOOL |
| Unix timestamp（数字） | 服务端推断 | TIMESTAMPTZ |

> **陷阱**：`123` 与 `123i`（InfluxDB 原义 Integer 后缀）都映射到 INT8，但写入「已是 INT8 列」时再发 `12.3` 会触发类型不匹配错误；写「已是 VARCHAR 列」时若原值未带双引号会被当作数字字面量 → **写入 VARCHAR 必须加双引号**。

### 5.3 服务端自动建表演示

输入：`meters,location=Beijing current=17.01,voltage=220,phase=0.29`

服务端生成 SQL：

```sql
CREATE TABLE meters (
    k_timestamp TIMESTAMPTZ NOT NULL,
    current FLOAT8, voltage FLOAT8, phase FLOAT8
) TAGS (primary_tag VARCHAR(64) NOT NULL, location VARCHAR)
  PRIMARY TAGS (primary_tag);

INSERT INTO meters VALUES (NOW(), 17.01, 220, 0.29,
    'c15cf362f37e0acc7ecc2db55ec1cc57fc9579ccba9e72c273abb140f568472d', 'Beijing');
```

`SELECT * FROM meters` 实际数据：

```
          k_timestamp           | current | voltage | phase |              primary_tag              | location
--------------------------------+---------+---------+-------+--------------------------------------+----------
  2024-10-08 07:16:30.404+00:00 |   17.01 |     220 |  0.29 | c15cf362f37e0acc7ecc2db55ec1cc57... | Beijing
(1 row)
```

### 5.4 P1+ 协议格式（参考资料，不实现）

#### OpenTSDB Telnet

```
<metric> <timestamp> <value> <tag1> <tag2> ...
```

> 所有参数之间使用空格分隔。`metric` 与 `tag` 取值**避免使用空格**。

类型映射要点：**所有标签列无论原值类型统一转 VARCHAR**，并按实际插入长度自动调宽。

#### OpenTSDB JSON

```json
[
  { "metric": "sys.cpu.nice", "timestamp": 1346846400, "value": 18,
    "tags": { "host": "web01", "dc": "1" } }
]
```

类型映射要点：标签**保留数值类型**（Integer/Float → FLOAT8），不做全 VARCHAR 化。其他类型（如 bool）输入则报错。

## 6. 认证与传输（P0）

### 6.1 认证方式：Token 认证（**P0 唯一**）

1. **Setup ThreadGroup** 调用 `GET /restapi/login` 一次拿 token。
2. 后续每个 ThreadGroup 的 `POST /restapi/influxdb` 在 `Authorization: Basic <token>` 头里携带该 token。
3. token 通过 JMeter 共享变量（例如 `${__P(rest_token)}`）在 TG 之间共享。

请求：

```
GET /restapi/login HTTP/1.1
Host: localhost:8080
Content-Type: plain/text
Accept: application/json
Authorization: dTE6a3dkYnBhc3N3b3Jk
```

响应：

```json
{ "code": 0, "token": "cm9vdDprd2RicGFzc3dvcmQ=" }
```

约束：

- 每次登录或使用令牌操作后，**系统自动更新令牌起始时间，重新计算到期时间**。
- 默认有效期 60 分钟，可用 `SET CLUSTER SETTING server.rest.timeout=<value>` 调整，范围 `[1, 2^63-1]` 分钟。
- 并发编程时每个线程分配独立 token；**并发上限 100**。SetupTG 一次性登录 1 次即可拿到 1 个 token，但写线程很多时**复用同一 token** 会触发「多线程共享令牌」的并发约束 —— DCR 需确认是否在 SetupTG 批量登录 N 个 token 写入池化变量。

> Basic Auth（每次请求用 `base64(user:password)`）和「每次都登录拿新 token」**都不在 P0 范围**。P0 仅走一次性 SetupTG 登录 + 共享。

### 6.2 Login 接口细节

请求：

| 项 | 值 |
|----|----|
| Method | `GET` |
| Endpoint | `/restapi/login?tz="timezone"`（`tz` 可选） |
| 请求头 | `Content-Type: text/plain`、`Accept: application/json`、`Authorization: Basic base64(user:password)` |
| 请求体 | 空 |

> Login 不支持 `db` 参数。

响应字段：`code`（0 成功 / -1 失败）、`token`（成功时返回）、`desc`（失败时返回错误描述）。

### 6.3 HTTPS 模式：insecure / TLS（**P0 配置项**）

由 `test_cfg.yaml` 顶层新增配置项 `rest_https_mode` 切换：

| 配置值 | 含义 | JMeter HTTP Request 实现 | curl 对照 |
|--------|------|--------------------------|-----------|
| `insecure` | HTTP 明文，**不**启用 TLS，跳过证书校验 | `Protocol: http`、端口 `-Jrest_http_port=8080`（明文端口）、不留 `HTTPSampler.customizedSslContext` | `curl http://host:8080/...` |
| `tls` | HTTPS + CA 证书校验 | `Protocol: https`、端口 `-Jrest_https_port=8080`（HTTPS 端口）、`HTTPSampler.customizedSslContext` 指向 CA 证书文件 | `curl --cacert ca.crt https://host:8080/...` |

> **注意**：KaiwuDB 默认 HTTP 服务端口 `8080` 同时支持 HTTP 与 HTTPS；insecure 模式下也应使用同一端口（HTTP 模式走明文），不要换端口。

**`test_cfg.yaml` 新增配置项**（示例）：

```yaml
# KaiwuDB RESTful API 连接配置（无模式写入 P0）
rest_api:
  https_mode: insecure        # insecure | tls
  ca_cert_path: null          # 仅 https_mode=tls 时必填；指向 PEM 格式 CA 证书
  http_port: 8080             # insecure 与 tls 共用端口；KaiwuDB 同端口双协议
  login_user: root            # 用于 SetupTG 登录的用户名
  login_password: ""          # 用于 SetupTG 登录的密码（默认 root 无密码）
  login_url_path: /restapi/login
  ddl_url_path: /restapi/ddl  # SetupTG 用于预建表的 DDL 接口
  write_url_path: /restapi/influxdb
  query_url_path: /restapi/query
  default_db: defaultdb       # 写入 ?db=<db_name> 默认值
  timezone: null              # 可选，传给 ?tz=<timezone>
  pre_create_tables: true     # 是否走 DDL SetupTG 预建表（见 §9.1）
```

**JMeter HTTP Request sampler 关键属性映射**：

| `test_cfg.yaml` | JMeter 属性 |
|-----------------|-------------|
| `rest_api.https_mode` | `HTTPSampler.protocol`（`http` 或 `https`） |
| `rest_api.http_port` | `HTTPSampler.port` |
| `rest_api.ca_cert_path` | `HTTPSampler.customizedSslContext` 与 `JMeterproperty: ssl.keystore.file`（仅 `tls` 模式） |
| `rest_api.login_url_path` | SetupTG Login sampler 的 `HTTPSampler.path` |
| `rest_api.ddl_url_path` | SetupTG DDL pre-create sampler 的 `HTTPSampler.path` |
| `rest_api.write_url_path` | 写入 TG 的 `HTTPSampler.path`（`/restapi/influxdb?db=${default_db}`） |
| `rest_api.query_url_path` | Query round-trip TG 的 `HTTPSampler.path` |
| `rest_api.ca_cert_path` 不存在但 `https_mode=tls` | 生成器**主动报错**（fail-fast，SetupTG 启动前） |

### 6.4 服务端证书

- KaiwuDB 服务端证书默认路径 `/etc/kaiwudb/certs`。
- 客户端将 `ca.crt` 拷到 JMeter 发起请求的机器上，通过 `rest_api.ca_cert_path` 引用。

## 7. 通用响应 schema

| 端点 | 成功响应字段 | 失败响应字段 |
|------|--------------|--------------|
| Login | `code`, `token` | `code`, `desc` |
| **InfluxDB（写入）** | `code`, `desc`, `rows`, `time` | 同上 |
| **Query** | `code`, `desc`, `time`, `column_meta`, `data`, `rows` | 同上 |
| DDL | `code`, `desc`(string[]), `time` | `code`, `desc`(string[]) |
| Insert | `code`, `desc`(string[]), `rows`, `notice`, `time` | 同上 |
| Session (GET) | `code`, `tokens[]`（含 `SessionID/Username/Token/MaxLifeTime/LastLoginTime/ExpirationTime`） | `code`, `desc` |
| Session (DELETE) | `code`, `desc` | `code`, `desc` |

## 8. HTTP 状态码

| Code | 描述 |
|------|------|
| 200 | 成功 |
| 400 | 参数错误 |
| 401 | 认证失败（token 无效或过期） |
| 404 | URL 不存在 |
| 500 | 内部错误 |
| 503 | 系统资源不足 |

## 9. 与本仓库（kwjdbc-svt）的对接要点

| 现状 | P0 决策 |
|------|---------|
| `write_groups.py` 生成 JDBC `PreparedStatement INSERT`，走 SQL 路径 | P0 **新增** `rest_write_groups.py`：生成 HTTP Request sampler（`POST /restapi/influxdb`），由 mode 路由选择 JDBC sampler 或 HTTP sampler |
| `ddl_setup.py` 已有的 `generate_ddl_setup_thread_group(ddl_statements, ...)` 组装 SetupTG + JDBC DDL sampler | P0 **新增** `generate_ddl_setup_http_thread_group(ddl_statements, ...)`：**复用同一份 `ddl_statements: List[str]` 入参**（由现有 `DDLGenerator` 从 `test_model.yaml` 产出），只把 sampler 类型从 JDBC 换成 HTTP Request（`POST /restapi/ddl` + `${__property(rest_token)}` 头），SetupTG 外壳、RelInit 子树编排、`num_threads=1` 约束**全部沿用** |
| `test_model.yaml` 列定义明确、列类型明确 | **InfluxDB Line 下，列定义可选**。`val_range` 字段烘焙的字符串直接作为 field/tag 的字符串值（如 `"17.01"`），不再走 JDBC typed bind |
| `seed_data_generator` 按列类型烘焙 seed 值 | InfluxDB Line 下：tag 值**必须为字符串**（带双引号写入）；field 值保留原字面量（数字不加引号、字符串加引号）。seed 类型映射表见 §5.2 |
| `batch_prepared` 模式假设单 prepared statement + N bind | `mode: schemaless_influxdb` 时**无 batch**，每行独立 HTTP POST。`batch_size` / `batch_prepared` 等 JDBC 模式参数失效 |
| SetupTG 仅做共享内存初始化 | SetupTG **新增**双重职责：① 调用 `GET /restapi/login` 拿 token 写入 `${__property(rest_token)}`；② 当 `rest_api.pre_create_tables=true` 时遍历 `test_model.yaml` 中每个 measurement 调用 `POST /restapi/ddl` 预建表（ptag / tag / field 名必须与 InfluxDB Line tag_set / field_set 一致，见 §9.1） |
| `conn_pool_size` UDV 控制 JDBC pool | **新增** `rest_conn_pool_size` UDV 控制 JMeter HTTPClient 连接池（`httpclient4.max_total_connections`） |
| throughput UDV 控制写入 QPS | 复用现有 `write_throughput`（`ConstantThroughputTimer`），不新增 |
| 数据库连接字符串 `db_url`（JDBC URL） | **新增** `rest_api` 配置段（见 §6.3），与 `db_url` 并存；不再用 JDBC URL |
| 默认时区 | 新增 `rest_api.timezone` UDV，可选透传给 `?tz=` |

### 9.1 Setup ThreadGroup 启动流程（P0 必做）

JMeter 计划启动顺序（**`SetupTG` 必须最先跑，且 `num_threads=1`**，子步骤串行）：

1. **HTTP Request sampler（Login）**：`GET ${__P(rest_api.login_url_path)}`
   - Headers：`Content-Type: text/plain`、`Accept: application/json`、`Authorization: Basic base64(${__P(rest_api.login_user)}:${__P(rest_api.login_password)})`
2. **JSON Extractor**：解析响应体，提取 `token` 字段，写入 JMeter property：
   ```
   ${__setProperty(rest_token, ${token})}
   ```
3. **HTTP Request sampler 列表（DDL pre-create）**—— **仅当 `rest_api.pre_create_tables=true` 时执行**：
   - 每个 DDL 语句（由现有 `DDLGenerator.generate(...)` 从 `test_model.yaml` 产出，与 JDBC 路径同源）独占一个 HTTP Request sampler，sampler 体结构由新增的 `generate_ddl_setup_http_thread_group(ddl_statements, ...)` 复用 `ddl_setup.py` 的 SetupTG 外壳，只换 sampler 类型。
   - Method `POST`，Path `${__P(rest_api.ddl_url_path)}`（默认 `/restapi/ddl`）
   - Headers：`Content-Type: text/plain`、`Accept: application/json`、`Authorization: Basic ${__property(rest_token)}`
   - Body：单条 `CREATE TABLE` / `DROP TABLE IF EXISTS` SQL（DDL API 支持多条 `;` 分隔；P0 沿用现有 DDLGenerator 一语句一 sampler 的粒度，便于断言）
   - **关键约束**：DDL 中的 **ptag 列名 / tag 列名 / field 列名必须与 InfluxDB Line 的 `tag_set` key / `field_set` key 一一对应**。当 InfluxDB Line 携带的 tag key 与已建表 ptag 同名时，服务端把 tag 值写入对应 ptag 列；不会触发 `ADD TAG` 也不会生成 `primary_tag VARCHAR(64)` 黑盒主标签。例：
     ```sql
     -- SetupTG DDL pre-create（来自 DDLGenerator，measurement=meters，ptag=device_id）
     DROP TABLE IF EXISTS meters;
     CREATE TABLE meters (
         k_timestamp TIMESTAMPTZ NOT NULL,
         current FLOAT8, voltage FLOAT8, phase FLOAT8
     ) TAGS (device_id VARCHAR(64) NOT NULL)
       PRIMARY TAGS (device_id);

     -- 写入 TG 的 InfluxDB Line（tag key device_id 与 ptag 同名）
     meters,device_id=device_1 current=17.01,voltage=220,phase=0.29 1721000000000000000
     -- 服务端：device_id=device_1 写入 ptag(device_id) 列；不生成 primary_tag
     ```
4. **断言**：Login 与所有 DDL 响应 `code == 0` 且 `${rest_token}` 非空；否则标记 SetupTG 失败（fail-fast）。

> 该策略直接对应 §9.4 #1 解决：研发明确 `primary_tag` 自动 hash 是为「无 ptag 概念的用户」准备的兜底；**有 ptag 的场景应先 DDL 建表再用 InfluxDB API 写入**，让 tag 写入已知 ptag 列，业务断言可稳定基于命名列。

> token 60 分钟有效期**不在本场景测试范围**（见 §9.4 #3 解决说明）。短测 + 业务功能测试已覆盖续期。

### 9.1.1 DCR 复用现有模块清单

| 现有模块 | DCR 复用方式 | 新增/修改 |
|----------|--------------|-----------|
| `ddl_generator/generator.py` 的 `DDLGenerator.generate(...)` | 直接调用，产出 `ddl_statements: List[str]`，与 JDBC 路径完全同源 | 无改动 |
| `jmx_skeleton_generator/generators/ddl_setup.py` 的 `setup_thread_group_element(...)` 工具函数 | SetupTG XML 外壳、`num_threads=1` 等约束**直接复用** | 无改动 |
| `jmx_skeleton_generator/generators/ddl_setup.py` 的 `generate_ddl_setup_thread_group(...)` 函数签名 | 入参 `ddl_statements: List[str]` **形状不变**，新 HTTP 版只换内部 sampler 类型 | **新增** `generate_ddl_setup_http_thread_group(ddl_statements, *, name, num_threads, rest_api_config)`，函数体复用 `setup_thread_group_element` + 替换 `jdbc_sampler_element` 为新增的 `http_request_sampler_element` |
| `utils/xml_helpers.py` 的 `jdbc_sampler_element(...)` | — | **新增** `http_request_sampler_element(method, path, headers, body, ssl_context)`，供 HTTP 版 SetupTG / 写入 TG / Query round-trip TG 共用 |
| `kwjdbc_svt/main.py` 的 mode 路由 | mode 切 JDBC / HTTP | **新增** `mode: schemaless_influxdb` 分支，调 DDLGenerator + `generate_ddl_setup_http_thread_group` + 新增的 `rest_write_groups.py` |

### 9.2 写入 ThreadGroup 模板（P0）

每个写入 TG 内的 HTTP Request sampler：

| 属性 | 值 |
|------|-----|
| Protocol | `${__P(rest_api.protocol)}`（`http` 或 `https`，由 `https_mode` 决定） |
| Server | `${__P(hostname)}`（从 `db_url` 解析 IP） |
| Port | `${__P(rest_api.http_port)}` |
| Method | `POST` |
| Path | `${__P(rest_api.write_url_path)}?db=${__P(rest_api.default_db)}${__P(rest_api.timezone,?tz=)}` |
| Headers | `Content-Type: text/plain`、`Accept: application/json`、`Authorization: Basic ${__property(rest_token)}` |
| Body | InfluxDB Line（由 `seed_data_generator` 烘焙） |
| customizedSslContext | 仅 `https_mode=tls` 时填 `${__P(rest_api.ca_cert_path)}` |

### 9.3 P0 DCR 候选 fixture 用例

默认 `pre_create_tables=true`：SetupTG 先用 `POST /restapi/ddl` 建好与 `test_model.yaml` 同构的表，再走 `POST /restapi/influxdb` 写入（tag key 与 ptag 同名 → 业务列可断言）。

- **行 #1**（insecure + DDL 预建）：单 measurement、双 tag 与 ptag 对齐（device_id + location）、三 field → 验 DDL 建表 + InfluxDB 写入业务 ptag/device_id 列、非 NULL 断言可命中具体列。
- **行 #2**（insecure + DDL 预建）：先发 measurement=A、再发 measurement=B（两者均在 SetupTG 预建） → 验证多 measurement 并行填行 + Query `column_meta` 列名稳定。
- **行 #3**（insecure + DDL 预建）：第二次写带新增 field（如 DDL 未列、InfluxDB Line 多写一列）→ 验证服务端 `ALTER TABLE ADD COLUMN` 自动扩列 + 自动调宽 VARCHAR。
- **行 #4**（insecure + DDL 预建）：类型不匹配（VARCHAR 列写 Float 字面量）→ 服务端报错，HTTP 200 但 `code=-1`，断言落 `desc`。
- **行 #5**（insecure + DDL 预建）：空 tag_set（`meters current=17.01,...`）→ 验服务端最小请求边界。
- **行 #6**（insecure + DDL 预建）：401 token 失效（手动改 `rest_token` 为非法值）→ `code=-1, desc="Incorrect authentication token"`。
- **行 #7**（TLS + DDL 预建）：同 #1 但 `https_mode=tls`、`ca_cert_path` 指向真实证书 → HTTPS 通道建表 + 写入。
- **行 #8**（TLS + DDL 预建）：`https_mode=tls` 但 `ca_cert_path` 不存在 → 生成器 fail-fast；SetupTG 启动前报错。
- **行 #9**（insecure + TLS 切换）：同一 fixture 跑两次，第一次 `https_mode=insecure`、第二次 `tls`，对比落库行数 + ptag 值一致。
- **行 #10**（insecure + DDL 预建，`pre_create_tables=false` 对照）：**关闭** 预建，全部交给服务端 auto-create，验 `primary_tag VARCHAR(64)` 黑盒列出现、`SHOW CREATE TABLE` 含 `primary_tag`。用于复现 §9.4 #1 描述的「无 ptag 用户」场景以暴露 hash 行为。
- **行 #11**（insecure + DDL 预建 + Query round-trip）：写入完成后用 `POST /restapi/query` 拉刚写入的 measurement，按命名 ptag / field 做行数 + 列值断言。
- **行 #12**（insecure + 写后扩列）：前 N 行写入后再扩 ptag（如 fixture 元数据新增一个 tag，SetupTG 调整建表 SQL 后重跑）→ 验 `ALTER TABLE ADD TAG` 路径 + 不丢历史数据。

### 9.4 P0 边界澄清结果

| # | 原问题 | 状态 | 处理方式 |
|---|--------|------|----------|
| 1 | 服务端生成的 `primary_tag VARCHAR(64) NOT NULL` 黑盒主标签值算法 | **已解决** | 研发确认该 hash 是为「无 ptag 概念的用户业务」准备的兜底。**P0 策略：SetupTG 先用 `POST /restapi/ddl` 预建含明确 ptag 的表，再走 `POST /restapi/influxdb` 写入，InfluxDB tag key 与 ptag 列名对齐时服务端把 tag 值写入 ptag 列而非生成 primary_tag**。业务断言基于命名 ptag / field 列。`pre_create_tables=false` 作为对照 fixture 保留（见 §9.3 行 #10），用于复现无 ptag 场景以暴露服务端行为，但不参与 P0 主线断言。 |
| 2 | 自动 `ALTER TABLE ADD TAG / ADD COLUMN` 是否触发 schema change 限流 | **已解决（非问题）** | 该限流由部署服务器规格 + 实际写入负载决定，**不在本场景测试范围内**。本 DCR 的核心目标正是探究无模式写入条件下的写入性能并提出改进建议，限流被暴露反而是有价值的产物（可触发改进需求）。P0 不主动构造限流场景，但通过 §9.3 行 #3 / #12 的扩列路径，让服务端按实际写入行为自然暴露限流。 |
| 3 | token 60 分钟有效期 vs 长 test_duration 的处理策略 | **已解决（非场景测试范围）** | token 续期由**功能测试**专项覆盖（涉及 `SET CLUSTER SETTING server.rest.timeout` / 刷新机制 / 并发 token 池等）。**场景测试只模拟真实写入场景**，不需要专门验续期。P0 默认 `test_duration` 远小于 60 分钟（参考 shig canonical smoke `test_duration=60`），无续期触发风险。 |

## 10. 引用

- 无模式写入：<https://doc.kaiwudb.com/template_version/pc/doc/development/restful-api/schemaless-writing.html>
- RESTful API：<https://doc.kaiwudb.com/template_version/pc/doc/development/restful-api/connect-restful-api.html>
- InfluxDB Line Protocol：<https://docs.influxdata.com/influxdb/v2.0/reference/syntax/line-protocol/>
- OpenTSDB Telnet put（P1+ 参考）：<https://opentsdb.net/docs/build/html/api_telnet/put.html>
- OpenTSDB HTTP JSON put（P1+ 参考）：<https://opentsdb.net/docs/build/html/api_http/put.html>