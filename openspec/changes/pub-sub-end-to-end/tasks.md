# Tasks: pub-sub-end-to-end

## 0. 范围决策确认(review 阶段已闭环)

- [x] 0.1 D5 重写为单池 + FQN 跨库(per user 与 KaiwuDB 开发同事核实:发布订阅 per-cluster 不区分 db,连接池 dbUrl 指向 defaultdb)
- [x] 0.2 `subscriber_db` 字段完全硬化为 `f"{publisher_db}_sub"`(不再作为 `pub_sub_config` 字段)
- [x] 0.3 `expected_min_rows` 默认值内联 1,`expected_rows.py` 模块删除(彻底移除 throughput 公式引用,per user 反馈)
- [x] 0.4 Verify TG `PostThreadGroup delay=60s` + duration 不输出(JMeter 5.6.3 实测 schema)
- [x] 0.5 `enabled` 字段彻底删除(per user 反馈:`enabled` 是过度设计,段声明与否本身即开关)
- [x] 0.6 3 个 helper(schema 对齐实测 jmx)/ SetupTG 4 步(`;` 分隔多 SQL 合并到单 sampler)/ VerifyTG 1+N sampler 顺序

---

## TDD 范式约定

每个模块按"pytest 先行 → 编码后继 → 单元测试通过 → 继续下一模块"节奏推进:

- pytest 子 task:`tests/<path>/<name>.py` 含失败断言(子 task 验收时跑 `pytest tests/<path>/<name>.py` 全绿)
- 编码子 task:实现 Pydantic 模型 / 函数 / helper,代码必须让上述 pytest 全绿才能勾选
- 模块切换:**当前模块 pytest 全绿**才推进下一模块

集成测试拆分为两个 phase:
- **Phase A:.jmx 生成层集成测试** — `python -m kwjdbc_svt.main` 生成 .jmx + `xml.etree.ElementTree.parse()` 解析校验结构,**不需要真实 KaiwuDB cluster**(本地 pytest 跑通)
- **Phase B:本地容器冒烟测试** — 真实启 KaiwuDB docker container + `jmeter -n` 跑端到端,**需要 cluster**(在修订 smoke skill 之后跑,本文档只列 smoke skill 修订与冒烟 invocation,**冒烟执行本身不在 pytest 里**)

---

## 1. Pydantic 模型(`PubSubConfig` + `PublicationTableEntry` + `TestConfig`)

- [x] 1.1 pytest 先写 `tests/config_parser/test_pub_sub_config.py` 含失败断言:`PubSubConfig` 7 字段 + `PublicationTableEntry` 3 字段 + `TestConfig.pub_sub_config: Optional[PubSubConfig] = None`;`@field_validator` / `@model_validator(mode="after")` 校验规则:
  - `conninfo` `startswith("postgresql://")` + non-empty
  - `tables` 多表时 `columns` / `where` 强制空
  - `tables[i].name` ∈ `test_model.ts_dbs[*].tables[*].name`
  - `columns` ⊆ `primary_tags + regular_tags + data_cols` 且包含所有 `primary_tag`
  - `options.target` 必填 + non-empty
  - `expected_min_rows >= 0`(允许 None)
  - `len(tables) > 1` 时 columns/where 强制空
  - `publisher_db` ∈ `test_model.ts_dbs[*].name`
- [x] 1.2 实现 `src/config_parser/models.py::PubSubConfig` + `PublicationTableEntry` + `TestConfig.pub_sub_config: Optional[PubSubConfig] = None` 字段
- [x] 1.3 实现 `PubSubConfig` / `PublicationTableEntry` 的 `@field_validator` + `@model_validator(mode="after")` 校验规则
- [x] 1.4 **验收**:跑 `pytest tests/config_parser/test_pub_sub_config.py` 全绿

## 2. xml_helpers.py 3 helper(`teardown_thread_group_element` / `regex_extractor_element` / `jsr223_assertion_element`)

