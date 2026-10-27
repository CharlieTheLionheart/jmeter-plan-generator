# Quality Review — write-missing-data(设计阶段)

> 本次 review 覆盖 proposal / design / specs 三份产物的一致性与完备性(编码尚未开始,实现阶段的验收指标见 tasks.md)。
> 记录格式沿用既有 change 的 review 约定(Status / Findings / Recommendations)。

## 1. 需求边界与语义完整性

**Status**: ✅ Pass

**Findings**: 三种思路(缺设备 / 缺时间戳 / 两者叠加)统一到**一条判定式**:设备维度与时间戳维度**分别判定**,两者同时命中才跳过该格(交集)。某一维度 count=0 时该维度视为全集(不构成约束),因此三种形态退化自洽:

| 配置 | 缺失形态 | 丢弃格数 |
|---|---|---|
| 只配 `ts_count` | 尾部 N 个 ts 下**所有设备**的行 | `N × device_per_thread` |
| 只配 `device_count` | 尾部 M 个设备在**所有 ts** 上的行 | `M × batch_lines` |
| 两个都配 | 交集(右下角 `M × N` 块) | `M × N` |

缺失维度绑定表结构(设备维度 = 第一个 primary tag 列,时间戳维度 = `ts_col`),尾部按**本轮网格相对下标**定义而非表内列序。

**Recommendations**: 无。

## 2. 三份文档的一致性

**Status**: ⚠️ Warning(已修正)

**Findings** —— review 过程中发现并已修正的不一致:

| # | 问题 | 处置 |
|---|---|---|
| 1 | **design 先于 spec 写**:design 初版基于随机抽样语义,spec 定稿为尾部截断,两者判定式冲突 | spec 先行,design 基于 spec 全文重写 |
| 2 | **判定式写法**:design/spec 写成单个合并布尔式,掩盖了"两维度独立判定"的结构 | 改为 `device_hit` / `ts_hit` 两行独立判定 + 交集 |
| 3 | **空维度的语义落地**:改写"分开判定"时一度写成 `count > 0 && ...`,会导致 count=0 的维度判定恒假 → **单维配置完全失效** | 修正为 `count == 0 || ...`(count=0 → 该维度恒命中 → 不构成约束) |
| 4 | **计数上界**:初版为 `<`(严格小于),把"缺整轮"挡在门外 | 放开为 `<=`,缺整轮成为取值的自然结果 |
| 5 | **概率比较**:`(missingProbability >= 1.0)` 的 ">" 分支不可达(值域被 `le=1.0` 封闭) | 改为 `== 1.0` |
| 6 | **`probability = 0.0` 仍注入**:脚本里留一段恒假死代码 | 改为不注入,行为与未声明 `missing` 段完全一致 |
| 7 | **配置形态**:初版为平级三字段,配了 count 忘配 probability 会静默失效 | 改为嵌套 `missing` 段,`probability` 必填 → 错误配置在语法上无法表达 |
| 8 | **表层级缺失**:spec 未说明配置归属哪一层,后期靠追加 Requirement 补丁 | Requirement 1 第一段前置表层级 + 层级图,补丁并回 |
| 9 | **design Non-Goals 措辞**:"不做缺整轮"读起来像"技术上做不到" | 改为"由计数取全量隐含表达,不提供独立开关" |
| 10 | **Risks 措辞**:以"不做 / 不改 / 未修"描述范围边界 | 改为能力边界声明(如"各线程独立判定,暂不支持全体同时缺失") |

**Recommendations**: 三份文档已逐条对齐,`openspec validate` 通过。

## 3. 性能开销

**Status**: ✅ Pass

**Findings**: 新增缺失判定的每批次随机调用**上界为 1 次**(概率判定),缺失格子集合由确定性下标比较得出,**不消耗随机数**。JDK 21 微基准确认 `ThreadLocalRandom.current()` 8 线程下 0.7 ns/call(无锁无争用),相对 `new Random()`(73.4 ns)+ `Math.random()`(141 ns,全局 CAS 争用)有量级优势。

更关键的是:既有路径的随机开销**远大于**新增功能 —— `direct` 两条路径在内层行循环里**每行**新建 `Random`,8 线程下约 1.5 μs/批次,是缺失判定总开销的千倍以上。因此 commit 1 把生成器 Groovy 脚本里的 7 处随机调用点**全量**替换(不刻意排除非热点处),让口径一致、不留"某个文件还没换"的认知负担。

**Recommendations**: `direct` 路径种子行选择从"每行独立随机"变为"每批次顺序取样",分布不变但**序列相关性上升**。已在 Risks 登记,若后续发现数据分布相关性问题需回退 commit 1。

