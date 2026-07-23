---
change: rest-schemaless-write
design-doc: docs/superpowers/specs/2026-07-23-rest-schemaless-write-design.md
base-ref: db7a9f841343da1ea28ed5fc6c646e98f294dcd0
---

# 实施计划 — rest-schemaless-write

## 目标

在 OpenSpec change `rest-schemaless-write` 范围内，实现 KaiwuDB RESTful 无模式写入 P0（InfluxDB Line + Token 认证 + SetupTG DDL pre-create + insecure / TLS 双模式），并在 `kwjdbc-svt` 仓库内端到端 smoke 通过。

## 文件结构

**新增**（4 工件）：

| 文件 | 职责 |
|------|------|
| `src/utils/xml_helpers.py::http_request_sampler_element` | 通用 HTTP Request sampler XML 构造（4 个 TG 共用底座） |
| `src/utils/rest_errors.py::RestConfigError` | 配置段缺失 / TLS 缺证书 / 字段非法 三种 fail-fast 异常 |
| `src/jmx_skeleton_generator/generators/ddl_setup.py::generate_ddl_setup_http_thread_group` | SetupTG HTTP DDL pre-create 装配（含 Login + token + DDL sampler） |
| `src/jmx_skeleton_generator/generators/rest_write_groups.py::generate_rest_write_thread_group` | 写入 TG 装配（JSR223PreProcessor 拼 line + HTTPSamplerProxy 发送） |
| `src/jmx_skeleton_generator/generators/rest_query_groups.py::generate_rest_query_thread_group` | Query round-trip TG 装配 |

**修改**（1 工件）：

| 文件 | 改动 |
|------|------|
| `src/kwjdbc_svt/main.py` | mode 路由新增 `schemaless_influxdb` 分支；调用 4 个新增生成器 |

**复用，零改动**：

- `src/ddl_generator/generator.py::DDLGenerator.generate(...)` — DDL 字符串源
- `src/utils/xml_helpers.py::setup_thread_group_element(...)` — SetupTG XML 外壳
- `src/utils/xml_helpers.py::jdbc_sampler_element(...)` — JDBC sampler 底座（不触碰）
- `src/seed_data_generator/orchestrator.py::_generate_table_seeds` — seed CSV 烘焙
- `src/jmx_skeleton_generator/generators/shared_memory_setup.py::generate_shared_memory_setup_thread_group` — SharedMemory SetupTG
- `src/shared_memory_initializer/` — JSR223 PreProcessor 读 CSV 写 props

## 全局约束

- **零改动原则**：`DDLGenerator` / `setup_thread_group_element` / `jdbc_sampler_element` / `seed_data_generator` / `shared_memory_setup.py` / `SharedMemoryInitializerGenerator` **不动一行**。所有复用只通过现有签名调用。
- **Smoke skill 行为不变**：现有 `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` 默认 insecure 路径**不修改**；TLS 路径作为新增可选 flag（任务 6.4）。
- **SetupTG 顺序**：Login → DDL pre-create → SharedMemory（显式锁定，见 Design Doc §3.2）。
- **Token 共享**：SetupTG Login 1 次拿 1 token，`${__property(rest_token)}` 在 TG 间共享；不池化。
- **DDL fail-fast**：任一 DDL sampler `code != 0` → SetupTG 整体失败，写入 TG 不启动。
- **Query round-trip 不读 `primary_tag`**：`pre_create_tables=true` 时该列不存在；`false` 时黑盒值不可断言。
- **HTTPS 双模式**：`https_mode: insecure` 走 http://+无证书；`tls` 走 https://+`ca_cert_path` 必填；缺失 → `RestConfigError`。

## 任务

### 1. 基础 HTTP sampler 构造器 + RestConfigError（tasks §1）

**文件**：修改 `src/utils/xml_helpers.py`；新建 `src/utils/rest_errors.py`。

