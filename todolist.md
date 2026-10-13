# pub-sub-end-to-end DCR 推进状态(2026-10-10 → 2026-10-12)

**变更目录**:`openspec/changes/pub-sub-end-to-end/`

**产物**(4 件):
- `openspec/changes/pub-sub-end-to-end/proposal.md`
- `openspec/changes/pub-sub-end-to-end/design.md`
- `openspec/changes/pub-sub-end-to-end/specs/pub-sub-end-to-end/spec.md`
- `openspec/changes/pub-sub-end-to-end/tasks.md`(TDD 范式 8 章编码 plan + §0 已闭环 review 决策)

**当前阶段**:设计文档 review 完成(2026-10-12),即将进入编码阶段

## 新会话切入指南

- **从 `tasks.md` §1.1 开始**(第一个子 task:`tests/config_parser/test_pub_sub_config.py` 含失败断言)
- **环境命令**(新会话第一步执行):
  ```bash
  cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
  source .venv/bin/activate  # 项目规则 AGENTS.md §5
  pip install -e ".[dev]"     # 首次进 worktree 必须
  ```
- **pytest 模板**:`tasks.md` 每个子 task 验收条件是"pytest 全绿",具体命令:
  ```bash
  python -m pytest tests/config_parser/test_pub_sub_config.py   # §1
  python -m pytest tests/utils/test_xml_helpers.py              # §2
  python -m pytest tests/pub_sub/test_publication_sql.py         # §3.1
  python -m pytest tests/pub_sub/test_subscribe_dest_schemas.py  # §3.2 / §3.3
  python -m pytest tests/pub_sub/test_pub_sub_verify_tg.py       # §3.4 / §3.6
  python -m pytest tests/pub_sub/test_pub_sub_setup_tg.py        # §3.5
  python -m pytest tests/pub_sub/test___init__.py                # §3.7
  python -m pytest tests/jmx_skeleton_generator/test_ddl_setup_pubsub_append.py  # §5 (Phase A)
  ```
- **smoke 模板**(§8 Phase B,需真实 KaiwuDB docker container;**不**在 pytest 里跑,触发 `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` §7):
  ```bash
  docker compose up -d kaiwudb  # insecure 容器, ?sslmode=disable
  python -m kwjdbc_svt.main -o output/a fixtures/test_model.yaml fixtures/test_cfg_pub_sub.yaml
  jmeter -n -t output/a/test_plan.jmx -Jdb_url=jdbc:kaiwudb://localhost:26257/defaultdb -Jdb_username=root -Jdb_password=
  ```
- **TDD 节奏**(tasks.md 顶部):pytest 先于编码,验收跑 pytest 全绿 → commit → 推下一模块。模块切换需前模块 pytest 全绿
- **commit / push 节奏**(每子 task / 每次模块通过):sub task 验收通过 → `git add <新/改文件>` → `git commit -m "..."` (commit message 不引用 `enabled` / throughput 公式 / `<JDBC Request.database>` 等已否决概念,per memory `feedback-no-removed-feature-meta-comments`) → `git push origin feat/pub-sub`
- **代码引用**: `PubSubConfig` 字段定义见 `design.md` §`pub_sub_config` 字段清单;helper schema 见 `docs/refs/jmx-components-references.md` §PostThreadGroup / §RegexExtractor / §JSR223Assertion;SetupTG 4 步 / VerifyTG 1+N sampler 顺序见 `design.md` §`pub_sub_setup_tg.py` / §`pub_sub_verify_tg.py`
- **不要做**的事(per 全局 memory `feedback-no-removed-feature-meta-comments`):不要再提 `enabled` / throughput 公式 / `<JDBC Request.database>` 字段 / Variable Name of Pool 等已否决概念
- **CLAUDE.md / AGENTS.md 项目规则**:venv / pytest / smoke skill / commit 规则都在项目指南里,新会话进入时会自动加载

