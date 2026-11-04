# kwjdbc-svt 实施档案

> 本文件回答"**为什么这么做**" —— 每个阶段做了什么 / 为什么 / 踩了什么坑与修法 / 遗留。
>
> - "上次到哪儿了、下一步做什么" → 工程根目录的 `handoff.md`(`handoff` skill 生成,gitignored,不入库)
> - 规格与任务清单 → 各 OpenSpec change 的 `openspec/changes/<change>/`(proposal / design / spec / tasks),**本档案不重复**其内容,只记录决策与教训
> - 主规格 → `docs/specs/kwdb-svt-test-plan-generator-spec.md`

## 已落地阶段一览

| 阶段 | 内容 | 状态 |
|---|---|---|
| pub-sub-end-to-end | 发布订阅端到端(SetupTG 建发布/订阅 + Verify tearDown TG + `pub_sub_config` 表级配置段) | 设计 + 实现 + smoke 完成,**已 `openspec archive`**(2026-11-02,spec 增量 +12 条合并进 `openspec/specs/pub-sub-end-to-end/spec.md`) |
| write-missing-data 阶段 0 | 写入侧按批次随机缺失数据 —— DCR 五件套设计(proposal / design / spec / review / tasks) | 设计完成,编码未开始 |
| write-missing-data 阶段 1 | commit 1 既有代码修正:7 处随机源换 `ThreadLocalRandom` + 空种子池抛业务异常(loader + 6 消费点)+ `write_config[]` 同表唯一校验 + schemaless 大小写归一 + schemaless 非 bind 路径既有缺陷修正 | 已落地(`e11f41d`,UT 874 全绿 + smoke 全绿) |
| write-missing-data 阶段 2 | commit 2 缺失功能:`MissingConfig` 配置模型 + Python/Groovy 同构判定 helper + 6 处 Groovy 注入 + D7 缺整轮兜底 + 9 个 fixture + 主 spec 同步;顺带修掉 direct 路径 3 个从未跑通的既有缺陷 | **已落地**(`de19e36`,分支 `feat/write-missing-data`;UT 951 全绿 + Phase B smoke 11 个用例全绿;change 已 `openspec archive`)。**smoke 断言已落成正式 pytest**(`tests/kwjdbc_svt/test_missing_smoke.py`,opt-in:`KWJDB_SVT_SMOKE=1`) |
| data-fill-query 预研 | 补值查询用例设计 + KaiwuDB 插值语义实测(3.2.0 / 3.3.1):新增场景配置 `docs/confs/test_cfg_shig_missing_fill.yaml`(缺值写入 + 13 条补值查询用例)+ 缺陷工单 `docs/issues/interpolate-multi-projection-count.md` | 预研 + 实测完成;**下一个 DCR 尚未开**(草稿 `openspec/specs/data-fill-query/` 未入库) |

## 待办(跨会话)

- **write-missing-data** —— **两个 commit 均已落地,change 已 `openspec archive`**(归档目录 `openspec/changes/archive/2026-10-30-write-missing-data/`,spec 增量合并进 `openspec/specs/write-missing-data/spec.md`)。
  - commit 1 = 既有代码修正(与缺失功能零耦合,可独立回滚):7 处随机源换 `ThreadLocalRandom` + 空种子池抛业务异常 + `write_config[]` 同表唯一校验 + schemaless 大小写归一 + schemaless 非 bind 路径修正 —— `e11f41d`(分支 `feat/pub-sub`)
  - commit 2 = 缺失功能(新增能力):配置模型 → 判定 helper → 6 处 Groovy 注入 → 集成与 fixture —— `86b4b63`(分支 `feat/write-missing-data`,从 `feat/pub-sub` 拉出)
