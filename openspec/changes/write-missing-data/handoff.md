# Handoff — write-missing-data

> 本文件是本 change 的进度交接点。**下一个会话只读本文件 + `tasks.md` 即可续接**;
> 也可以把下方「续接提示」整段粘贴给新会话。写法遵循 `session-handoff-prompt` skill 的输出契约。

---

## 续接提示(可直接粘贴给新会话)

你正在接手一个进行中的 agent 会话。直接从下面的上下文续接,不要重新打开已定结论;若本提示与工作区当前文件/已验证证据冲突,以当前证据为准并说明冲突。

【工作目录】
- 仓库:/home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
- 分支:feat/pub-sub(已 push;远端默认分支 develop-2.0)
- change 位置:openspec/changes/write-missing-data/
- 环境(project 规则 §5,worktree 独立 venv):
  cd /home/liujin/workspace/quality-test-pipelines/kwjdbc-svt
  source .venv/bin/activate
  pip install -e ".[dev]"    # 首次进 worktree 才需要

【用户目标】
为 kwjdbc-svt 生成器实现"写入侧按批次随机缺失数据"的能力(OpenSpec change `write-missing-data`),按 TDD 节奏编码落地,并跑通端到端 smoke。

【必须遵守的要求】
- TDD 节奏:pytest 先行 → 编码 → 该模块 pytest 全绿 → 才推进下一模块(tasks.md 顶部有约定)。
- review 闸门:每个 commit 前停下来等 user review,收到明确信号再 commit/push(全局规则 feedback-review-before-commit-not-after)。
- 两个 commit 切分固定:
  · commit 1 = 既有代码修正(与缺失功能零耦合,可独立回滚):7 处随机源换 ThreadLocalRandom + 空种子池抛业务异常 + write_config[] 同表唯一校验 + schemaless 大小写归一。
  · commit 2 = 缺失功能(新增能力),依赖 commit 1 的干净基线。
- smoke 需 6 条路径全覆盖:direct / prepare / schemaless × bind / 非 bind,不得只跑一条就宣称通过。
- 零回归:未声明 missing 段或 probability=0.0 的条目,生成的 JMX 与基线逐字节一致。
- 过程文档 / 思考 / 回复一律中文(技术术语、代码标识符保留原文)。

【已确认的事实与决策】
design.md §Open Questions 16 条全部收敛(0 条待决),要点:
- [verified] 配置形态 = 表级嵌套 missing 段(write_config[].missing),段名 missing;probability 必填([0.0,1.0],1.0=必然缺失 / 0.0=关闭);ts_count / device_count 可选缺省 0;段不存在 = 该表不做缺失。
- [verified] 缺失判定由设备维度与时间戳维度分别判定,两者同时命中才跳过该格(交集);某维度 count=0 → 该维度恒"命中" → 视为全集、不构成约束:
    device_hit = device_count == 0 || device_idx >= device_per_thread - device_count
    ts_hit     = ts_count == 0 || ts_idx >= batch_lines - ts_count
    skip       = device_hit && ts_hit
- [verified] 截断方式 = 从后向前(尾部),设备序列 1、2、3、4、5 截断 2 个 → 保留 1、2、3;尾部按本轮网格相对下标定义(非绝对设备号、非表内列序)。
- [verified] 缺失维度绑定表结构:设备维度 = 第一个 primary tag 列,时间戳维度 = ts_col。
- [verified] 触发时机 = 每写入批次判定一次;probability=1.0 走常量分支(零随机调用);各写入线程判定相互独立,不支持"所有线程同一批次同时缺失"。
- [verified] 计数上界取 <=(等于总数即"缺整轮",合法形态);超过总数在配置期 ValueError。
- [verified] probability=0.0 时不注入缺失逻辑(行为与未声明 missing 段完全一致,不留恒假死代码)。
- [verified] 覆盖 6 处 Groovy 装配点:direct 非 bind / direct bind / prepare 非 bind / prepare bind / schemaless 非 bind / schemaless bind。
- [verified] 缺失不做吞吐补偿(只减落库行数,不改变 sampler 触发次数)。
- [verified] 缺整轮(空批次)在三条路径各有兜底:direct 不产出空 VALUES;prepare 跳过空批次;schemaless 空 body 不判失败。
- [verified] 运行时 device_per_thread 漂移(UDV 被改小)→ 退化为只按 ts 维度截断(而非 clamp 阈值),保住数据。
- [verified] 既有代码修正另一半:生成器 Groovy 脚本 7 处随机调用点全部换 ThreadLocalRandom.current()(8 线程 0.7 ns/call,无锁无争用);write_config[] 同表不可多条(按 tbl_name.lower() 比较,配置期拒绝);schemaless 建索引与查询统一 to_lower。
- [verified] 空种子池:上游 loader 不再 log.error + 置空(改为抛异常中断),下游 6 个消费点抛业务异常直接退出 —— 修正前是"测试跑完全绿却一行数据都没写"。