**已完成项**:
- F-001 Decision 3 简化:`expected_min_rows` 显式覆盖字段,未设时 Verify TG 内联取 `1` 兜底;彻底移除 throughput 公式引用,保留 write_config 字段示例(无公式)
- F-002 `expected_rows.py` 模块删除:`expected_min_rows` 默认值内联到 `generate_pub_sub_verify_tg` 函数体,无独立模块
- F-003 Verify TG signature 简化:`generate_pub_sub_verify_tg(pub_sub_config, test_model_config)` 移除 `write_config_by_table` + `conn_config_test_duration` 参数;内联 row count 公式不再依赖
- F-004 `subscriber_db` 字段完全硬化:从 `pub_sub_config` 字段删除;生成器内部硬约定 `sub_db = f"{publisher_db}_sub"`
- F-005 D5 重写为单池 + FQN 跨库:同集群两库共享 `${db_url}`(`dbUrl` 指向 defaultdb);subscriber sampler 全部 FQN 跨库;publication / subscription metadata per-cluster;不派生 `${db_url_sub}` UDV、不新增第二条 Connection、不用 `<JDBC Request.database>` 字段(JMeter 5.6.3 实测该字段不存在)、不用 `USE` 切库
- F-006 SetupTG subscriber DDL 单 sampler 注入:KaiwuDB JDBC driver 支持 `;` 分隔多条 SQL 一次执行,合并到单 sampler 替代 N 个 sampler 循环(简化 JMX 体积)
- F-007 helper 函数 f-string `"""..."""` 风格:helper 脚本(去 `ref_name` / `count_var` 参数化,函数名固定语义)
- F-008 `build_create_subscription_sql` 增加 `options=None` 参数(支持 subscription-side WITH OPTIONS 子句)
- F-009 `caller 过滤契约`:`append_pub_sub_to_setup_tg` 在调用 `build_create_subscription_sql` 前按 SUBSCRIPTION_OPTION_KEYS 集合过滤 `pub_sub_config.options`,与 `build_publication_sql` 过滤 publication-side keys 对称
- F-010 Verify TG 属性锁定:`PostThreadGroup`(testclass="PostThreadGroup" / guiclass="PostThreadGroupGui") + `delay=60s` + `<longProp name="ThreadGroup.duration">` 不输出(JMeter 默认行为 = 跑完 sampler 列表自然结束)
- F-011 `enabled` 字段彻底删除:从 `PubSubConfig` Pydantic 模型移除;`test_cfg.yaml` 段存在 = 启用,不存在 = 不启用(段声明与否本身即开关,无 enabled 子字段);4 个 artifact(`design.md` / `proposal.md` / `spec.md` / `todolist.md`) 全部 `enabled` 字面已清理 0 处残留
- F-012 jmx-components-references.md 新增 3 段:`§PostThreadGroup`(testclass 实测 PostThreadGroup + duration 省略)+ `§RegexExtractor`(实测 refname/sample/match_number 默认值 + `|` 字面)+ `§JSR223Assertion`(实测 guiclass=`TestBeanGUI` + 字段名 `script` 而非 `assertion_script`),全部基于 user 实测 jmx 文件
- F-013 JMeter Element Schema Reference 段对齐实测 jmx:`<JDBCSampler>` schema 移除错误的 `database` 字段描述(实测 JMeter 5.6.3 无此字段);`<RegexExtractor>` / `<JSR223Assertion>` schema 字段顺序与实测一致
- F-014 落全局 memory 规则:`feedback-no-removed-feature-meta-comments` — user 反对保留"刻意隐藏 X" / "无需 X 子字段" 等元描述(此地无银三百两);被删除概念不再以任何形式回提
- F-015 `pub_sub_config` fixture yaml 示例 + 字段清单:`design.md` 新增完整段(整库模式 + 表级 + 列子集 + WHERE 模式 fixture 示例;PubSubConfig 字段清单 8 项 + PublicationTableEntry 子模型 3 项 + TestConfig 挂载位置)
- F-016 `conninfo` 来源与构造明确:`conninfo` 由 user 在 `test_cfg.yaml::pub_sub_config.conninfo` 字段显式填;generator 不派生、不用 `${db_url}` 字符串重写;libpq 格式 + TLS 双格式 + 与 `${db_url}` 用户名/密码/host/port 必须一致
- F-017 §1 Pydantic 模型 + 外部 cross-ref validator 编码完成(commit `86f70ab`):`PubSubConfig` 7 字段 + `PublicationTableEntry` 3 字段 Pydantic 模型 + `TestConfig.pub_sub_config: Optional[PubSubConfig] = None` 字段;`validate_pub_sub_refs` 外部 validator 拆出(与 `validate_foreign_key_refs` 职责完全独立,只校验 ts_table 自身属性存在性);column_namer 规则校验(`^{col|rtag|ptag}_{normalize_type(col_type)}_{int}$` shape + normalize_type 必须在声明的 col_type 集合中);ptag 联合主键规则(必须覆盖**所有**声明的 ptag col_type);35 pytest 用例(`tests/config_parser/test_pub_sub_config.py`)全绿 + 全套 678 passed 无 regression
- F-018 多段 f-string 统一改为 `f"""..."""` 多行格式(commit `86f70ab`):`PubSubConfig.check_options` / `multi_table_forbids_columns_and_where` / `validate_pub_sub_refs` 4 处错误消息;按 AGENTS.md "Surgical Changes" 原则只动 §1 新加代码,pre-existing 多段 f-string 不在范围不动
- F-019 §2 三个 pub-sub xml_helpers 落地(commit `83d1ff4`):`teardown_thread_group_element` / `regex_extractor_element` / `jsr223_assertion_element`;依据综合 `~/Downloads/JSR223 Assertion.jmx` (user 之前 JMeter GUI 手动保存的实测 jmx) + `docs/refs/jmeter-testplan-reference.md` (JMeter 官方文档副本,line 1671-1672 确认 delay + scheduler 必须配对输出) + `docs/refs/jmx-components-references.md` (§PostThreadGroup 示意);`PostThreadGroup.delay=60s + scheduler=true` 配对输出,`ThreadGroup.duration` 不输出,`enabled` 属性不输出(JMeter GUI 默认省略),helper 返回单 Element(`<PostThreadGroup>`/`<RegexExtractor>`/`<JSR223Assertion>`),paired `<hashTree>` 由 caller 端(`generate_pub_sub_verify_tg`)负责;35 个 pytest 用例全绿 + 全套 713 passed 无 regression
- F-020 §3.1 `build_publication_sql` 落地(commit `ed9c078` + `d46bcce`):6 种 SQL 形态(整库 / 单表 4 组合 / 多表) + WITH OPTIONS 拼接(无/空 dict 不追加,非空末尾追加且保留 dict 插入顺序非字母序);caller 过滤契约(F-009 `target` / `enable` 等 subscription-side keys 由 caller 端过滤)归 §3.5 测,本文件不重复;14 个 pytest 用例全绿 + 全套 730 passed 无 regression
- F-021 §3.2 `build_subscribe_dest_schemas` 落地(commit `a058da8`):两步字符串替换 per D8 — 字符串精确替换 `CREATE TS DATABASE <pub_db>` + word boundary regex `\b{re.escape(pub_db)}\.` 防 `iot_monitor_other.t` 误匹配;`sub_db = f"{publisher_db}_sub"` 内部硬约定(不作为参数,per D5);`build_create_subscription_sql` (§3.3) 留到下一轮 TDD,跟 §3.2 同文件但分开 commit;12 个 pytest 用例全绿 + 全套 742 passed 无 regression
- F-022 §3.3 `build_create_subscription_sql` 落地(commit `effb7ae`):基础形态 `CREATE SUBSCRIPTION <name> CONNECTION '<conninfo>' PUBLICATION <pub_name>`(`CONNECTION` 用单引号包裹 conninfo,per design.md line 331)+ WITH OPTIONS 拼接(无/空 dict 不追加,非空末尾追加且保留 dict 插入顺序);与 `build_publication_sql` 拼接规则对齐;`options=None / options={}` 防御性覆盖(per design.md scope note:同集群两库 caller 永远非空,这俩分支仅作多集群扩展预留,smoke 不覆盖);9 个新 pytest 用例全绿(同文件 `test_subscribe_dest_schemas.py`,与 §3.2 12 用例合跑 20 passed)+ 全套 750 passed 无 regression
- F-023 §3.4 2 个 verify TG helper 落地(commit `eb41018`):`_build_show_subscription_status_sampler` (JDBCSampler + RegexExtractor + JSR223Assertion 断言 status 含 'running') + `_build_count_sampler` (JDBCSampler query 走 FQN 跨库查 `{sub_db}.{table}` + JSR223Assertion 断言 count_1 >= expected_min_rows);`subscriber_db` / `publisher_db` 参数按 tasks.md §3.4.2 签名接收(`_build_show_subscription_status_sampler` 内部不用 subscriber_db,SHOW SUBSCRIPTION 是 per-cluster;`_build_count_sampler` 内部不用 publisher_db,query 只引用 sub_db.table);`jdbc_sampler_element` 返回 Tuple, helper 解构时忽略 paired hashTree (caller 端 §3.6 负责重新组装);26 个 pytest 用例全绿 + 全套 776 passed 无 regression
- F-024 §3.5 `append_pub_sub_to_setup_tg` 落地(commit `9f98171`):4 步顺序(per design.md line 350-353)— `CreatePublication-<name>` (build_publication_sql 委托) → `CreateSubscriberDDL` (build_subscribe_dest_schemas 输出 + `'; '.join` 合并到单 sampler,per F-006) → `CreateSubscription-<name>` (build_create_subscription_sql 委托);内部派生 `sub_db = f"{pub_db}_sub"` (D5 硬约定) + `publisher_ddls = DDLGenerator(test_model_config).generate_statements()`(design.md line 469 写 `.generate()` 返回 str 是 typo, 实际该用 `.generate_statements()`);**F-009 caller 过滤契约对称**: `PUBLICATION_OPTION_KEYS = {buffer_size, retrieve_tags, publish}` + `SUBSCRIPTION_OPTION_KEYS = {target, enable, ignore_history, retry}`;配套修改 `build_subscribe_dest_schemas` 大小写不敏感(IGNORECASE)+ 容忍可选 `if not exists` 子句(per DDLGenerator 实际输出);13 个 pytest 用例全绿 + 全套 790 passed 无 regression
- F-025 §3.6 `generate_pub_sub_verify_tg` 落地(commit `2a535ee`):编排 PostThreadGroup + 1 SHOW SUBSCRIPTION status sampler + N count sampler;收集所有 sampler 列表, 一次性作为 `children` kwarg 传给 §2 `teardown_thread_group_element`(per F 决定: aligned paired hashTree 模式, 跟 setup_thread_group_element 一致);§2 `teardown_thread_group_element` 重构 (per A 决定): 对齐 paired 模式返回 `(tg, hashTree)` Tuple + 暴露 8 个新 kwarg(duration / scheduler / enabled / on_sample_error / same_user_on_next_iteration / props / testname / children), testclass / guiclass 硬编码(per user 反馈 JMeter GUI 不能改节点类型);setup_thread_group_element 顺手移除 guiclass / testclass kwarg(per user 'setup 顺手也改一下');§3.4 `_build_show_subscription_status_sampler` SQL 关键字改小写(per 全局 spec 约定, 之前 §3.4 写大写违反 spec, 增量改);35 → 44 §2 用例 + 13 §3.6 用例全绿 + 全套 813 passed 无 regression
- F-026 §3.7 `pub_sub` 公开 API 导出落地(commit `44d8e37`):`__init__.py` re-export 5 个公开 API (`build_publication_sql` / `build_subscribe_dest_schemas` / `build_create_subscription_sql` / `append_pub_sub_to_setup_tg` / `generate_pub_sub_verify_tg`),`__all__` 锁定范围(防止 caller 误用 module-private helper);7 个 pytest 用例(5 import + 1 __all__ 集合 + 1 私有 helper 不暴露);§3 全套 98 passed + 全套 820 passed 无 regression