- 1.1 在 `src/utils/rest_errors.py` 新增 `RestConfigError(ValueError)`，定义 message 模板覆盖三种 fail-fast 场景。
- 1.2 在 `src/utils/xml_helpers.py` 新增 `http_request_sampler_element(method, path, headers, body, ssl_context=None, *, name, testname, follow_redirects=True)` 返回 `(HTTPSamplerProxy Element, hashTree)`：
  - `HTTPSampler.method` / `path` / `protocol=${__P(rest_api.protocol)}` / `port=${__P(rest_api.http_port)}` / `follow_redirects=auto` / `postBodyRaw=true`（body 非空时）
  - HeaderManager 子 hashTree；`ssl_context` 非空时设 `HTTPSampler.customizedSslContext=${ssl_context}` 与 `JMeterproperty: ssl.keystore.file=${ssl_context}`
  - body 注入 `<![CDATA[${body}]]>` 到 `Arguments` 子树
- 1.3 新增 `tests/utils/test_http_request_sampler_element.py`：覆盖 (a) GET/POST/PUT 切换；(b) HeaderManager 节点；(c) `ssl_context` 写入两属性；(d) `ssl_context=None` 不产出 ssl 节点；(e) `body="${request_body}"` 字面量保留（JMeter 运行时展开）；(f) `(sampler, hashTree)` 配对正确。
- 1.4 新增 `tests/utils/test_rest_errors.py`：三种 fail-fast 触发场景的 message 验证。

### 2. SetupTG HTTP DDL pre-create（tasks §2）

**文件**：修改 `src/jmx_skeleton_generator/generators/ddl_setup.py`。

- 2.1 新增 `generate_ddl_setup_http_thread_group(ddl_statements, *, name="DDL Setup (REST)", num_threads=1, rel_init_specs=None, rest_api_config)` 返回 `[SetupThreadGroup, hashTree]`：
  - 复用 `setup_thread_group_element(name, num_threads=1, ramp_time=1, duration=1, delay=0, loops=1, scheduler=True, children=[...])` 外壳
  - Step A：生成 Login HTTPSamplerProxy（`GET ${rest_api_config[login_url_path]}` + `Authorization: Basic base64(login_user:login_password)`）
  - Step B：生成 JSON Extractor（`$.token` → `${token}`）+ JSR223 PostProcessor（`${__setProperty(rest_token, ${token})}`）
  - Step C：`pre_create_tables=true` 时遍历 `ddl_statements`，每条生成 DDL HTTPSamplerProxy（`POST ${rest_api_config[ddl_url_path]}` + `Authorization: Basic ${__property(rest_token)}` + body=该 SQL）；每 sampler 配 JSR223 Assertion 断言 `responseBody.code == 0`
  - **不**触碰现有 `generate_ddl_setup_thread_group(...)`
- 2.2 新增 `tests/jmx_skeleton_generator/test_ddl_setup_http_thread_group.py`：
  - `test_pre_create_true_emits_login_plus_ddl_samplers`
  - `test_pre_create_false_emits_login_only`
  - `test_tls_missing_ca_cert_raises_rest_config_error`
  - `test_insecure_no_customized_ssl_context`
  - `test_multiple_ddl_statements_emit_n_ddl_samplers`
  - `test_rel_init_specs_pass_through_unchanged`

### 3. 写入 TG（Groovy 拼 InfluxDB Line + HTTPSamplerProxy）（tasks §3）

**文件**：新建 `src/jmx_skeleton_generator/generators/rest_write_groups.py`。

