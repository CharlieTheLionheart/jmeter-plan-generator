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

## 待办(跨会话)

- **write-missing-data 编码** —— 按 `openspec/changes/write-missing-data/tasks.md` §1~§9 推进(TDD 节奏:pytest 先行 → 编码 → 模块全绿 → 下一模块;每个 commit 前**停下等 user review**)。
  - commit 1 = 既有代码修正(与缺失功能零耦合,可独立回滚):7 处随机源换 `ThreadLocalRandom` + 空种子池抛业务异常 + `write_config[]` 同表唯一校验 + schemaless 大小写归一
  - commit 2 = 缺失功能(新增能力):配置模型 → 判定 helper → 6 处 Groovy 注入 → 集成与 fixture
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