**已确定的设计决策**(8 个 Decision + 5 段实现细节):

- **D1**:`pub_sub_config.tables` 字段决定发布粒度,`null/[]` 降级到 `FOR DATABASE` 整库模式;6 种 SQL 形态(整库 / 单表 / 单表+列子集 / 单表+WHERE / 单表+列子集+WHERE / 多表) + `WITH OPTIONS` 拼接规则(12 形态)
- **D2**:`tables[i].columns` 必须含所有 primary_tag 列(spec §2.0 锁定 data 列默认 `nullable=true`,NOT NULL data_col 校验不实施)
- **D3**:`expected_min_rows` 显式覆盖字段,未设时 Verify TG 内联取 `1` 兜底(不依赖 write_config / conn_config.test_duration)
- **D4**:subscriber schema = publisher 全列(即使列子集发布也保持 super-set)
- **D5**:同集群两库单池 + FQN 跨库,`${db_url}` 指向 **defaultdb**(per 2026-10-12 user 纠正:连接时 tsdb 不存在会失败)。subscriber 端 sampler 全部用 FQN 表名(`<publisher_db>_sub.<table>`)跨库访问;publication / subscription metadata per-cluster,在 defaultdb 连接上直接跑;**不**派生 `${db_url_sub}` UDV、**不**新增第二条 Connection、**不**用 `USE` 切库
- **D6**(原编号,现已合并到 D5 段):Verify TG 改用 `tearDown ThreadGroup` 类型,JMeter 引擎保证在所有普通 TG 完成后跑(与 `TestPlan.serialize_threadgroups` 设置无关)。**不**改 `serialize_threadgroups`(保持现有 Write/Query 并行情景)
- **D7**:Verify TG 首条 `SHOW SUBSCRIPTION <sub_name>` + RegexExtractor 提 status + JSR223Assertion 断言含 `running`(防"订阅未启动但 row 数对"假阳性)
- **D8**:`subscribe_dest_schemas.build_subscribe_dest_schemas` 字符串替换复用 `DDLGenerator.generate(...)` 输出,**不**新增 SQL 真源