- [ ] 2.1 pytest 先写 `tests/utils/test_xml_helpers.py::test_teardown_thread_group_element_*` 含失败断言:testclass="PostThreadGroup" / guiclass="PostThreadGroupGui" / **不**输出 `<longProp name="ThreadGroup.duration">` / `delay=60` / `num_threads=1` / `ramp_time=1` / `LoopController.loops=1`
- [ ] 2.2 pytest 先写 `tests/utils/test_xml_helpers.py::test_regex_extractor_element_*` 含失败断言:字段顺序 + 实测 schema(`useHeaders` / `refname` / `regex` / `template` / `default` / `default_empty_value` / `match_number`)
- [ ] 2.3 pytest 先写 `tests/utils/test_xml_helpers.py::test_jsr223_assertion_element_*` 含失败断言:字段顺序 + 实测 schema(`cacheKey=true` / `filename` / `parameters` / `script` / `scriptLanguage=groovy`;字段名 `script` **而非** `assertion_script`)
- [ ] 2.4 实现 `src/utils/xml_helpers.py::teardown_thread_group_element(name, *, num_threads=1, ramp_time=1, delay=60, loops=1, ...)` 元素渲染(不输出 `<longProp name="ThreadGroup.duration">` / 不输出 `<stringProp name="ThreadGroup.duration">`)
- [ ] 2.5 实现 `src/utils/xml_helpers.py::regex_extractor_element(ref_name, regex, template, match_number, default="")` 元素渲染
- [ ] 2.6 实现 `src/utils/xml_helpers.py::jsr223_assertion_element(script, script_language="groovy")` 元素渲染
- [ ] 2.7 **验收**:跑 `pytest tests/utils/test_xml_helpers.py` 全绿

## 3. src/pub_sub/ 子包 — TDD 节奏

> **模块推进顺序**:`build_publication_sql` → `build_subscribe_dest_schemas` → `build_create_subscription_sql` → `_build_show_subscription_status_sampler` / `_build_count_sampler` → `append_pub_sub_to_setup_tg` → `generate_pub_sub_verify_tg`。每个模块单元 UT 通过后才进入下一模块。

### 3.1 `build_publication_sql(publication_name, publisher_db, tables, options=None)`

- [ ] 3.1.1 pytest 先写 `tests/pub_sub/test_publication_sql.py` 6 种 SQL 形态断言(整库 / 单表 / 单表+列子集 / 单表+WHERE / 单表+列子集+WHERE / 多表)+ `WITH OPTIONS` 拼接规则(无 options 不追加 / 有 options 含 publication-side keys 才追加 / 12 形态插入顺序保留)
- [ ] 3.1.2 实现 `src/pub_sub/publication_sql.py::build_publication_sql(...)`
- [ ] 3.1.3 **验收**:跑 `pytest tests/pub_sub/test_publication_sql.py` 全绿
- [ ] 3.1.4 *commit*:该模块完成后再继续 §3.2

### 3.2 `build_subscribe_dest_schemas(publisher_ddls, publisher_db)`

- [ ] 3.2.1 pytest 先写 `tests/pub_sub/test_subscribe_dest_schemas.py::test_build_subscribe_dest_schemas_*` 含失败断言:`CREATE TS DATABASE <pub_db>` → `'CREATE TS DATABASE <pub_db>_sub'` 字符串精确替换 + `<pub_db>.` → `<pub_db>_sub.` via `\b` word boundary regex(含 `iot_monitor_other.t` 不被误匹配反例);`sub_db` 内部硬约定 = `f"{publisher_db}_sub"`
- [ ] 3.2.2 实现 `src/pub_sub/subscribe_dest_schemas.py::build_subscribe_dest_schemas(...)`(内部派生 `sub_db`)
- [ ] 3.2.3 **验收**:跑 `pytest tests/pub_sub/test_subscribe_dest_schemas.py::test_build_subscribe_dest_schemas_*` 全绿
- [ ] 3.2.4 *commit*:该模块完成后再继续 §3.3

### 3.3 `build_create_subscription_sql(subscription_name, publication_name, conninfo, options=None)`

