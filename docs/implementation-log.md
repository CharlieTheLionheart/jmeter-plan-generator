# kwjdbc-svt 实施档案

> 本文件回答"**为什么这么做**" —— 每个阶段做了什么 / 为什么 / 踩了什么坑与修法 / 遗留。
>
> - "上次到哪儿了、下一步做什么" → 工程根目录的 `handoff.md`(`handoff` skill 生成,gitignored,不入库)
> - 规格与任务清单 → 各 OpenSpec change 的 `openspec/changes/<change>/`(proposal / design / spec / tasks),**本档案不重复**其内容,只记录决策与教训
> - 主规格 → `docs/specs/kwdb-svt-test-plan-generator-spec.md`

## 已落地阶段一览

| 阶段 | 内容 | 状态 |
|---|---|---|
| pub-sub-end-to-end | 发布订阅端到端(SetupTG 建发布/订阅 + Verify tearDown TG + `pub_sub_config` 表级配置段) | 设计 + 实现 + smoke 完成,待 `openspec archive` |
| write-missing-data 阶段 0 | 写入侧按批次随机缺失数据 —— DCR 五件套设计(proposal / design / spec / review / tasks) | 设计完成,编码未开始 |
| write-missing-data 阶段 1 | commit 1 既有代码修正:7 处随机源换 `ThreadLocalRandom` + 空种子池抛业务异常(loader + 6 消费点)+ `write_config[]` 同表唯一校验 + schemaless 大小写归一 + schemaless 非 bind 路径既有缺陷修正 | 已落地(代码 + UT 全绿 + smoke 全绿,review 通过后 commit) |

## 待办(跨会话)

- **write-missing-data 编码** —— 按 `openspec/changes/write-missing-data/tasks.md` §1~§9 推进(TDD 节奏:pytest 先行 → 编码 → 模块全绿 → 下一模块;每个 commit 前**停下等 user review**)。
  - commit 1 = 既有代码修正(与缺失功能零耦合,可独立回滚):7 处随机源换 `ThreadLocalRandom` + 空种子池抛业务异常 + `write_config[]` 同表唯一校验 + schemaless 大小写归一 + schemaless 非 bind 路径修正 —— **§1~§3 已落地,UT 874 全绿 + smoke 全绿,已 commit**
  - commit 2 = 缺失功能(新增能力):配置模型 → 判定 helper → 6 处 Groovy 注入 → 集成与 fixture —— **下一步从这里开始(tasks.md §4)**
- **pub-sub-end-to-end 归档** —— `openspec archive` 前确认 spec 增量合并进主 spec。
- **smoke 证据** —— write-missing-data 的 Phase B smoke(6 条路径全覆盖 + 概率 + 缺整轮 + 空种子池失败路径)尚未跑,编码阶段补。

## §决策汇总

### §2026-10-26~27 write-missing-data 阶段 0:DCR 设计

**做了什么** —— 产出 OpenSpec 五件套(proposal / design / spec / review / tasks),`openspec validate` 通过。核心决策:写入侧新增**表级嵌套 `missing` 段**(`probability` 必填 / `ts_count` / `device_count` 缺省 0),按**从后向前截断**、设备维度与时间戳维度**分别判定取交集**、**每写入批次按概率**触发一次缺失,覆盖 `direct` / `prepare` / `schemaless` × bind / 非 bind 共 6 处 Groovy 装配点。

**为什么** —— 当前写入侧永远是"完整笛卡尔积"(`device_per_thread` 个设备 × `batch_lines` 个时间戳全写),无法制造"某些设备某些时刻没上报"的稀疏形态,而稀疏形态正是 CDC 增量同步 / 时序补写 / 稀疏查询的真实输入。

**踩了什么坑与修法**(review 阶段实际发现并已修正,共 10 处三文档不一致):