- 3.1 新增 `generate_rest_write_thread_group(test_model_config, rest_api_config, *, name="REST Write", throughput_qps=None)` 返回 `[ThreadGroup, hashTree]`：
  - 对每个 measurement 生成 1 个 sampler 单元（`JSR223PreProcessor` + `HTTPSamplerProxy`）
  - 复用 `ConstantThroughputTimer` + `write_throughput` UDV
  - Path：`${rest_api.write_url_path}?db=${rest_api.default_db}` + 当 `timezone` 非空时追加 `&tz=${timezone}`
  - Header：`Content-Type: text/plain`、`Accept: application/json`、`Authorization: Basic ${__property(rest_token)}`
  - HTTPSamplerProxy body 为 `${request_body}` 字面量（Groovy PreProcessor 运行时填 `vars.put('request_body', line)`）
- 3.2 Groovy PreProcessor 模板（参考 Design Doc §4.7）：
  ```groovy
  def tableName = "<db>.<measurement>"   // 生成器按 measurement 注入
  def ptagNames = [...]  // primary_tags 列名（first ptag 用于 device_<n> 注入）
  def tagNames  = [...]  // regular_tags 列名
  def fieldNames = [...] // data_cols 列名

  def rowsKey = "__SHARED_MEM_" + tableName.replace('.', '_')
  def rows = globalProps.get(rowsKey) as ArrayList
  def columnNames = globalProps.get(rowsKey + "_columns") as ArrayList
  if (rows == null || rows.isEmpty()) throw new IllegalStateException("empty shared rows")

  def threadCount = ctx.getThreadGroup().getNumThreads()
  int rowIdx = (ctx.getThreadNum() + iteration * threadCount) % rows.size()
  def row = rows[rowIdx]
  def deviceStart = Long.parseLong(vars.get("device_start") ?: "1")
  def devicePerThread = Integer.parseInt(vars.get("device_per_thread") ?: "1")

  def ts = System.nanoTime()
  def measurement = tableName.substring(tableName.indexOf('.') + 1)
  def sb = new StringBuilder()
  sb.append(measurement)
  if (ptagNames && ptagNames.size() > 0) {
      sb.append(',').append(ptagNames[0]).append('=device_').append(deviceStart + (rowIdx % devicePerThread))
  }
  ptagNames.drop(1).each { name ->
      int csvIdx = columnNames.indexOf(name); if (csvIdx < 0) return
      def raw = row.get(csvIdx)?.toString() ?: ""
      sb.append(',').append(name).append('=').append(escapeLineValue(raw))
  }
  tagNames.each { name ->
      int csvIdx = columnNames.indexOf(name); if (csvIdx < 0) return
      def raw = row.get(csvIdx)?.toString() ?: ""
      sb.append(',').append(name).append('=').append(escapeLineValue(raw))
  }
  sb.append(' ')
  fieldNames.each { name ->
      int csvIdx = columnNames.indexOf(name); if (csvIdx < 0) return
      def raw = row.get(csvIdx)?.toString() ?: ""
      sb.append(name).append('=').append(formatFieldValue(name, raw)).append(',')
  }
  if (sb.charAt(sb.length() - 1) == ',') sb.deleteCharAt(sb.length() - 1)
  sb.append(' ').append(ts)
  vars.put("request_body", sb.toString())

  String escapeLineValue(String s) {
      if (s == null) return ""
      return s.replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=").replace("\n", "\\n")
  }
  String formatFieldValue(String fieldName, String raw) {
      if (raw == null || raw.isEmpty()) return "\"\""
      if (raw ==~ /^-?\d+$/) return raw
      if (raw ==~ /^-?\d+\.\d+$/) return raw
      if (raw == "true" || raw == "false") return raw
      return "\"" + raw.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
  }
  ```
- 3.3 新增 `tests/jmx_skeleton_generator/test_rest_write_groups.py`：
  - `test_single_measurement_emits_one_unit`（JSR223PreProcessor + HTTPSamplerProxy 一对）
  - `test_multi_measurement_emits_n_units`
  - `test_body_is_request_body_variable_reference`（验证 sampler body 为 `${request_body}` 字面量）
  - `test_groovy_script_contains_required_helpers`（验证 PreProcessor 内含 `escapeLineValue` / `formatFieldValue` / `device_`）
  - `test_path_contains_db_and_optional_tz`
  - `test_tls_injects_customized_ssl_context`
  - `test_insecure_omits_customized_ssl_context`