- [ ] 3.3.1 pytest 先写 `tests/pub_sub/test_subscribe_dest_schemas.py::test_build_create_subscription_sql_*` 含失败断言:`CREATE SUBSCRIPTION <name> CONNECTION '<conninfo>' PUBLICATION <pub_name>` 基础拼接 + `WITH OPTIONS (k1 = v1, k2 = v2)` 拼接(无 options 不追加 / 有 options 追加 + 顺序保留);`options=None` / `options={}` 时**不**追加 WITH OPTIONS(防御性支持,per scope note)
- [ ] 3.3.2 实现 `src/pub_sub/subscribe_dest_schemas.py::build_create_subscription_sql(...)`
- [ ] 3.3.3 **验收**:跑 `pytest tests/pub_sub/test_subscribe_dest_schemas.py::test_build_create_subscription_sql_*` 全绿
- [ ] 3.3.4 *commit*:该模块完成后再继续 §3.4

### 3.4 `_build_show_subscription_status_sampler` + `_build_count_sampler`(helper,依赖 §2 helper)

- [ ] 3.4.1 pytest 先写 `tests/pub_sub/test_pub_sub_verify_tg.py::test__build_show_subscription_status_sampler` + `test__build_count_sampler` 含失败断言(`jdbc_sampler_element` + `regex_extractor_element` + `jsr223_assertion_element` 子节点结构 + variable_names + f-string script 内容)
- [ ] 3.4.2 实现 `_build_show_subscription_status_sampler(subscription_name, subscriber_db)` + `_build_count_sampler(publisher_db, table_name, subscriber_db, expected_min_rows)`(放 `pub_sub_verify_tg.py` 内)
- [ ] 3.4.3 **验收**:跑 `pytest tests/pub_sub/test_pub_sub_verify_tg.py::test__build_*` 全绿
- [ ] 3.4.4 *commit*

### 3.5 `append_pub_sub_to_setup_tg(setup_tg_element, pub_sub_config, test_model_config)`

- [ ] 3.5.1 pytest 先写 `tests/pub_sub/test_pub_sub_setup_tg.py` 含失败断言:`DDLGenerator.generate(test_model_config)` 内部调用 + `sub_db = f"{pub_sub_config.publisher_db}_sub"` 派生 + 4 个 JDBC Sampler 顺序与命名(per §3.5.2)+ `; '.join(subscribe_dest_schemas)` 合并到 `CreateSubscriberDDL` 单 sampler + sub_options caller 过滤契约(`SUBSCRIPTION_OPTION_KEYS = frozenset({"target", "enable", "ignore_history", "retry"})`)
- [ ] 3.5.2 实现 `src/pub_sub/pub_sub_setup_tg.py::append_pub_sub_to_setup_tg(...)`(4 步顺序:CreatePublication → CreateTSDatabaseSubscriber → CreateSubscriberDDL(`; '.join`)→ CreateSubscription)
- [ ] 3.5.3 **验收**:跑 `pytest tests/pub_sub/test_pub_sub_setup_tg.py` 全绿
- [ ] 3.5.4 *commit*

### 3.6 `generate_pub_sub_verify_tg(pub_sub_config, test_model_config)`

- [ ] 3.6.1 pytest 先写 `tests/pub_sub/test_pub_sub_verify_tg.py::test_generate_pub_sub_verify_tg` 含失败断言:`sub_db = f"{pub_sub_config.publisher_db}_sub"` 派生 + PostThreadGroup delay=60s 无 duration + 1 个 SHOW SUBSCRIPTION status sampler + N 个 count sampler(每张 ts_table 一条)+ `expected_min_rows` 内联(`pub_sub_config.expected_min_rows if pub_sub_config.expected_min_rows is not None else 1`)+ 每 sampler `database` 字段不写(单池 + FQN 跨库)
- [ ] 3.6.2 实现 `src/pub_sub/pub_sub_verify_tg.py::generate_pub_sub_verify_tg(...)`(调用 §3.4 helper)
- [ ] 3.6.3 **验收**:跑 `pytest tests/pub_sub/test_pub_sub_verify_tg.py` 全绿
- [ ] 3.6.4 *commit*

### 3.7 `__init__.py` 导出

- [ ] 3.7.1 pytest 先写 `tests/pub_sub/test___init__.py` 验证 5 个公开 API 可导入:`build_publication_sql` / `build_subscribe_dest_schemas` / `build_create_subscription_sql` / `append_pub_sub_to_setup_tg` / `generate_pub_sub_verify_tg`
- [ ] 3.7.2 实现 `src/pub_sub/__init__.py` 从 5 个内部模块导入
- [ ] 3.7.3 **验收**:跑 `pytest tests/pub_sub/test___init__.py` 全绿