- **pub-sub-end-to-end 归档** —— `openspec archive` 前确认 spec 增量合并进主 spec。
- **write-missing-data 后续** —— 分支 `feat/write-missing-data` 待提 PR 合入(远端默认分支 `develop-2.0`)。smoke 断言已落成 `tests/kwjdbc_svt/test_missing_smoke.py`(opt-in:`KWJDB_SVT_SMOKE=1`)。
- **smoke 证据** —— write-missing-data 的 Phase B smoke(6 条路径 + 概率 + 缺整轮 ×3 路径 + 空种子池)已跑完并全绿,证据见阶段 2 条目。
- **data-fill-query(下一个 DCR)** —— 预研 + 实测已完成(见下方 §2026-11-03 条目),但 **DCR 尚未开**:草稿 `openspec/specs/data-fill-query/pre-research.md` 仍为未跟踪状态(按既有约定不直接入库),下一步应把它整理成 change 的 proposal / design / spec / tasks。
  - 场景配置 `docs/confs/test_cfg_shig_missing_fill.yaml` 已就位(可直接拷进 `integration-test/configs/`),待 DCR 定稿后再决定是否入库流水线。
  - 两处待定:`missing.probability` 暂取 0.5(是否改 1.0);FILL 用例的 `ptag_varchar_1 = '0_1'` 与 `device_start` 的耦合。
  - 缺陷工单 `docs/issues/interpolate-multi-projection-count.md` 待厂商响应(3.2.0 与 3.3.1 均复现)。

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

### §2026-10-29 write-missing-data 阶段 2:commit 2 缺失功能

**做了什么** —— §4 配置模型(`MissingConfig`)+ §5 判定 helper(Python/Groovy 同构)+ §6 六处 Groovy 注入 + §7 集成与 8 个 fixture,全部落地并通过 §9 的 Phase B smoke。

| 子阶段 | 内容 |
|---|---|
| §4 | `config_parser/models.py` 新增 `MissingConfig`(段内字段白名单 `extra="forbid"`、`probability` 必填且 ∈ [0.0,1.0]、两个 count 缺省 0);`WriteConfig.missing: Optional[MissingConfig]` + `@model_validator(mode="after")` 跨字段校验(`ts_count ≤ batch_lines` / `device_count ≤ device_per_thread`,取等合法 = 缺整轮) |
| §5 | `utils/preprocessor_helpers.py` 新增 `should_skip_row(...)`(纯比较,无随机源)+ `groovy_missing_data_decl(...)` + `groovy_missing_data_block(...)`(未启用时返回空串 → 拼接后脚本逐字节不变)+ `groovy_missing_skip_line(...)` |
| §6 | 6 处装配点注入:`write_groups.py` 的 direct 非 bind / direct bind / prepare 非 bind / prepare bind,`rest_write_groups.py` 的 schemaless 非 bind / bind。D7 兜底:direct 空行 → 注释串兜底;prepare bind 空 rows 设备不入 preps;schemaless 空 body → `__missing_skipped` 标记,B1 断言据此放行 |
| §7 | `tests/kwjdbc_svt/test_main.py` 集成用例(8 个 fixture 生成 JMX + `ElementTree.parse()` 校验)+ 8 个新 fixture |
| §8 | 主 spec `docs/specs/kwdb-svt-test-plan-generator-spec.md` §2.0 补 `missing` 段字段表;本档案同步 |

**关键设计修正(实现阶段发现,已回写 design/spec/tasks)**

| # | 问题 | 处置 |
|---|---|---|
| 1 | **design D1 的"count=0 视为全集恒命中"有漏洞**:两个 count 都是 0 时算出 `true && true` → **整轮全丢**,与 spec Scenario「两个 count 均为 0 → 无缺失效果」直接冲突 | 改为"count=0 = **该维度未配置、不参与判定**",生成期只把已配置的维度写进脚本。四种形态(单维 ×2 / 双维交集 / 双零不丢)与 spec 逐条对齐。D7 的运行时漂移(阈值非正 → 设备维退化为全集 → 只按 ts 维截断)**不需要额外分支**,阈值不做 clamp 即自然成立 |
| 2 | **tasks §9.1 断言 ⑤ 的公式是并集口径** `(dpt−M)×(B−N)`,与 D1 的交集语义冲突 | 改为 `dpt×B − M×N`(交集口径) |
| 3 | **`missing` 段的注入闸门**(design D6)只判 `probability > 0` | 补:两个 count 都是 0 时段合法但无缺失效果 —— 生成的闭包恒 `return false`,不丢任何格子 |

