# rest-schemaless-write — Proposal

## Why

当前 kwjdbc-svt 仅覆盖 JDBC 写入路径（`PreparedStatement INSERT`），无法驱动 KaiwuDB 提供的 **RESTful 无模式写入（Schemaless Writing）** 能力。`POST /restapi/influxdb` 是 KaiwuDB 在不预定义表结构的情况下接收 InfluxDB Line 数据的官方通道；为探究该通道在生产负载下的写入性能与稳定性、并把相关 SQL 落库断言纳入场景测试，必须为本仓库补一条 REST + SetupTG token + DDL 预建表的端到端写入路径。

## What Changes

- 新增 mode `schemaless_influxdb`：在 `kwjdbc_svt/main.py` mode 路由中并列 JDBC 三种写入模式；`mode=schemaless_influxdb` 时组装 HTTP Request sampler（`POST /restapi/influxdb`）替代 JDBC sampler。
- 新增 SetupTG 双职责：(1) `GET /restapi/login` 拿长效 token，写入 JMeter property `${__property(rest_token)}`；(2) 当 `rest_api.pre_create_tables=true` 时遍历 `test_model.yaml` 的每个 measurement 调用 `POST /restapi/ddl` 预建表（ptag / tag / field 名与 InfluxDB Line tag_set / field_set 一一对齐）。
- 新增 `test_cfg.yaml` `rest_api` 配置段：`https_mode: tls`（**唯一**，2026-07-27 起 insecure 移除）、`ca_cert_path`（必填）、`http_port`、`login_user/password`（非空）、`*_url_path`、`default_db`、`timezone`、`pre_create_tables`。
- 新增 `utils/xml_helpers.py::http_request_sampler_element(method, path, headers, body, ssl_context)`：通用 HTTP Request sampler XML 构造器，供 SetupTG Login / DDL pre-create / 写入 TG / Query round-trip TG 共用。
- 新增 `jmx_skeleton_generator/generators/ddl_setup.py::generate_ddl_setup_http_thread_group(ddl_statements, *, name, num_threads, rest_api_config)`：与现有 `generate_ddl_setup_thread_group(...)` 同签名同入参（`ddl_statements: List[str]` 由现有 `DDLGenerator.generate(...)` 产出），函数体复用 `setup_thread_group_element`，只把 `jdbc_sampler_element` 换成 `http_request_sampler_element`。
- 新增 `jmx_skeleton_generator/generators/rest_write_groups.py`：写入 TG 装配（HTTP POST + token 头 + InfluxDB Line body + 可选 ssl_context）。
- 新增 `jmx_skeleton_generator/generators/rest_query_groups.py`：Query round-trip TG 装配（HTTP POST `/restapi/query`）。
- **不**新增 DDL 生成代码：复用 `ddl_generator/generator.py` 的 `DDLGenerator.generate(...)` 输出与现有 `ddl_setup.py` 的 SetupTG XML 外壳，零 SQL 重写。
- **不**覆盖 OpenTSDB JSON / Telnet 协议（标 P1+）。
- **不**覆盖 Basic Auth 与 token 续期场景（标 P1+ 或归功能测试）。

## Capabilities

### New Capabilities

- `rest-schemaless-write`：覆盖 HTTP Request sampler 构造、SetupTG token + DDL pre-create 装配、写入 TG 装配、Query round-trip TG 装配、`test_cfg.yaml` `rest_api` 配置段、**TLS 唯一**（2026-07-27 起 insecure 移除）。

### Modified Capabilities

- （无。现有 JDBC 路径、`DDLGenerator`、SetupTG XML 外壳 `setup_thread_group_element(...)` 工具函数均不修改；`DDLGenerator.generate(...)` 输出对 HTTP 路径同源复用。）

## Impact

- **新增模块**：`utils/xml_helpers.py::http_request_sampler_element`、`jmx_skeleton_generator/generators/ddl_setup.py::generate_ddl_setup_http_thread_group`、`jmx_skeleton_generator/generators/rest_write_groups.py`、`jmx_skeleton_generator/generators/rest_query_groups.py`。
- **路由改动**：`kwjdbc_svt/main.py` mode 路由新增 `schemaless_influxdb` 分支。
- **配置改动**：`test_cfg.yaml` 顶层新增 `rest_api` 段；新增 UDV `${__P(rest_api.*)}` 与 `${__property(rest_token)}`。
- **依赖**：无新增 Python 依赖。JMeter 内置 HTTP Request sampler 自带，无需 JMeter Plugins。
- **复用面**：`ddl_generator/generator.py::DDLGenerator.generate(...)` 输出与 JDBC 路径 100% 同源；`jmx_skeleton_generator/generators/ddl_setup.py::setup_thread_group_element(...)` SetupTG XML 外壳、`num_threads=1` 约束、`ramp_time=1` / `duration=1` / `scheduler=True` 直接沿用。
- **验证面**：`tests/jmx_skeleton_generator/` 新增 `test_http_request_sampler_element.py`、`test_ddl_setup_http_thread_group.py`、`test_rest_write_groups.py`、`test_rest_query_groups.py`；`tests/kwjdbc_svt/` 新增 mode 路由用例。`kwjdbc-jmx-smoke` skill 跑一次端到端 smoke：SetupTG Login → DDL pre-create → 写入 TG → Query round-trip，断言落库行数 + ptag 业务列值。
- **回归风险**：低。DDLGenerator 与现有 SetupTG XML 外壳未触碰；新增 sampler 构造器与生成函数与 JDBC 路径完全独立，仅在 mode 路由上分流。