## 4. 既有行为兼容性

**Status**: ⚠️ Warning

**Findings** —— commit 1 含三类既有代码修正,均改变失败模式:

| 修正 | 现状 | 改后 | 影响 |
|---|---|---|---|
| 空种子池(loader + 6 消费点) | loader 吞错误置空;1 处走到 `% totalRows` 除零 `ArithmeticException`;5 处 `log.warn` + 静默降级 | loader 抛异常中断;消费点抛业务异常直接退出 | **失败模式从"静默通过"变为"尽早报错"** —— 现状下测试会跑完全绿却一行数据都没写 |
| `write_config[]` 同表多条 | 无任何校验;JDBC 路径生成两个同名 TG(行数与 throughput 翻倍、缺失策略叠加),schemaless 路径后者覆盖前者(前一条静默丢弃) | 配置期拒绝(`tbl_name.lower()` 比较) | 现状两个结果都不是设计意图;由校验从源头消除分叉 |
| schemaless 大小写 | 建索引用 cfg 原样串、查询用 model 的 name,大小写不一致即匹配失败 | 统一 `to_lower` | 与 JDBC 路径的容忍度对齐 |

零回归保证:未声明 `missing` 段或 `probability = 0.0` 的条目,生成脚本与基线**逐字节一致**。

**Recommendations**: `write_config[]` 的"每表一条"语义由主 spec 示例与 `check_write_num_threads_consistency` 共同印证,本次以配置校验固化。若将来确需"同一张表多套缺失策略",需先定义多条目语义并另开 change。

## 5. 回滚方案

**Status**: ✅ Pass

**Findings**: 两个 commit 独立可回滚 —— commit 1(既有代码修正,与缺失功能零耦合)+ commit 2(缺失功能新增)。`git revert <hash>` 即可单独回滚任一 commit。删除配置里的 `missing` 段即回到现状(生成器不注入缺失逻辑)。主 spec 的字段表更新是 doc-only,可独立 revert。

**Recommendations**: 无。

## 6. 测试覆盖规划

**Status**: ✅ Pass(规划已就绪)

**Findings**: tasks.md 按 TDD 范式拆为 9 节 / 40+ 子 task,pytest 先行 → 编码 → 全绿 → 下一模块;模块切换有 pytest 全绿闸门。覆盖:配置模型(§4)、判定 helper 的 4 种形态含缺整轮(§5)、6 处装配点注入 + 零回归逐字节比对(§6)、集成层 .jmx 生成校验(§7)、配置校验硬化(§3)。

**Recommendations**: Phase B smoke(真实容器 `jmeter -n`)不在 pytest 内,走 `kwjdbc-jmx-smoke` skill;概率触发导致落库行数有统计波动,smoke 断言用区间而非精确等值。

## 7. Task 粒度与提交切分

**Status**: ✅ Pass

**Findings**: commit 1 = 随机源替换 + 空种子池失败模式修正 + 配置校验硬化(三者均为对既有代码的定点修正,合并为一个 commit);commit 2 = 缺失功能(新增能力)。既有代码修正先于功能改动落地,使功能 commit 的基线已是优化过的,避免"新增功能用了无锁随机源、老代码仍每行 new Random"出现在同一 diff。

每个 commit 前设**review 闸门**:验收通过后停下等 user review,收到信号再 commit / push。

**Recommendations**: 无。

## Overall Assessment

**Status**: ✅ Pass with Warnings

**Strengths**:

- 三种思路统一到一条判定式,单维/双维退化自洽,无需特例分支
- 缺失集合确定性(纯下标比较),每批次随机调用上界 1 次
- 配置形态用嵌套段 + `probability` 必填,从语法层消除"配了却不生效"的静默失效
- 表级归属在 spec 第一段即讲清,层级图明示
- 顺带修正三类既有缺陷(静默降级 / 同表多条 / 大小写),且与主功能解耦、独立可回滚

**Warnings**:

1. Phase B smoke(真实 KaiwuDB 容器)未跑 —— 编码阶段补
2. `direct` 路径种子行的序列相关性因随机源复用而上升(分布不变)—— 需在 smoke 中观察
3. 交集语义下缺失量小于字面直觉(`M × N` 而非 `M + N`)—— spec 已写明,示例配置需避免歧义措辞
4. 各写入线程的缺失判定相互独立,**不支持**"所有线程在同一批次同时缺失"—— 语义限制,已在 spec 与 design 声明

**Recommendation**: 进入编码阶段(tasks.md §1 起)。