**关键锁定**:
- `pub_sub_config.options` 必填 + `options.target` 必填(同集群两库场景下,服务端无法仅靠"两端 db.table 名完全对应" 推断同步关系;KaiwuDB 不支持同 db 同 table 自订阅,必须用 `target` 显式指明发布库表 → 订阅库表映射)
- options key 集合分两组,分别注入对应 DDL:
  - publication-side(`buffer_size` / `retrieve_tags` / `publish`)→ `CREATE PUBLICATION` 的 `WITH OPTIONS`
  - subscription-side(`target` / `enable` / `ignore_history` / `retry`)→ `CREATE SUBSCRIPTION` 的 `WITH OPTIONS`
- **不**生成 tearDown ThreadGroup 做 DROP / 不做 `IF EXISTS` 幂等清理(DROP 属功能测试范畴,文档未明确支持 `IF EXISTS`;测试计划仅在流水线内集成,数据库清理由流水线侧负责)
- **DDL 字符串生成层** 与 **TG XML 装配层** 彻底切割:`publication_sql.py` / `subscribe_dest_schemas.py` 只产字符串;`pub_sub_setup_tg.py` / `pub_sub_verify_tg.py` 只装配 XML 元素

**模块布局**(`src/pub_sub/`):
- `__init__.py` — 5 个公开 API 导出(`build_publication_sql` / `build_subscribe_dest_schemas` / `build_create_subscription_sql` / `append_pub_sub_to_setup_tg` / `generate_pub_sub_verify_tg`)
- `publication_sql.py` — `build_publication_sql(publication_name, publisher_db, tables, options=None) -> str`
- `subscribe_dest_schemas.py` — `build_subscribe_dest_schemas(publisher_ddls, publisher_db) -> List[str]`(内部硬约定 `sub_db = f"{publisher_db}_sub"`) + `build_create_subscription_sql(subscription_name, publication_name, conninfo, options=None) -> str`
- `pub_sub_setup_tg.py` — `append_pub_sub_to_setup_tg(setup_tg_element, pub_sub_config, test_model_config) -> None`(4 步:内部 derive publisher_ddls → CREATE PUBLICATION → CREATE TS DATABASE `<publisher_db>_sub` → `;` 分隔 subscriber DDL 合并到单 sampler → CREATE SUBSCRIPTION)
- `pub_sub_verify_tg.py` — `generate_pub_sub_verify_tg(pub_sub_config, test_model_config) -> Element`(Verify TG delay=60s、duration 不显式设让 TG 自然结束;expected_min_rows 内联 default=1,user 显式覆盖可设 0 走恒真)