- 3.4 新增 `tests/jmx_skeleton_generator/test_groovy_influxdb_line_template.py`（Python 镜像实现，**不**依赖 groovy CLI）：
  - `test_escape_space`
  - `test_escape_comma`
  - `test_escape_equal`
  - `test_escape_newline`
  - `test_escape_quote`
  - `test_escape_backslash`
  - `test_format_int_no_quote`
  - `test_format_float_no_quote`
  - `test_format_bool_no_quote`
  - `test_format_string_quoted`
  - `test_build_line_complete_with_first_ptag_device_injection`
  - `test_build_line_without_ptag`
  - Python 镜像实现需与 Groovy 行为对齐（regex / replace 顺序 / null vs '' 处理）

### 4. Query round-trip TG（tasks §4）

**文件**：新建 `src/jmx_skeleton_generator/generators/rest_query_groups.py`。

- 4.1 新增 `generate_rest_query_thread_group(test_model_config, rest_api_config, *, name="REST Query Round-Trip")` 返回 `[ThreadGroup, hashTree]`：
  - 每个 measurement 1 个 HTTPSamplerProxy：`POST ${rest_api.query_url_path}` + body `select count(*) from <measurement>;`
  - JSON Extractor：`responseBody.rows` → `${rows}`（JSONPath `$.rows`）
  - Response Assertion：`${rows} >= <expected_rows>`
  - 复用 `ConstantThroughputTimer` + `query_throughput` UDV
  - **不**读 `primary_tag`
- 4.2 新增 `tests/jmx_skeleton_generator/test_rest_query_groups.py`：
  - `test_each_measurement_one_query_sampler`
  - `test_authorization_header_correct`
  - `test_json_extractor_path_$.rows`
  - `test_response_assertion_threshold`
  - `test_assertion_does_not_read_primary_tag`

### 5. mode 路由 + test_cfg.yaml schema（tasks §5）

**文件**：修改 `src/kwjdbc_svt/main.py` + `src/config_parser/`。

- 5.1 在 `src/kwjdbc_svt/main.py` mode 路由新增分支（在 `schemaless` 占位报错之后）：
  ```python
  elif mode == "schemaless_influxdb":
      from ddl_generator.generator import DDLGenerator
      from jmx_skeleton_generator.generators.ddl_setup import generate_ddl_setup_http_thread_group
      from jmx_skeleton_generator.generators.rest_write_groups import generate_rest_write_thread_group
      from jmx_skeleton_generator.generators.rest_query_groups import generate_rest_query_thread_group
      from jmx_skeleton_generator.generators.shared_memory_setup import generate_shared_memory_setup_thread_group

      ddl_gen = DDLGenerator(test_model_config, test_cfg)
      ddl_statements = ddl_gen.generate()
      seed_csv_paths = _resolve_seed_csv_paths(test_model_config, output_dir)  # 从 seed_data_generator 输出解析

      setup_tg = generate_ddl_setup_http_thread_group(ddl_statements, rest_api_config=rest_api_config)
      shared_mem_tg = generate_shared_memory_setup_thread_group(seed_csv_paths)
      write_tg = generate_rest_write_thread_group(test_model_config, rest_api_config)
      query_tg = generate_rest_query_thread_group(test_model_config, rest_api_config)
      elements.extend([*setup_tg, *shared_mem_tg, *write_tg, *query_tg])
  ```
- 5.2 在 `src/config_parser/` 新增 `RestApiConfig` dataclass + 校验规则：
  - `https_mode ∈ {insecure, tls}`；`tls` 时 `ca_cert_path` 非空；`mode != schemaless_influxdb` 时 `rest_api` 段静默忽略