| # | 坑 | 修法 |
|---|---|---|
| 1 | design 先于 spec 写,design 初版还是"随机抽样"语义,与 spec 的尾部截断冲突 | 推倒重写:spec 先行,design 基于 spec 全文重写 |
| 2 | 需求描述有问题时往 spec 后面**追加补丁 Requirement** | 改前面那一节(表层级归属合并回 Requirement 1 第一段 + 层级图) |
| 3 | 判定式写成单个合并布尔式,掩盖了"两维度独立判定"的结构 | 改为 `device_hit` / `ts_hit` 两行独立判定再取交集 |
| 4 | 改写"分开判定"时写成 `count > 0 && ...` | **单维配置会完全失效**(count=0 的维度应恒"命中"= 不构成约束)→ 改回 `count == 0 \|\| ...` |
| 5 | 概率上界写 `>= 1.0` | 值域被 `le=1.0` 封闭,`> 1.0` 分支不可达 → 写 `== 1.0` |
| 6 | `probability = 0.0` 时仍注入缺失逻辑 | 改为不注入(行为与未声明 `missing` 段一致,不留恒假死代码) |
| 7 | 计数上界写 `<`(严格小于),把"缺整轮"挡在门外 | 放开为 `<=`,缺整轮成为取值的自然结果 |
| 8 | 配置形态用平级三字段,配了 count 忘配 probability 会静默失效 | 改为嵌套段 + `probability` 必填 → 错误配置在语法上无法表达 |
| 9 | design 的 Non-Goals 写"不做缺整轮" | 读起来像"技术上做不到" → 改为"由计数取全量隐含表达,不提供独立开关" |
| 10 | Risks 用"不做 / 不改 / 未修"描述范围边界 | 改为能力边界声明(如"各线程独立判定,暂不支持全体同时缺失") |

**顺带修正的 3 类既有缺陷**(归入 commit 1,与缺失功能解耦):

| 缺陷 | 现状 | 修法 |
|---|---|---|
| 空种子池静默降级 | loader `log.error` + 置空数组;1 处走到 `% totalRows` 除零 `ArithmeticException`,5 处 `log.warn` + 静默降级 —— **测试跑完全绿却一行数据都没写** | loader 抛异常中断;6 个消费点抛业务异常直接退出 |
| `write_config[]` 同表多条无校验 | JDBC 路径生成两个同名 TG(行数与 throughput 翻倍、缺失策略叠加),schemaless 路径后者覆盖前者(前一条静默丢弃),两路径不一致 | 配置期按 `tbl_name.lower()` 拒绝重复 |
| schemaless 大小写敏感 | 建索引用 cfg 原样串、查询用 model 的 name,不一致即匹配失败 | 统一 `to_lower`,与 JDBC 路径对齐 |

**性能依据** —— JDK 21 微基准(8 线程并发):`new Random().nextInt` 73.4 ns/次(每行调用时约 1.5 μs/批次)、`Math.random()` 141.4 ns(全局 CAS 争用)、`ThreadLocalRandom.current()` **0.7 ns**(无锁无争用)。缺失判定每批次只调 1 次概率判定,缺失集合由确定性下标比较得出(零随机数)。据此把生成器 Groovy 脚本里的 7 处随机调用点全量替换。

**遗留 / 待验证**

- `direct` 路径种子行选择因随机源复用而**序列相关性上升**(分布不变)—— smoke 时观察
- 交集语义下缺失量是 `M × N` 而非 `M + N`(例 `M=1, N=2` → 丢 2/20 格 = 10%)—— spec 已写明,示例配置需避免歧义措辞
- Phase B smoke(真实 KaiwuDB 容器)未跑

### §2026-10-28 write-missing-data 阶段 1:commit 1 既有代码修正

**做了什么** —— 三块既有代码修正(D4(b) / D11 / D12),全部与"缺失功能"零耦合、可独立回滚:

| # | 修正 | 落点 |
|---|---|---|
| 1 | 随机源全量换 `ThreadLocalRandom` | `write_groups.py` 4 处 + `rest_write_groups.py` 2 处 + `query_groups.py` 1 处 |
| 2 | 空种子池改为**尽早抛业务异常** | loader(`shared_memory_initializer.py`)2 处 + 6 个消费点(`write_groups.py` 4 + `rest_write_groups.py` 2) |
| 3 | 配置校验硬化 | `TestConfig.check_write_config_unique_tables`(同表唯一,大小写不敏感)+ schemaless 索引/查询大小写归一 |