**顺带修掉的既有缺陷(3 处,全部是 direct 路径从未跑通的原因)**

| # | 缺陷 | 症状 | 修法 |
|---|---|---|---|
| 1 | direct 的 Write TG **没有挂 per-ThreadGroup UDV** | preprocessor 读不到 `column_types` → 类型表为空 → 数值列被加引号 → 服务端 `42804 datatype mismatch`,一行都写不进去 | direct 分支补 `_build_write_udv(...)` |
| 2 | direct 非 bind 的 `typeList.get(c)` —— `String.split()` 返回**数组**,Groovy 数组没有 `.get()` | preprocessor 每 tick 抛 `MissingMethodException` → JSR223 报错但 sampler 仍报成功 → 静默 0 行 | 改 `typeList[c]` |
| 3 | direct bind 的单元格**原样未加引号**拼进 inline INSERT | 字符串值被当关系名解析 → `42601 unsupported input type relation "m2"` | bind 分支按列类型引号化(数值列不加引号,与非 bind 分支同规则);类型经 `column_types` UDV + model 列序回查 |

> 三处都在 `direct` 路径上,而 `direct` 此前**没有任何一次成功记录**(基线 `e11f41d` + 无 `missing` 段的 direct fixture 实跑:`Err: 4 (50%)`、0 行)—— 是 §9.2.1/§9.2.2 要求的 direct smoke 暴露出来的,不是本 change 引入的。

**踩了什么坑与修法**

| # | 坑 | 修法 |
|---|---|---|
| 1 | **pytest 抓不到 Groovy 编译/运行错误** —— 本次 direct 路径的 3 个缺陷全是 JMeter 运行时才暴露(preprocessor 抛异常、sampler 报 42804/42601) | 严格按 `AGENTS.md` §6:UT 全绿后逐路径跑 smoke;并把 JTL 的 `success=false` + `responseCode` 纳入断言 |
| 2 | **JSR223PreProcessor 抛异常时 sampler 仍报成功** —— direct 缺陷 2 就是这样"静默 0 行 + Err: 0" | smoke 断言不能只看 `Err:` 计数,必须查落库行数与 `jmeter.log` 的 `Problem in JSR223 script` |
| 3 | **direct 路径的 ts 取毫秒级 wall clock,多线程首批会撞值** —— 4 线程首批 baseTime 落在同一毫秒 → 20 个 ts 值塌成 6 个,per-ts 断言失真 | direct / schemaless 缺失 fixture 改单线程(多线程语义已由 prepare 两条 4 线程路径覆盖);断言按"每设备经历的批次数"归一 |
| 4 | **smoke 断言口径要按"每设备批次数"归一** —— 同一台表里每设备经历的批次数可能不同(各线程独立 tick) | 归一因子 = `max(每设备 ts 覆盖数) / batch_lines`;行数期望 = `组数 × 批次数 × (D×B − M×N)` |
| 5 | **`kwbase sql` 输出是 tab 分隔**,按 `|` 切分解析不到分布 | 解析改空白切分 + 跳过表头 |
| 6 | **JTL 的 `failureMessage` 对 JSR223 报错是空的** —— JMeter 只写 `responseCode=500`,异常文本进 `jmeter.log` | 失败消息的内容断言只能从 `jmeter.log` 取;JTL 只用于"哪些 label 报了 error" |
| 7 | **JMeter 的 preprocessor 异常不阻断 sampler** —— 消费点抛了业务异常,sampler 仍执行并拿到 null → NPE | 两者都算 error,测试如实报失败;失败消息(业务异常)在 `jmeter.log`,JTL 里看到的是 NPE |
| 8 | **多线程首批的 baseTime 可能落在同一毫秒** → ts 值相撞,`distinct_ts < 批次数 × batch_lines` | 批次数的判定基准用 JTL 的 `[Write]` sample 数,不用 `distinct_ts ÷ batch_lines`;direct / schemaless 的缺失 fixture 用单线程 |