【已完成】
- [verified] OpenSpec 五件套全部落地并 openspec validate 通过(proposal 65 行 / design 443 行 / spec 378 行 / review 113 行 / tasks 135 行 / 53 条子 task)。
- [verified] commit 9479783(DCR 五件套)与 ce95107(删除 todolist.md + 落地 handoff.md)已 push 到 feat/pub-sub。
- [verified] todolist.md 已删除;AGENTS.md §7 改为跟踪 change 的 handoff.md;README.md 死链已修。
- [verified] 本次 review 修正了 10 处三文档不一致 + 3 类既有缺陷(见 review.md §2 / §4)。

【未完成 / 待验证】
- [verified] 编码尚未开始,tasks.md §1~§9 全部子 task 未勾选。
- [verified] Phase B smoke(真实 KaiwuDB 容器)未跑,编码阶段补(tasks.md §9)。
- [unverified] direct 路径种子行选择因随机源复用而序列相关性上升(分布不变)—— smoke 时需观察。
- [unverified] 交集语义下缺失量是 M × N 而非 M + N(例 M=1,N=2 → 丢 2/20 格 = 10%);spec 已写明,示例配置需避免歧义措辞。

【关键文件 / 命令 / 产物】
- 设计产物:openspec/changes/write-missing-data/{proposal,design,specs/write-missing-data/spec,review,tasks,handoff}.md
- 配置模型:src/config_parser/models.py(WriteConfig / 新增 MissingConfig)
- 6 处装配点:src/jmx_skeleton_generator/generators/write_groups.py(_build_inline_sql_preprocessor_script / _build_batch_prepared_preprocessor_body / _build_batch_prepared_bind_preprocessor_body)、rest_write_groups.py(_build_rest_write_preprocessor_script)
- 判定 helper:src/utils/preprocessor_helpers.py(新增 should_skip_row + groovy_missing_data_decl)
- loader:src/shared_memory_initializer/shared_memory_initializer.py::generate_groovy_loader_script
- 7 处随机源:write_groups.py(:186/:252/:635/:744)、rest_write_groups.py(:236/:329)、query_groups.py(:489)
- 测试:tests/config_parser/、tests/utils/、tests/jmx_skeleton_generator/、tests/kwjdbc_svt/fixtures/
- 全量回归:python -m pytest tests/(当前基线 835 passed)
- 生成 JMX:python -m kwjdbc_svt.main -o output/a <model.yaml> <cfg.yaml>
- 端到端 smoke:走 kwjdbc-jmx-smoke skill(不要自己拼命令序列),需真实 KaiwuDB 容器

【不要重复 / 不要做】
以下都是本次 review 实际踩过并已修正的,别再犯:
1. 别先写 design 再写 spec —— 正确顺序 proposal → spec → design → tasks;design 必须基于 spec 写。
2. 别往 spec 后面追加补丁章节 —— 需求描述有问题就改前面那一节。
3. 别把判定式写成单个合并布尔式 —— 两个维度必须分别判定再取交集。
4. 别把 count==0 写成 count>0 —— 会让单维配置完全失效(count=0 的维度应恒"命中"= 不构成约束)。
5. 别把概率上界写成 >= 1.0 —— 值域被 le=1.0 封闭,> 1.0 分支不可达,写 == 1.0。
6. 别在 probability=0.0 时注入 —— 不注入才没有恒假死代码。
7. 别把计数上界写成 < —— 应为 <=,缺整轮是合法形态。
8. 别写"不做 X"式的反向元描述 —— 改成"由取值隐含表达,不需要独立开关" / "暂不支持……的模拟"。
9. 别在 DCR 文档里提已否决概念(enabled 字段、throughput 公式等)。
10. 别顺手扩大范围 —— commit 1 的三类修正虽已获批,但要保持在 commit 1 内、别混进 commit 2。

【下一步】
1. 读 openspec/changes/write-missing-data/handoff.md 与 tasks.md(尤其 §0 决策清单与 TDD 约定)。
2. 从 tasks.md §1 开始:pytest 先写 tests/jmx_skeleton_generator/test_random_source.py 含失败断言 → 实现 7 处随机源替换 → 全绿 → §2 → §3。
3. §3 验收通过后停下等 user review,收到信号再 commit 1 + push。
4. 拿到信号后从 §4 起做缺失功能(配置模型 → 判定 helper → 6 处注入 → 集成与 fixture),同样在 commit 2 前停下 review。
5. §9 smoke:8 个 fixture 覆盖 6 条路径 + 概率 + 缺整轮 + 空种子池失败路径;probability=1.0 的确定性断言见 tasks.md §9.1。
6. 每完成一节,回来更新本文件的「已完成」并勾选 tasks.md 对应子 task。