## 4. fixture 文件(2 个)

- [ ] 4.1 pytest 先写 `tests/kwjdbc_svt/fixtures/test_cfg_pub_sub.yaml`(publisher_db="iot_monitor" / publication_name="pub_iot" / conninfo="postgresql://root@localhost:26257/iot_monitor?sslmode=disable" / options 含 target + enable / tables=null 整库模式 / expected_min_rows 未设)— 验证:`config_parser.parse_test_cfg_yaml(...)` 解析无 `ValidationError`,`pub_sub_config` 字段被加载为 `PubSubConfig` 实例
- [ ] 4.2 pytest 先写 `tests/kwjdbc_svt/fixtures/test_cfg_pub_sub_tables.yaml`(tables=[{name: t_cnc, columns: [k_timestamp, device_id, col_float8_1], where: "col_float8_1 > 0"}] / options 含 target + ignore_history + retry / expected_min_rows=0)— 验证同上
- [ ] 4.3 实现 2 个 fixture yaml 文件 + 解析断言测试
- [ ] 4.4 **验收**:跑 `pytest tests/config_parser/test_fixture_yaml_parse.py`(或类似) 全绿

## 5. 集成到 test_plan.py — Phase A: .jmx 生成层集成测试

> **不需要真实 KaiwuDB cluster**,本地 pytest 跑通

- [ ] 5.1 pytest 先写 `tests/jmx_skeleton_generator/test_ddl_setup_pubsub_append.py` 含失败断言:不声明 `pub_sub_config` 段 → SetupTG / VerifyTG 不追加(空 hashTree);声明 `pub_sub_config` 段 → SetupTG 末尾 4 个 sampler + VerifyTG `PostThreadGroup` + 3 sampler;XML 结构可通过 `xml.etree.ElementTree.parse()` 解析
- [ ] 5.2 实现 `src/jmx_skeleton_generator/generators/test_plan.py` 在 `generate_ddl_setup_thread_group(...)` 之后追加 `pub_sub_setup_tg.append_pub_sub_to_setup_tg(setup_tg, pub_sub_config, test_model_config)`(当 `test_config.pub_sub_config` 非 None)
- [ ] 5.3 同文件在主 TG 之后追加 `pub_sub_verify_tg.generate_pub_sub_verify_tg(pub_sub_config, test_model_config)`(当 `test_config.pub_sub_config` 非 None)
- [ ] 5.4 实现 helper 让 `TestConfig` 解析时把 `test_model_config` 透传到 `JMXSkeletonGenerator.generate(test_model_config, test_config)` 调用(若当前尚未透传)
- [ ] 5.5 **验收**:跑 `pytest tests/jmx_skeleton_generator/test_ddl_setup_pubsub_append.py` 全绿
- [ ] 5.6 *commit*:Phase A 集成测试通过后再继续 §6

## 6. reference 文档(直接落地,无测试)

- [ ] 6.1 `docs/refs/kaiwudb-pubsub-references.md` 新建,包含:CREATE PUBLICATION / CREATE SUBSCRIPTION 语法 + 同步周期 + 端到端延迟 + 2-5s 连接窗口 + insecure / TLS conninfo 示例 + `options` key 集合分两组 + `SHOW SUBSCRIPTION` / `CREATE SUBSCRIPTION` per-cluster + conninfo 与 `${db_url}` 一致性 + 数据库清理归属(由流水线负责)
- [ ] 6.2 `test_cfg.yaml::pub_sub_config` 字段 → 生成 DDL / JMX 元素映射表覆盖:`publisher_db` / `publication_name` / `subscription_name` / `conninfo` / `tables` / `expected_min_rows` + `subscriber_db = <publisher_db>_sub` 派生规则
- [ ] 6.3 `tables` 校验规则段:multi-table 不可 columns/where;columns 必须含所有 primary_tags + NOT NULL data_cols;where 字符串 parse 时不语法校验