- 5.3 新增 `tests/config_parser/test_rest_api_config.py`：覆盖 schema 各字段必填 / 类型 / enum
- 5.4 新增 `tests/kwjdbc_svt/test_main_routes_schemaless_influxdb.py`：
  - `test_schemaless_influxdb_with_valid_rest_api_emits_complete_jmx`
  - `test_missing_rest_api_raises_rest_config_error`
  - `test_batch_prepared_without_rest_api_does_not_error`（向后兼容）
  - `test_schemaless_influxdb_with_tls_missing_ca_cert_raises_error`
  - `test_schemaless_influxdb_output_contains_no_jdbc_samplers`
  - `test_existing_schemaless_mode_still_raises_not_implemented`

### 6. 端到端 fixture + smoke skill 扩展（tasks §6）

**文件**：新建 fixture + 修改 `.claude/skills/kwjdbc-jmx-smoke/SKILL.md`。

- 6.1 新增 `tests/kwjdbc_svt/fixtures/test_model_schemaless.yaml`：`mode: schemaless_influxdb`、单 measurement `meters`、ptag `device_id`、2 tag、3 field。
- 6.2 新增 `tests/kwjdbc_svt/fixtures/test_cfg_schemaless.yaml`：`rest_api.https_mode=insecure` + `pre_create_tables=true`、默认值齐全。
- 6.3 跑 `kwjdbc-jmx-smoke` skill（insecure 默认，**现有 SKILL.md 不动**）：
  - SetupTG Login `code==0` + `${rest_token}` 非空
  - SetupTG DDL pre-create 全部 `code==0`
  - SharedMemory SetupTG 加载完成
  - 写入 TG JTL `code==0` + `rows >= 1`；第一条 sample `requestBody` 符合 InfluxDB Line + `device_id=device_<n>` ptag 注入正确
  - Query round-trip TG `rows >= 1`
  - DB `select count(*) from meters` 行数与 JMeter 写入一致
  - `device_id` ptag 列非 NULL + 采样值在 `device_<start>..device_<start+num_threads*device_per_thread>` 范围
- 6.4 扩展 `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` 加 `--tls` flag：
  - 容器内跑 `kwbase cert create-ca` + `create-node` 生成证书到 `/tmp/kaiwudb-certs/`（参考 `docs/refs/kaiwudb-tls-cert-reference.md` §3）
  - 容器启动参数加 `--certs-dir=/tmp/kaiwudb-certs`
  - `docker cp` ca.crt 到 JMeter 主机 `tests/kwjdbc_svt/fixtures/tls/ca.crt`
  - 增加 `tests/kwjdbc_svt/fixtures/test_cfg_schemaless_tls.yaml`（`https_mode: tls` + `ca_cert_path` 指向拷贝后的路径）
  - insecure 路径**不修改**，现有调用兼容
- 6.5 跑 `kwjdbc-jmx-smoke --tls`：复用 6.3 全部断言；额外验证 HTTPS 通道；记录 insecure vs TLS QPS / latency 差到 `docs/refs/kaiwudb-schemaless-write-reference.md` §9.5。

### 7. 文档 + 回归保护 + build → verify 推进（tasks §7）

- 7.1 全量 `python -m pytest tests/ -q` 通过（参考 `ddl-generator` change 完成态 633 passed）。
- 7.2 跑一次 shig canonical smoke（验证 JDBC 路径不受 schemaless_influxdb mode 路由分流影响）。
- 7.3 勾选 `tasks.md` 全部任务；按 commit-per-task 风格逐个 commit（参考 `ddl-generator` change commit 历史）。
- 7.4 更新 `docs/refs/kaiwudb-schemaless-write-reference.md` §9.5 实测性能基线；§10 引用加新增实现模块路径。
- 7.5 更新 `todolist.md`：把 `rest-schemaless-write` change 完成项移到「已完成」，新增 `F-id` 记录 commit hash + pytest 行数 + smoke 验收。
- 7.6 跑 `comet-guard rest-schemaless-write build --apply` 推进到 verify。