**smoke 证据**(本次实跑,KaiwuDB TLS 容器 `kaiwudb-smoke`,6 条写入路径 + 3 个专项)

| 用例 | 结果 |
|---|---|
| direct 非 bind | `Err: 0`,落库 8 行 = 2 设备 × (5 ts + 3 ts);每设备 ts 覆盖 `{5,3}`、每 ts 设备覆盖 `{2,1}` |
| direct bind | 同上,`Err: 0`,8 行 |
| prepare 非 bind | `Err: 0`,落库 32 行 = 4 线程 × 8 行;每设备 ts 覆盖 `{5:4, 3:4}`、每 ts 设备覆盖 `{2:12, 1:8}` |
| prepare bind | 同上,`Err: 0`,32 行 |
| schemaless 非 bind(TLS) | `Err: 0`,落库 9 行 = 3 批 × 3 行;每设备 ts 覆盖 `{6,3}`(归一 `{2,1}`)、每 ts 设备覆盖 `{2:3, 1:3}` |
| schemaless bind(TLS) | 同上,`Err: 0`,9 行 |
| §9.3 概率(`probability: 0.5`) | `Err: 0`,落库 38/40 行;每设备 ts 覆盖 `{5:7, 3:1}` —— 既非全触发也非全不触发 |
| §9.4 缺整轮(`ts_count == batch_lines`,prepare) | `Err: 0`,落库 **0 行**;日志见 `WARN No batch rows prepared`(sampler 侧既有 `rowCount==0` 兜底) |
| §9.4 缺整轮(direct,补 fixture) | `Err: 0`,落库 **0 行**;JMX 含 `if (valuesSql.isEmpty())` + `-- no rows written for ` 兜底 |
| §9.4 缺整轮(schemaless,补 fixture) | `Err: 0`,落库 **0 行**;JMX 含 `vars.put('__missing_skipped','true')` + 断言 `vars.get('__missing_skipped')=='true'` 放行 |
| §9.5 空种子池 | 删掉行聚合 CSV → SetupTG `SharedMemoryLoader` 报错(`RuntimeException: SharedMemoryLoader: CSV file not found: ...`)+ Write 消费点二次抛业务异常(`SharedMemory pool empty for table ... (key ...): seed CSV load failed or produced no rows`)+ Write sampler NPE,共 5 条 error、`Err: 5 (62.50%)`、落库 0 行 —— 失败模式如实暴露,不再"全绿但没写数据" |

**smoke 断言已落成正式 pytest 用例**(2026-11-02):`tests/kwjdbc_svt/test_missing_smoke.py`,
11 个用例(6 条写入路径 + 概率 + 缺整轮 ×3 路径 + 空种子池),断言口径与上表逐条对应。
默认**跳过**(不需容器),opt-in 跑法::

    KWJDB_SVT_SMOKE=1 python -m pytest tests/kwjdbc_svt/test_missing_smoke.py -v

落成 pytest 的原因:断言口径原先只存在于临时驱动脚本里,重启即丢;落成用例后口径变更会随代码一起被 review。
两处**有意不做的断言**:①「每个 ts 的设备数」—— 多线程首批 baseTime 可能落在同一毫秒 → 两批次 ts 值相撞 → 该 ts 设备数翻倍,断言会随机翻车(等价事实已由"每设备 ts 覆盖数"覆盖);② JTL 的 `failureMessage` 内容 —— JMeter 对 JSR223 报错只写 `responseCode=500`,异常文本在 `jmeter.log`(空池用例的消息断言因此走 label 判定 + 落库行数)。

**零回归核验**(与基线 commit `e11f41d` 逐字节比对,6 处脚本 × `missing=None`)

| 路径 | 结果 |
|---|---|
| direct 非 bind / prepare 非 bind / prepare bind / schemaless 非 bind / schemaless bind | **去掉注释后逐字节一致**(差异只有本阶段统一精简的 Groovy 注释) |
| direct bind | 去掉注释后仅差 1 行 `def batchLines = 5` —— 该分支此前用了 `batchLines` 却从未定义,运行时会 `MissingPropertyException`;§6.3 的 direct bind 注入与 §9.2.2 的 smoke 都要求该路径可用,故补上 |