## 7. smoke skill 修订(发布订阅相关补充说明)

> **在本地容器冒烟测试之前**完成

- [ ] 7.1 `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` §7 新增 `pub_sub smoke` 章节:不需 TLS 容器准备(`?sslmode=disable` insecure 容器即可,per proposal.md 备注)
- [ ] 7.2 §7 给出两次端到端 invocation templates:(a) `test_cfg_pub_sub.yaml`(整库模式 + 默认阈值);(b) `test_cfg_pub_sub_tables.yaml`(表级 + 列子集 + WHERE + `expected_min_rows=0` 恒真)— 完整 `jmeter -n -t test_plan.jmx -J...` 命令行
- [ ] 7.3 §7 断言 checklist 匹配 SetupTG / Write TG / Verify TG lifecycle(SetupTG 全部 `code==0` / Write TG JTL 100% 成功 / Verify TG `count(*) >= threshold` / SHOW SUBSCRIPTION `status` 含 `running`);note 当 publication 用 WHERE 过滤时 `expected_min_rows` 必须设 0(走恒真)
- [ ] 7.4 §7 troubleshooting 段:`<publisher_db>_sub` 已存在 from prior run / conninfo sslmode mismatch / `count(*)=0` likely causes / WHERE clause rejected by server at CREATE PUBLICATION execution time
- [ ] 7.5 §7 显式声明 database cleanup 责任由流水线负责(`DROP SUBSCRIPTION` / `DROP PUBLICATION` / `DROP DATABASE` 推荐 operator-side cleanup sequence)— 与 design.md §"约束锁定" 锁定对齐
- [ ] 7.6 **章节完成判定**:`kwjdbc-jmx-smoke` skill `SKILL.md` 文档结构 + 章节逻辑在 `PATH/.claude/skills/kwjdbc-jmx-smoke/SKILL.md` 校验全绿(无 pytest,但 README / 章节标记存在)

## 8. Phase B: 本地容器冒烟测试(**§5 + §7 通过后**)

- [ ] 8.1 启动本地 KaiwuDB Docker container(insecure 容器,`?sslmode=disable`,per skill §7 修订)
- [ ] 8.2 跑 `(a) test_cfg_pub_sub.yaml` 端到端:`python -m kwjdbc_svt.main ...` 生成 .jmx + `jmeter -n -t test_plan.jmx -J...`,断言 SetupTG 全部 `code==0` + Write TG JTL 100% 成功 + Verify TG `count(*) >= 1` + SHOW SUBSCRIPTION `status` 含 `running`
- [ ] 8.3 跑 `(b) test_cfg_pub_sub_tables.yaml` 端到端:断言 SetupTG 全部 `code==0` + Write TG JTL 100% 成功 + Verify TG `count(*) >= 0`(走恒真 WHERE 过滤场景)+ SHOW SUBSCRIPTION `status` 含 `running`
- [ ] 8.4 数据库清理 operator-side 流程验证:`DROP SUBSCRIPTION` → `DROP PUBLICATION` → `DROP DATABASE` 可正常执行(归属流水线,本任务不写自动化,只记录可执行)
- [ ] 8.5 **冒烟通过**:两条 fixture 数据组合(整库 / 表级+列子集+WHERE) 端到端无失败,Verify TG row 阈值断言 / subscription status 断言 全过

---

## 验证总览

| phase | 工具 | 时机 |
|---|---|---|
| 单元测试 | pytest | 每个 §1 / §2 / §3.x / §4 编码子 task 完成后立即 |
| **Phase A:.jmx 生成集成测试** | pytest(`tests/jmx_skeleton_generator/test_ddl_setup_pubsub_append.py`) | §5 全部子 task 完成 |
| **Phase B:本地容器冒烟** | `kwjdbc-jmx-smoke` skill §7 修订后,真实启 KaiwuDB docker container | §7 修订完成 + §5 全绿 |

回归:每模块单元测试全绿 → commit → 推下一模块。`enabled` / `throughput` 公式 / `JDBC Request.database` / `Variable Name of Pool` 等已否决概念不在本 tasks.md 任何 task 中出现(per user 全局 memory 规则 `feedback-no-removed-feature-meta-comments`)。