**为什么** —— 三者都是**存量缺陷**:空种子池静默降级会让整轮测试"跑完全绿但一行数据都没写"(§2 的 6 个消费点里 5 处 `log.warn` + 早退、1 处除零 `ArithmeticException`);同表两条在 JDBC 与 schemaless 两条路径的行为分叉(JDBC 生成两个 TG 叠加写、schemaless 后者静默覆盖前者);随机源是真实热点(内层行循环每行 `new Random()`)。它们与缺失功能解耦,先落地可让功能 commit 的基线已经是干净的。

**踩了什么坑与修法**

| # | 坑 | 修法 |
|---|---|---|
| 1 | **pytest 抓不到 Groovy 编译错误** —— 生成的 Groovy 只是一段文本,语法错误要等 JMeter 运行时才暴露 | 加"转义回归闸门"单测(见坑 3);并按 `AGENTS.md` §6 在 UT 全绿后必跑 smoke |
| 2 | **3 个既有单测锁的是"静默降级"旧契约**(空池 → `SELECT 1` / 空 body / `log.warn`),与 D11 直接冲突 | 改写这 3 个用例为新契约(抛异常 + 带上下文),不是删测试 |
| 3 | **smoke 暴露 schemaless 非 bind 路径整体不可用**(见下"既有缺陷 4") | 补"生成脚本不得残留字面 `\n`"的回归闸门单测(字面反斜杠 n 会让 Groovy 报 `Unexpected character: '\'`) |
| 4 | **schemaless 非 bind 路径的既有缺陷**:`rest_write_groups.py` 的 `tsValue` 行写成 f-string 时把 `\n` 误写成 `\\n` → 生成脚本残留字面反斜杠 n → Groovy 编译失败(2026-09-08 commit `2cb6d39` 引入);修掉后又暴露该分支缺 ns 换算(`* 1000 * 1000`,bind 分支在 D-29 已补、non-bind 漏补)与 fixture 缺 `ts_col`(`k_timestamp` / `timestamp(9)`)→ 服务端把行尾时间戳映射不到列,NOT NULL 的 `ts` 恒 NULL | 三处一并修正(源码 2 行 + fixture 补 `ts_col`);修完 schemaless smoke 由 20 错 → **Err: 0** |

**为什么之前 smoke 能跑通** —— schemaless 非 bind 路径**从 2026-09-08 起就没跑通过**:skill §6.4.5 的排障记录停在 2026-07-31(在 typo 之前),此后跑过的都是 §7 pub_sub smoke(JDBC 路径)与 D-29 ns 精度修复(只动 bind 分支那一行);所有 schemaless fixture 当时要么是 bind 模式(`test_model_sparse_100_schemaless.yaml` 走 bind 分支,那行 `\n` 是对的),要么就是本 DCR 之后要新建的缺失数据 fixture。non-bind 分支 + `test_model_schemaless.yaml` 这对组合**没有任何一次成功记录**。

**smoke 证据**(本次实跑,KaiwuDB 容器)

| 路径 | 结果 |
|---|---|
| JDBC(`prepare`,`test_cfg.yaml`) | `Err: 0 (0.00%)`,落库 40 行 = 8 设备 × 5 ts(满网格) |
| schemaless 非 bind(TLS,`test_cfg_schemaless_tls.yaml`) | `Err: 0 (0.00%)`,落库 100 行 = 10 设备 × 10 ts(满网格) |
| 无 DB 跑(暴露非 DB bug) | JMX 加载成功;唯一错误是 `ConnectException: 连接被拒绝`(JDBC driver 层,符合预期);无 Groovy 编译错误 |

**遗留**

- `TestConfig.find_write_config()` 仍是**大小写敏感**的精确匹配 —— D12(b) 只覆盖了 schemaless 路径的索引/查询。cfg 写大写表名时,schemaless 路径能命中,但 `main.py` 的 bind 模式校验 / seed CSV 路径排除仍会 `find_write_config` 返回 `None`(两者都是"跳过"语义,不会误写)。若后续要求 cfg 表名大小写全链路等价,需另开一处归一。
- commit 1 已于 2026-10-28 review 通过后落地(见 git log)。下一阶段从 `tasks.md` §4(commit 2:缺失功能)继续。
