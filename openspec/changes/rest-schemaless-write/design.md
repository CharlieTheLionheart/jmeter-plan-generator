# rest-schemaless-write — Design

## Context

当前 `kwjdbc-svt` 仅覆盖 JDBC 写入路径（`PreparedStatement INSERT`）。KaiwuDB 官方同时提供 RESTful 无模式写入通道 `POST /restapi/influxdb`，允许以 InfluxDB Line Protocol 直接写入服务端自动建表 / 扩列 / 调宽 VARCHAR。本仓库无法对该通道做端到端场景测试，也无 SetupTG token 初始化、DDL pre-create、TLS 通道接入能力。

约束：
- KaiwuDB 服务端默认 HTTP 端口 `8080` 同时支持 HTTP 与 HTTPS（同端口双协议）。2026-07-27 行为变更：schemaless Login 强制非空密码用户，非空密码用户只能通过安全模式创建，因此 `https_mode` 仅接受 `tls`（insecure 路径移除）。
- 服务端生成的 `primary_tag VARCHAR(64)` 主标签值算法是黑盒（hash），不应进入业务断言。
- 现有 `DDLGenerator.generate(...)` 输出对 JDBC 路径已是稳定源；REST 路径**必须**复用而非重写。

## Goals / Non-Goals

**Goals：**
- 在 `kwjdbc_svt/main.py` mode 路由新增 `schemaless_influxdb` 分支；与 JDBC 三模式并列。
- SetupTG 承担 Login + DDL pre-create 双职责；token 通过 JMeter property `${__property(rest_token)}` 在 TG 间共享。
- 写入 TG 用 HTTP Request sampler 走 `POST /restapi/influxdb`；Query round-trip TG 走 `POST /restapi/query`。
- `test_cfg.yaml` 新增 `rest_api` 配置段，覆盖 `https_mode` (`tls` 唯一) / `ca_cert_path`（必填）/ `http_port` / 凭证 / 各 endpoint 路径 / `default_db` / `timezone` / `pre_create_tables`。
- 复用现有 `DDLGenerator.generate(...)` 输出与 `setup_thread_group_element(...)` XML 外壳，零 SQL 重写。

**Non-Goals：**
- 不覆盖 OpenTSDB JSON / Telnet 协议（标 P1+）。
- 不覆盖 Basic Auth 与 token 续期场景（功能测试范围）。
- 不新增 Python 第三方依赖；JMeter 内置 HTTP Request sampler 已具备所需能力。
- 不为 DDL 生成新增独立 SQL 路径。

## Decisions

### Decision 1：DDL 字符串由 `DDLGenerator.generate(...)` 产出，HTTP 路径零 SQL 重写

**选择**：直接调 `DDLGenerator.generate(test_model_config)`，把现有 `List[str]` 传给新增的 `generate_ddl_setup_http_thread_group(ddl_statements, ...)`，函数体复用 `setup_thread_group_element(...)` 外壳 + `RelInit` 子树编排（若 `pre_create_tables=true` 且存在 rel table），只把 `jdbc_sampler_element(...)` 替换为新增的 `http_request_sampler_element(...)`。

**备选**：在 `ddl_generator/` 下新增 `RestDdlGenerator` 子类，专门为 DDL API 生成简化版 DDL（去掉 `IF NOT EXISTS` 等 JDBC 驱动特定语法）。**否决**：DDL API 与 SQL DDL 语法一致；新建分支会引入两套 DDL 真源，长久分裂。

### Decision 2：`RestApiConfig.https_mode` 恒为 `tls`（2026-07-27 起 insecure 移除），`ca_cert_path` 缺省时 fail-fast

**范围说明**：本 Decision 约束**仅限 schemaless 写入路径**（`RestApiConfig` 是 schemaless 专属配置段）。JDBC 路径（`mode: batch_prepared` 等）**不受影响**，`.claude/skills/kwjdbc-jmx-smoke/SKILL.md` §1-§5 仍可走 insecure 容器跑 smoke（无 `rest_api_config` 字段）。

**选择**：`test_cfg.yaml::rest_api.https_mode` ∈ {`tls`}（insecure 不再被 Pydantic Literal 接受）。sampler `protocol=https` + `customizedSslContext` 指向 `${__P(rest_api.ca_cert_path)}`。`ca_cert_path` 缺失时生成器抛 `RestConfigError`。

**变更动机**（2026-07-27）：经与测试确认，schemaless Login 要求非空密码用户；`--insecure` 启动的容器不支持 `ALTER USER ... PASSWORD`（SQLSTATE 28P01 "setting or updating a password is not supported in insecure mode"），REST Login 始终回 `{"code":-1,"desc":"the provided username and password did not match any credentials on the server."}`。非空密码用户只能通过安全模式（`--certs-dir=<dir>` + `CREATE USER root WITH PASSWORD '<pwd>'`）创建，因此 insecure 路径无解。

**备选**：始终启用 HTTPS 证书校验，对开发环境用 `javax.net.ssl.trustStore` 系统属性绕过。**否决**：JMeter 5.6+ 通过 `HTTPSampler.customizedSslContext` 已原生支持证书配置，再叠系统属性会让 fixture 配置与 JMeter 内部状态耦合。

### Decision 3：SetupTG 双职责（Login + DDL pre-create），DDL pre-create 由 `pre_create_tables` 开关

**选择**：SetupTG 串行发出 Login HTTP Request sampler → JSON Extractor → `${__setProperty(rest_token, ${token})}` → DDL pre-create HTTP Request sampler 列表 → Response Assertion (`code==0`)。`pre_create_tables=true` 时 DDL sampler 列表由 `DDLGenerator.generate(...)` 产出；`false` 时跳过。