**Reference 文档**:
- `docs/refs/kaiwudb-pubsub-references.md` 待新建(编码阶段创建)
- `docs/refs/jmx-components-references.md` 已加 §PostThreadGroup / §RegexExtractor / §JSR223Assertion 三段(基于 2026-10-12 user 实测 jmx);Flow Control Action 条目保留(对其他 SetupTG 暂停场景仍有参考价值)

**Spec 未验 / 后续 DCR 范围**:
- 列子集发布 + WHERE 过滤的 server-side 行为验证(端到端 smoke)
- options 字段(`buffer_size` / `retrieve_tags` / `publish` / `target` / `enable` / `ignore_history` / `retry`)的 server-side 行为验证
- ALTER SUBSCRIPTION / ALTER PUBLICATION 完整生命周期(归属功能测试)
- HA 主备切换 / 断点续传(归属功能测试)
- 多 publication / 多 subscription 链式级联(KaiwuDB 平台 1:1 限制)

**编码阶段 plan**(2026-10-12 review 收尾):
- (1) `src/config_parser/models.py` 新增 `PubSubConfig` + `PublicationTableEntry` Pydantic 模型 + `@model_validator` 校验规则(已锁定的 8 字段 + 嵌套模型 + 各种校验约束);`TestConfig` 增加 `pub_sub_config: Optional[PubSubConfig] = None` 字段
- (2) `src/utils/xml_helpers.py` 新增 3 个 helper:`teardown_thread_group_element(...)` / `regex_extractor_element(ref_name, regex, template, match_number, default="")` / `jsr223_assertion_element(script, script_language="groovy")`,对齐 `docs/refs/jmx-components-references.md` §PostThreadGroup / §RegexExtractor / §JSR223Assertion 实测 schema
- (3) `src/pub_sub/` 子包 5 个模块按 Module Layout 段(`__init__.py` + `publication_sql.py` + `subscribe_dest_schemas.py` + `pub_sub_setup_tg.py` + `pub_sub_verify_tg.py`),纯函数式 API;SetupTG 4 步 / VerifyTG PostThreadGroup + 3 sampler 顺序按 design.md 实现
- (4) `src/jmx_skeleton_generator/generators/test_plan.py` 在 `generate_ddl_setup_thread_group` 后追加 `append_pub_sub_to_setup_tg`(当 `pub_sub_config` 段存在);在主 TG 后追加 `generate_pub_sub_verify_tg`(当 `pub_sub_config` 段存在)
- (5) `tests/kwjdbc_svt/fixtures/test_cfg_pub_sub.yaml` (整库模式) + `test_cfg_pub_sub_tables.yaml` (表级 + 列子集 + WHERE) 按 design.md §`pub_sub_config` 段示例编写
- (6) `tests/pub_sub/` 新增 pytest:`test_publication_sql.py` / `test_subscribe_dest_schemas.py` / `test_pub_sub_setup_tg.py` / `test_pub_sub_verify_tg.py`(每段映射 `src/pub_sub/` 模块);`tests/config_parser/test_pub_sub_config.py` 覆盖 PubSubConfig 各种校验场景;`tests/jmx_skeleton_generator/test_ddl_setup_pubsub_append.py` 覆盖集成路径
- (7) `docs/refs/kaiwudb-pubsub-references.md` 新建:CREATE PUBLICATION / CREATE SUBSCRIPTION 语法 + 权限 + 同步周期 + 端到端延迟 + 2-5s 连接窗口 + insecure / TLS conninfo 示例 + conninfo 与 `${db_url}` 一致性 + 数据库清理归属说明(由流水线负责)
- (8) `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` §7 加 pub_sub smoke 章节:`jmeter -n -t test_plan.jmx -J...` 跑两次端到端(a) 整库模式 (b) 表级 + 列子集 + WHERE 模式,断言 (a)-(d) 全过(SetupTG code==0 / Write TG JTL 100% 成功 / Verify TG count(*) >= threshold / SHOW SUBSCRIPTION status 含 running)

**下一动作**:§1 + §2 已完成;开始 step (3) src/pub_sub/ 子包 5 模块(`__init__.py` + `publication_sql.py` + `subscribe_dest_schemas.py` + `pub_sub_setup_tg.py` + `pub_sub_verify_tg.py`)→ step (4) 集成到 test_plan.py → step (5)-(8) 联调 + 文档收尾