## 风险

- **Groovy 镜像实现 drift**：`test_groovy_influxdb_line_template.py` 的 Python 镜像与 Groovy 行为可能不一致（regex / replace 顺序 / null 处理）。Mitigation：smoke 端到端跑通 + DB 落库一致时二次校准。
- **JMeter 5.6+ `HTTPSampler.customizedSslContext` schema 严格**：TLS sampler 可能被 JMeter 拒绝加载。Mitigation：smoke 跑两次（insecure + tls）；TLS 失败时直接 JMeter GUI 加载 JMX 看错。
- **token 60 分钟过期**：smoke 默认 `test_duration=10` 远小于 60 分钟，无影响；若 build 阶段引入更长测试需评估。
- **`pre_create_tables=false` 时 `primary_tag` 不可断言**：对照 fixture 仅断言 `SHOW CREATE TABLE` 包含 `primary_tag` 列存在，不读值（spec §9.3 行 #10）。
- **DDL pre-create 重复跑同 fixture 表已存在**：fail-fast；smoke 前手动 `DROP DATABASE`。
- **JMeter `JMeterProperties` 单例 vs JSR223 `props`**：跨 SetupTG 持久靠单例；build 阶段不踩坑。
- **smoke skill 改 `--tls` 破坏现有 insecure 流程**：保留 insecure 为默认；`--tls` 为可选 flag；现有调用方式不变。

## 验收清单

- [ ] 全部新增测试文件（5 个）通过：`test_http_request_sampler_element.py`、`test_rest_errors.py`、`test_ddl_setup_http_thread_group.py`、`test_rest_write_groups.py`、`test_groovy_influxdb_line_template.py`、`test_rest_query_groups.py`、`test_rest_api_config.py`、`test_main_routes_schemaless_influxdb.py`
- [ ] 全量 `python -m pytest tests/ -q` 通过（≥ 现有 633 + 新增 ≈ 50 用例）
- [ ] `kwjdbc-jmx-smoke` insecure 跑通：0 err；SetupTG Login/DDL `code==0`；写入 `code==0` + `rows >= 1`；Query `rows >= 1`；DB `count(*)` 与 JMeter 写入一致；`device_id` ptag 列非 NULL
- [ ] `kwjdbc-jmx-smoke --tls` 跑通：HTTPS 通道 + ca.crt 校验通过；DB 落库数据与 insecure 路径一致
- [ ] shig canonical smoke 跑通：回归保护 JDBC 路径
- [ ] `docs/refs/kaiwudb-schemaless-write-reference.md` §9.5 记录两次 smoke 的 QPS / latency
- [ ] `todolist.md` 更新完成项
- [ ] `comet-guard rest-schemaless-write build --apply` 全 PASS，phase=verify

## 引用

- Design Doc：`docs/superpowers/specs/2026-07-23-rest-schemaless-write-design.md`
- Tasks：`openspec/changes/rest-schemaless-write/tasks.md`
- 上游 delta spec：`openspec/changes/rest-schemaless-write/specs/rest-schemaless-write/spec.md`
- Brainstorm：`openspec/changes/rest-schemaless-write/.comet/handoff/brainstorm-summary.md`
- 参考：
  - `docs/refs/kaiwudb-schemaless-write-reference.md` §6 / §9.4
  - `docs/refs/kaiwudb-tls-cert-reference.md` §3 / §5
  - `docs/refs/jmeter-testplan-reference.md`（HTTPSampler 属性）
- 现有参考实现（不改）：`src/jmx_skeleton_generator/generators/write_groups.py`（JDBC 路径 Groovy PreProcessor 模板）
- 现有 commit 风格：`docs/superpowers/specs/2026-07-22-conditional-relational-setup-design.md` 关联的 commits（参考 commit-per-task 风格）