**备选**：用独立 ThreadGroup 跑 DDL pre-create，与 SetupTG 并列。**否决**：JMeter 中 SetupTG 与独立 TG 的启动顺序不可控；DDL pre-create 必须先于写入 TG 完成；放同一 SetupTG 保证顺序且不引入并发竞态。

### Decision 4：Query round-trip 断言仅落命名业务列，不读 `primary_tag`

**选择**：写入 TG 跑完后用 Query round-trip TG 调 `POST /restapi/query`，断言 `count(*)` 行数 + 命名 ptag / field 列值（如 `device_id` / `current`）。**禁止**对 `primary_tag VARCHAR(64)` 黑盒列做值断言（`pre_create_tables=true` 时该列不存在；`false` 时值不可预测）。

**备选**：跳过 Query round-trip，仅断言 JTL response `code==0`。**否决**：仅 `code==0` 不能区分「成功写入 1 行」与「成功写 0 行」；spec §6.1 数据落库断言要求落库数据可验证。

### Decision 5：`mode: schemaless_influxdb` 路由独立，与原 spec §7 的 `mode: schemaless` 主动报错路径并存

**选择**：`mode: schemaless` 保留为「占位模式」（按 spec §7 主动报 NotImplemented）；`mode: schemaless_influxdb` 为本 change 的真正实现。两者并列，路由分发。

**备选**：把 `mode: schemaless` 直接复用为 InfluxDB Line 模式名。**否决**：会绕过 spec §7 的「schemaless 主动报错」行为；新模式名显式区分协议，避免误用。

## Risks / Trade-offs

- **`DDLGenerator` 输出与 DDL API 兼容性**：`DDLGenerator` 当前为 JDBC 驱动设计（包含 `IF NOT EXISTS` 等 KaiwuDB 方言）。DDL API 对 SQL DDL 语法 100% 兼容；但若未来 `DDLGenerator` 输出引入 JDBC 特有语法（如 `USING INDEX`），HTTP 路径需要同步适配。**Mitigation**：在 `tests/ddl_generator/` 加一个回归测试，确保 `DDLGenerator.generate(...)` 输出对 KaiwuDB DDL API `POST /restapi/ddl` 也是合法 body。
- **token 60 分钟有效期**：`test_duration` < 60 分钟时无影响；若超过需 `SET CLUSTER SETTING server.rest.timeout` 调长。**Mitigation**：在 `docs/refs/kaiwudb-schemaless-write-reference.md` §9.4 已显式说明「token 续期不在场景测试范围，由功能测试覆盖」；P0 默认短测（参考 shig canonical smoke `test_duration=60`）。
- **`pre_create_tables=false` 时 `primary_tag` 黑盒值不可断言**：对照 fixture 仅断言 `SHOW CREATE TABLE meters` 包含 `primary_tag VARCHAR(64) NOT NULL` 列存在，不读其值。**Mitigation**：见 §9.3 行 #10 fixture 描述。
- **HTTP 连接池与 JDBC 连接池语义不同**：现有 `conn_pool_size` UDV 控制 JDBC pool；HTTP 路径新增 `rest_conn_pool_size` UDV 控制 `httpclient4.max_total_connections`。**Mitigation**：两个 UDV 独立，互不耦合；fixture 配置示例显式区分。
- **服务端自动 `ALTER TABLE ADD TAG / ADD COLUMN` 限流**：高频扩列会触发 schema change 限流；本 DCR 的核心目标就是暴露该限流。**Mitigation**：见 §9.4 #2 已解决说明 —— 限流被暴露反而是有价值的产物。
- **JMeter 5.6+ `HTTPSampler.customizedSslContext` 行为**：TLS 模式下 sampler 必须正确生成；某些 JMeter 版本对该属性的 schema 校验严格。**Mitigation**：`tests/jmx_skeleton_generator/test_http_request_sampler_element.py` 用 XSD / JMeter 加载验证生成的 JMX 可被 JMeter 解析。

## Migration Plan

无（新增能力，不替换既有 JDBC 路径）。`mode: schemaless_influxdb` 是新分支，与 `mode: batch_prepared` 等并列；现有 shig fixture 不受影响。

部署步骤：
1. 合并本 change 的所有 commit。
2. `tests/` 新增测试全部通过。
3. `kwjdbc-jmx-smoke` skill 跑一次端到端：SetupTG Login → DDL pre-create → 写入 TG → Query round-trip，断言落库行数 + ptag 业务列值。
4. 文档：`docs/refs/kaiwudb-schemaless-write-reference.md` 同步更新（如有边界澄清迭代）。

回滚：删除新增模块（`http_request_sampler_element`、`generate_ddl_setup_http_thread_group`、`rest_write_groups.py`、`rest_query_groups.py`），删除 mode 路由分支，删除测试。`DDLGenerator` 与现有 SetupTG XML 外壳**零修改**，无副作用。

## Open Questions

- 是否需要 `rest_conn_pool_size` 默认值（建议沿用 `conn_pool_size` 默认值，待 build 阶段在实现中确认）。
- DDL pre-create HTTP sampler 是否需要 Response Assertion（建议加 `code==0` 断言，已纳入 `§9.1` SetupTG 流程步骤 4；build 阶段实现时细化）。
- Query round-trip TG 是否要 `ConstantThroughputTimer`（建议与现有 query TGs 保持一致，复用 `query_throughput` UDV；待 build 阶段确认）。