**遗留**

- `direct` 的 `ms_step` 仍取生成器默认值 `1000`,未按 model 的 `ts_col.ms_step` 解析(既有行为,与本次改动无关;`test_model.yaml` 的 `ms_step` 恰为 1000 故无差异)。
- `TestConfig.find_write_config()` 仍是大小写敏感的精确匹配(阶段 1 已记,未变)。
- 阶段 2 的代码与档案待 user review 后落 commit 2(`tasks.md` §7.4)。


### §2026-11-03 data-fill-query 预研:补值查询用例设计 + KaiwuDB 插值语义实测

**做了什么**

- 预研草稿 `openspec/specs/data-fill-query/pre-research.md` 就地更正 4 处不准确表述 + 追加「实测验证结论」一节(**草稿本身仍未入库**,按既有约定后续整理成 DCR 的 proposal/design/spec/tasks)。
- 新增场景配置 `docs/confs/test_model_shig_missing_fill.yaml` + `docs/confs/test_cfg_shig_missing_fill.yaml`:基线 = **不带 eximport 的 shig 配置**(原 12 条查询原样保留),retentions 库级/表级均 `1d`。
- `write_config` 开启 write-missing-data 缺值写入:`probability: 0.5` / `ts_count: 30` / `device_count: 0`。
- `query_config` 追加 **13 条**补值查询用例:interpolate/gapfill 组 7 条(每种聚合函数一条)+ FILL 子句组 6 条(每种模式一条);各用例独立线程组,间隔取 13 个互质素数分钟(17/19/23/29/31/37/41/43/47/53/59/61/67),全部 ≤ 1 次/15min。
- 缺陷工单 `docs/issues/interpolate-multi-projection-count.md` + 最小复现 `interpolate_multi_projection_repro.sql` / `.sh`。

**关键决策**

| 决策 | 理由 |
|---|---|
| 条数 7+6=13(不是预研写的 8+6) | `diff()` 是窗口函数不是聚合函数:`interpolate(diff(...) OVER (...), mode)` 被服务端拒(`the first parameter of interpolate must be agg func`),且与 `time_bucket_gapfill` 的 GROUP BY 不能同层(`window functions are not allowed in GROUP BY`) |
| interpolate 组按 7 种聚合函数定数 | 「最大集合量」原则:聚合函数(7) > 补值模式(5) > 数值类型(3) = 联合使用(3)。数值类型只有 3 种是因为 shig 两表没有 INT8/FLOAT8 列(时序类型全集 12 种,当前覆盖 5 种,缺口见「遗留」) |
| 补值模式按 5 种全覆盖 | constant / prev / next / linear / NULL 实测均可用,结果符合语义 |
| `missing.device_count` 取 0 | 缺失语义是「尾部截断 + 交集」:两维都配时**只有尾部设备**有空洞;而 interpolate 组按 `ptag_varchar_1` 分组、FILL 组固定查单台设备,要稳定命中缺口就必须让时间戳维度覆盖**全部**设备 |
| `missing.ts_count` 取 30 | 写节奏 60s/批、`batch_lines=60`×`ms_step=1s` ⇒ 每批本应覆盖 60s;截掉尾部 30 个时间戳后只覆盖 30s,与下一批之间留出**约 30s 时间轴空洞** —— 这正是补值要跨的缺口 |
| FILL 的 ts 用 `${__time(yyyy-MM-dd HH:mm:ss)}` | FILL 的 WHERE 只接受常量(`now()` / `NOW()-INTERVAL` 被拒 `only supports single column and constant`);实测 **JMeter 的 JDBC sampler 会替换查询文本里的 `${}`**(A/B:`${__time}` 正常执行、`'ZZZ-not-a-timestamp'` 60/60 报错)⇒ 动态 ts 无需改生成器 |
| gapfill 桶粒度取 `'10s'`(不是 `'1m'`) | 桶粒度必须**细于**空洞,否则空洞落在桶内部、桶不空 → gapfill 不补桶、interpolate 无从补起(**不报错,但不补任何东西**)。这属「按桶补行」的设计语义,**不是缺陷**,但文档未说明 → 已写进配置注释与工单「附带发现」 |
| 每条 SELECT 只用一个 `interpolate()` | 同列多 interpolate 且含 `count()` 时,`count()` 投影复用前一个投影的补值结果,返回类型在计划期(int8)与执行期(float8)之间漂移 → 已开工单 |

