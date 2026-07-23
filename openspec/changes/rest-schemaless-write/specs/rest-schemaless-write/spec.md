# rest-schemaless-write — Spec

## ADDED Requirements

### Requirement: Setup ThreadGroup MUST 先用 DDL API 预建表再走 InfluxDB Line 写入

`mode: schemaless_influxdb` 下，Setup ThreadGroup MUST 先调用 `GET /restapi/login` 拿长效 token 并写入 `${__property(rest_token)}`；当 `rest_api.pre_create_tables=true` 时 MUST 遍历 `test_model.yaml` 每个 measurement 调用 `POST /restapi/ddl` 预建表。DDL 中的 ptag / tag / field 列名 MUST 与该 measurement 的 InfluxDB Line `tag_set` key / `field_set` key 一一对齐，使服务端把 tag 值写入已知 ptag 列而非生成 `primary_tag VARCHAR(64)` 黑盒主标签。DDL 字符串 MUST 复用现有 `ddl_generator/generator.py::DDLGenerator.generate(...)` 输出，禁止新增独立 SQL 生成路径。

#### Scenario: SetupTG Login + DDL pre-create 成功路径
- **WHEN** `mode: schemaless_influxdb` + `rest_api.pre_create_tables=true` + `test_model.yaml` 含 measurement `meters`（ptag `device_id`，fields `current` / `voltage` / `phase`）
- **THEN** SetupTG 按顺序发出 `GET /restapi/login` 与 `POST /restapi/ddl`（body 为 `DDLGenerator.generate(...)` 产出的 `CREATE TABLE meters ... TAGS (device_id VARCHAR(64) NOT NULL) PRIMARY TAGS (device_id);`），并把 `${__property(rest_token)}` 注入到 DDL sampler 的 `Authorization: Basic <token>` 头

#### Scenario: pre_create_tables=false 关闭预建
- **WHEN** `rest_api.pre_create_tables=false`
- **THEN** SetupTG MUST NOT 发出 DDL sampler，仅 Login + setProperty + assert；`primary_tag VARCHAR(64)` 黑盒主标签由服务端在首次 InfluxDB Line 写入时自动创建（用于复现无 ptag 用户场景的对照 fixture）

### Requirement: HTTP Request sampler MUST 按 https_mode 切换协议与证书

写入 TG、SetupTG Login、SetupTG DDL pre-create、Query round-trip TG 内的 HTTP Request sampler MUST 根据 `rest_api.https_mode` 切换协议与证书：`insecure` 走 `http://`，不带 `customizedSslContext`；`tls` 走 `https://`，MUST 带 `customizedSslContext` 指向 `${__P(rest_api.ca_cert_path)}`。`rest_api.https_mode=tls` 但 `ca_cert_path` 为空时，生成器 MUST 在生成阶段 fail-fast，不允许生成残缺 JMX。

#### Scenario: insecure 模式正确组装 HTTP sampler
- **WHEN** `rest_api.https_mode=insecure`
- **THEN** 生成的 HTTP Request sampler `protocol=http`、`port=${__P(rest_api.http_port)}`、不含 `HTTPSampler.customizedSslContext` 元素

#### Scenario: TLS 模式正确组装 HTTP sampler
- **WHEN** `rest_api.https_mode=tls` + `rest_api.ca_cert_path=/path/to/ca.crt`
- **THEN** 生成的 HTTP Request sampler `protocol=https`、`port=${__P(rest_api.http_port)}`、`HTTPSampler.customizedSslContext` 指向 `ca.crt`

#### Scenario: TLS 模式缺 ca_cert_path MUST fail-fast
- **WHEN** `rest_api.https_mode=tls` + `rest_api.ca_cert_path` 为 `null` 或空字符串
- **THEN** 生成器在 JMX 输出前抛出 `DdlGenerationError` 或新增的 `RestConfigError`，不生成任何 JMX 文件

### Requirement: 写入 TG MUST 按 InfluxDB Line Protocol 序列化 body

写入 TG 的 HTTP Request sampler body MUST 是 InfluxDB Line 协议单行或多行格式：`<measurement>,<tag_set> <field_set> <timestamp>`，由 `seed_data_generator` 烘焙。`Authorization` 头 MUST 携带 `${__property(rest_token)}`。Query 参数 `?db=${rest_api.default_db}` 与可选 `?tz=${rest_api.timezone}` MUST 出现在 Path 上。

#### Scenario: 写入 sampler 序列化与 Path 正确
- **WHEN** `measurement=meters` + tag `device_id` 与 DDL 中 ptag 同名
- **THEN** sampler body 形如 `meters,device_id=device_1 current=17.01,voltage=220,phase=0.29 1721000000000000000`；Path 形如 `/restapi/influxdb?db=defaultdb`

### Requirement: Query round-trip TG MUST 用命名列断言业务字段

Query round-trip TG 在写入 TG 跑完后调用 `POST /restapi/query`，MUST 按命名 ptag / field 列做行数与列值断言；禁止对 `primary_tag VARCHAR(64)` 黑盒列做值断言（`pre_create_tables=true` 时该列不存在；`pre_create_tables=false` 时其值为服务端 hash 算法生成，不可预测）。

#### Scenario: Query 断言仅落在命名业务列
- **WHEN** 写入完成后调 `POST /restapi/query` body `select count(*) from meters;`
- **THEN** 断言落 `rows` 字段，且不读取 `primary_tag` 列

### Requirement: test_cfg.yaml MUST 含 rest_api 配置段

`test_cfg.yaml` MUST 含 `rest_api` 配置段，覆盖：协议、端口、CA 证书路径、登录凭证、各 endpoint 路径、目标库、时区、是否预建表。生成器 MUST 校验 `rest_api` 段存在且字段类型正确，缺失时 fail-fast。

#### Scenario: rest_api 配置段缺失 MUST fail-fast
- **WHEN** `test_cfg.yaml` 顶层无 `rest_api` 段但 `mode: schemaless_influxdb`
- **THEN** 生成器在 main 入口抛出 `RestConfigError`，不生成 JMX

### Requirement: kwjdbc_svt main mode 路由 MUST 支持 schemaless_influxdb

`kwjdbc_svt/main.py` mode 路由 MUST 支持 `mode: schemaless_influxdb`，与 `mode: batch_prepared` / `single_insert` / `single_prepared` / `schemaless`（按原 spec §7 主动报错）并列；该 mode MUST 调 `DDLGenerator.generate(...)` + `generate_ddl_setup_http_thread_group(...)` + 新增 `rest_write_groups.py` + `rest_query_groups.py`，不调 JDBC 写入路径。

#### Scenario: schemaless_influxdb 模式路由正确
- **WHEN** fixture `mode: schemaless_influxdb`
- **THEN** 生成器输出 JMX 含 (1) SetupTG with Login + DDL pre-create HTTP samplers，(2) 至少一个写入 TG with HTTP POST `/restapi/influxdb` sampler，(3) Query round-trip TG with HTTP POST `/restapi/query` sampler；不含任何 JDBC sampler