# rest-schemaless-write — Tasks

## 1. 基础 HTTP sampler 构造器

- [ ] 1.1 在 `src/utils/xml_helpers.py` 新增 `http_request_sampler_element(method, path, headers, body, ssl_context=None, *, name, testname, follow_redirects=True)`；输出 JMeter `HTTPSamplerProxy` XML + 配对 `hashTree`；支持 `protocol` 由调用方在 caller 层写入 sampler properties（沿用现有 `HTTPSampler.protocol` 约定）。
- [ ] 1.2 在 `src/utils/xml_helpers.py` 或新文件 `src/utils/rest_errors.py` 新增 `RestConfigError`（继承 `ValueError`），覆盖 `https_mode=tls` 但 `ca_cert_path` 缺失、`rest_api` 配置段缺失、字段类型错误三种 fail-fast 场景。

## 2. SetupTG HTTP DDL pre-create

- [ ] 2.1 在 `src/jmx_skeleton_generator/generators/ddl_setup.py` 新增 `generate_ddl_setup_http_thread_group(ddl_statements: List[str], *, name="DDL Setup (REST)", num_threads=1, rest_api_config: Dict[str, Any])`：复用 `setup_thread_group_element(...)` 外壳 + `rel_init_specs` 编排；对每条 `ddl` 调 `http_request_sampler_element(method="POST", path="${__P(rest_api.ddl_url_path)}", headers=...+token, body=ddl, ssl_context=...)` 产出 HTTP sampler。
- [ ] 2.2 在生成的 SetupTG 串行追加 Login HTTP Request sampler + JSON Extractor（提取 `token`） + `__setProperty(rest_token, ${token})`；`pre_create_tables=true` 时再追加 DDL sampler 列表，`false` 时跳过；统一 Response Assertion（`code==0`）。
- [ ] 2.3 新增 `tests/jmx_skeleton_generator/test_ddl_setup_http_thread_group.py`：覆盖 (a) `pre_create_tables=true` 生成 Login + DDL sampler；(b) `pre_create_tables=false` 仅生成 Login；(c) `https_mode=tls` + `ca_cert_path` 缺失抛 `RestConfigError`；(d) `https_mode=insecure` 不带 `customizedSslContext`。
- [ ] 2.4 新增 `tests/utils/test_http_request_sampler_element.py`：覆盖 (a) GET/POST/PUT method；(b) header 注入；(c) `ssl_context` 路径正确写入 `HTTPSampler.customizedSslContext`；(d) `body` 注入到 `HTTPSampler.postBody`；(e) 生成的 hashTree 配对正确。

## 3. 写入 TG（HTTP POST /restapi/influxdb）

- [ ] 3.1 新增 `src/jmx_skeleton_generator/generators/rest_write_groups.py::generate_rest_write_thread_group(test_model_config, rest_api_config, *, name="REST Write", throughput_qps=None)`：每个 measurement 对应 1 个 sampler 单元（`JSR223PreProcessor` 拼 InfluxDB Line + `HTTPSamplerProxy` 发送）；Groovy PreProcessor 读 `globalProps.__SHARED_MEM_{db}_{table}` 行 + `_columns` header，按列 group 拆 ptag / tag / field → `escapeLineValue` + `formatFieldValue` + `buildLine` → `vars.put('request_body', line)`；HTTPSamplerProxy body 引用 `${request_body}`；Path 含 `?db=${rest_api.default_db}` 与可选 `?tz=${rest_api.timezone}`；Headers 含 `Authorization: Basic ${__property(rest_token)}`；沿用现有 `ConstantThroughputTimer` 控 QPS（复用 `write_throughput` UDV）。
- [ ] 3.2 新增 `tests/jmx_skeleton_generator/test_rest_write_groups.py`：覆盖 (a) 单 measurement 输出 1 个 sampler 单元（JSR223PreProcessor + HTTPSamplerProxy 一对）；(b) 多 measurement 输出 N 个 sampler 单元；(c) `tag_set` key 与 DDL ptag 对齐时 PreProcessor 拼出的 line 正确格式；(d) sampler body 为 `${request_body}` 变量引用（不是烘焙字符串）；(e) PreProcessor 内 Groovy 脚本含 `escapeLineValue` + `formatFieldValue` + `buildLine` 关键调用；(f) Path 正确拼接 `?db=` 与 `?tz=`；(g) `customizedSslContext` 仅在 `https_mode=tls` 注入。

## 4. Query round-trip TG（HTTP POST /restapi/query）

- [ ] 4.1 新增 `src/jmx_skeleton_generator/generators/rest_query_groups.py::generate_rest_query_thread_group(test_model_config, rest_api_config, *, name="REST Query Round-Trip")`：每个 measurement 调 `POST /restapi/query`（body `select count(*) from <measurement>;`）+ JSON Extractor 提取 `rows` + Response Assertion（`rows >= <expected_rows>`）。**不**读 `primary_tag` 列。
- [ ] 4.2 新增 `tests/jmx_skeleton_generator/test_rest_query_groups.py`：覆盖 (a) 每个 measurement 生成 1 个 Query sampler；(b) Path 与 `Authorization` 头正确；(c) `rows` 字段断言正确；(d) `pre_create_tables=false` 时 Query 仍可用但断言**不**读 `primary_tag`。