**踩的坑与修法**

| # | 坑 | 修法 |
|---|---|---|
| 1 | 预研文档的「8 种聚合函数」含 diff、「5 种数值类型」在 shig 模型上不成立 → 条数与覆盖都算错 | 实测后更正文档,条数 8→7,并在文档里写明差异原因与实测报错原文 |
| 2 | 场景基线取错(用了 eximport 变体:库级 retentions `7d`、无 `pub_sub_config`) | 改用不带 eximport 的 shig 配置为基线,retentions 统一 `1d` |
| 3 | 首主标签**没有种子文件**,`ptag_varchar_1 = ?` 落到兜底值 `device_1` 恒不匹配 | 过滤列改用有种子的 `ptag_varchar_2` / `rtag_varchar_1`;FILL 必须给全主标签且主标签只能写字面量 → 用 runtime 派生的 `'0_1'` |
| 4 | `?` 一律按 VARCHAR 绑定,数值列比较报 `unsupported comparison operator` | `?` 只绑 varchar 列;数值常量写进 SQL 字面量 |
| 5 | smoke 时把**写** throughput 也调成 2.0(30s/批),批次跨度与写节奏相等 → 尾部截断被抵消,缺口只剩 3.6s | 只加速查询、写节奏保持交付版的 1.0/分钟;重跑后缺口 29.5~31.8s |
| 6 | 一度把「桶粒度粗于空洞」当成服务端缺陷 | 复核后判定为设计语义(按桶补行),改记为使用约束 |
| 7 | 工单初稿写了未实测的 `SQLSTATE: 22003`,并把「JDBC 直接抛异常」当推断 | 删掉臆测的 SQLSTATE;JDBC 侧实测(3.3.1)为 `cached plan must not change result type`,两种协议症状分列;「调换顺序」这个绕法只在 CLI 有效,已显式标注 |

**验证证据**

- 缺口几何:设备 `0_1` 稳态**每批 30 行、批间缺口 29.5~31.8s**(`probability=1.0` 确定性变体)。
- 补值确实跨过空洞(空洞正中间 `2026-11-03 07:50:10`,两侧为 `07:49:54.437` / `07:50:25.353`):`EXACT→NULL`、`PREVIOUS→47064.02`(空洞前)、`NEXT→1145.46`(空洞后)、`CLOSER→1145.46`(就近)、`LINEAR→23948.79`(跨 31s 插值)。
- 端到端:两轮 `jmeter -n` 跑真实 shig 模型(写入并发进行),13 条补值用例共 117 样本 **0 失败**;`pytest tests/` 951 passed / 11 skipped。
- 缺陷:3.2.0(CLI)与 **3.3.1(CLI + JDBC)**均复现 → 未修复。

**遗留**

- `missing.probability` 暂取 0.5(完整数据与缺口数据两条路径都覆盖),是否改 1.0 待定。
- FILL 用例的 `ptag_varchar_1 = '0_1'` 绑死 `device_start=1` / `num_threads=20` / `device_per_thread=50`;多端扩展改 `device_start` 时需同步。
- 下一个 DCR(`data-fill-query`)尚未开:预研草稿仍是未跟踪状态,按既有约定不直接入库。
- 时序类型覆盖缺口(INT8 / FLOAT8 / BOOL / NCHAR / NVARCHAR / VARBYTES / GEOMETRY)待与需求方确认后再扩模型(BOOL / VARBYTES / NCHAR / NVARCHAR / GEOMETRY 的 `val_range` 种子生成路径尚未验证)。
- 缺陷工单待厂商响应。