## 5. mode 路由 + test_cfg.yaml schema

- [ ] 5.1 在 `src/kwjdbc_svt/main.py` mode 路由新增 `mode: schemaless_influxdb` 分支：调 `DDLGenerator.generate(test_model_config)` → `generate_ddl_setup_http_thread_group(...)` → `generate_rest_write_thread_group(...)` → `generate_rest_query_thread_group(...)`；不调 JDBC 写入路径。
- [ ] 5.2 在 `test_cfg.yaml` schema 校验逻辑（`src/config_parser/`）新增 `rest_api` 段校验：必填字段（`https_mode` / `http_port` / `login_user` / `*_url_path` / `default_db` / `pre_create_tables`），`https_mode ∈ {insecure, tls}`，`ca_cert_path` 在 `tls` 时非空。
- [ ] 5.3 新增 `tests/kwjdbc_svt/test_main_routes_schemaless_influxdb.py`：覆盖 (a) `mode: schemaless_influxdb` + 合法 `rest_api` → 生成完整 JMX；(b) 缺 `rest_api` 段 → `RestConfigError`；(c) `mode: batch_prepared` + 缺 `rest_api` 段 → 不报错（向后兼容）；(d) `https_mode=tls` + 缺 `ca_cert_path` → `RestConfigError`。
- [ ] 5.4 新增 `tests/config_parser/test_rest_api_config.py`：覆盖 `rest_api` schema 各字段必填 / 类型 / enum 校验。

## 6. 端到端 fixture + smoke

- [ ] 6.1 新增 `tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml`：`mode: schemaless_influxdb`、单 measurement `meters`、ptag `device_id`、2 个 tag、3 个 field；与 shig fixture 解耦以便独立 smoke。
- [ ] 6.2 新增 `tests/kwjdbc_svt/fixtures/test_cfg_schemaless.yaml`：`rest_api.https_mode=insecure` + `pre_create_tables=true`、默认值齐全。
- [ ] 6.3 跑 `kwjdbc-jmx-smoke` skill（insecure 路径，**现有 SKILL.md 不动**）：SetupTG Login → DDL pre-create → SharedMemory → 写入 TG → Query round-trip；断言 (a) SetupTG Login/DDL `code==0`；(b) 写入 TG JTL response `code==0` 且 `rows >= 1`；(c) Query round-trip `rows >= 1`；(d) DB 内 `select count(*) from meters` 行数与 JMeter 写入一致；(e) `device_id` ptag 列非 NULL 且采样值在 `device_<start>..device_<start+num_threads*device_per_thread>` 范围内。
- [ ] 6.4 (扩展) 更新 `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` 加 `--tls` 可选 flag：
  - skill 内 Docker 容器跑 `kwbase cert create-ca` + `create-node`，生成证书到容器内 `/tmp/kaiwudb-certs/`（参考 [`docs/refs/kaiwudb-tls-cert-reference.md`](../../refs/kaiwudb-tls-cert-reference.md) §3）
  - 容器启动参数加 `--certs-dir=/tmp/kaiwudb-certs`
  - `docker cp` 把 `ca.crt` 拷到 JMeter 主机 `tests/kwjdbc_svt/fixtures/tls/ca.crt`（git 跟踪测试用 CA，与运行时生成 CA 解耦；fixture `ca_cert_path` 指向该路径）
  - skill 增加 `tests/kwjdbc_svt/fixtures/test_cfg_schemaless_tls.yaml` 选择（`https_mode: tls` + `ca_cert_path` 指向拷贝后的路径）
  - 保留 insecure 模式为默认行为（不改现有 smoke 流程；不破坏现有调用）
- [ ] 6.5 跑 `kwjdbc-jmx-smoke --tls` 一次：复用 6.3 的所有断言；额外验证 HTTPS 通道 + `device_id` ptag 列落库一致；记录 insecure vs TLS 的 QPS / latency 差到 `docs/refs/kaiwudb-schemaless-write-reference.md` §9.5（新增小节，记录实测性能基线，作为本 DCR 的产物）。

## 7. 文档与回归保护

- [ ] 7.1 更新 `docs/refs/kaiwudb-schemaless-write-reference.md`：补 §9.5 实测性能基线；补 §10 引用中新增的实现模块路径。
- [ ] 7.2 在 `docs/superpowers/specs/` 新增 `rest-schemaless-write-design.md`（Superpowers Design Doc，build 阶段 `comet-design` 产物；open 阶段不写）。
- [ ] 7.3 跑全量 `python -m pytest tests/ -q`：确保新增测试 + 现有 633 个测试全 pass（参考 `ddl-generator` change 完成态 633 passed）。
- [ ] 7.4 更新 `todolist.md`：把 schemaless-write change 完成项移到「已完成」，新增 `F-id` 记录 commit hash + pytest 行数 + smoke 验收。