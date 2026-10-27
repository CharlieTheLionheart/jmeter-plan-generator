# write-missing-data — Design

## Context

### 当前写入机制

kwjdbc-svt 的 3 种写入 mode(`write_config[].mode`)最终都落到同一个运行时形态:**一次 Write TG sampler tick(下称"一轮")= 一个 `device_per_thread` × `batch_lines` 的二维网格**,每个格子一行数据:

```
外层 for (int d = deviceStart; d < deviceStart + devicePerThread; d++)   // 设备维
    deviceCode = "${threadNum}_${d}"                                      // 第一个 primary tag
    内层 for (int r = 0; r < batchLines; r++)                             // 时间戳维
        ts = baseTime + r * ms_step                                       // 整步语义
        <写一行>
```

三条路径的具体落点:

| mode | 装配函数 | 分支 | 装配点 |
|---|---|---|---|
| `direct` | `write_groups.py::_build_inline_sql_preprocessor_script` | 非 bind | inline SQL `VALUES` 列表逐行拼接 |
| `direct` | 同上 | bind | `valsRows` 逐行拼接 |
| `prepare` | `write_groups.py::_build_batch_prepared_preprocessor_body` | 非 bind | `batchRows` 扁平 `List<Object[]>` |
| `prepare` | `write_groups.py::_build_batch_prepared_bind_preprocessor_body` | bind | per-device `rows` 列表 |
| `schemaless` | `rest_write_groups.py::_build_rest_write_preprocessor_script` | 非 bind | InfluxDB Line 逐行 append 到 `request_body` |
| `schemaless` | 同上 | bind | InfluxDB Line 逐行 append 到 `request_body` |

6 个装配点共享同一套"外层设备 / 内层时间戳"骨架,差别只在单行的表示形式(INSERT 值元组 / `Object[]` / Line Protocol 文本)。这决定了缺失能力可以在**同一个判定式**下注入到全部 6 处。

### 配置层级

`test_cfg.yaml::write_config[]` 是一个数组,每个条目锚定一张具体的表(`tbl_name` 为 `{db}.{table}` 形式),条目的 `mode` / `throughput` / `batch_lines` / `device_per_thread` / `num_threads` 都是这张表私有的。`WriteConfig` 经 `find_write_config(db, table)` 按 `{db}.{table}` 精确匹配被消费方取用(JDBC 路径逐条 `for wc in write_config` 生成 TG;schemaless 路径按 `db.table` 建索引)。**表级隔离在生成期天然成立**,缺失配置沿用同一套机制即可。

### 现有写入路径的随机开销

写入路径在挑选种子行时大量使用随机数,其中两处位于**内层行循环**内、每行新建随机源,构成实际热点(JDK 21 微基准,单位 ns/op):

| 随机源 | 单线程 | 8 线程并发 | 说明 |
|---|---|---|---|
| `new Random().nextInt(n)` | 33.8 | **73.4** | 每次 new 要收集熵 + 静态 seed CAS 争用 |
| `Random` 复用实例 | 8.2 | 1.2 | |
| **`ThreadLocalRandom.current()`** | **1.9** | **0.7** | 每线程独立 seed,无锁无争用 |
| `Math.random()` | 17.3 | **141.4** | 全局单例 CAS 争用,所有随机源里最慢 |
| 除法取余伪随机 | 0.4 | 0.3 | 最快但**不是随机**,退化成确定性周期 |

热点定位:

| 位置 | 现状 | 调用频次 | 8 线程成本 |
|---|---|---|---|
| `write_groups.py:252`(`direct` 非 bind) | `new Random().nextInt(total)` | **每行** | ~73.4 ns × 行数 |
| `write_groups.py:186`(`direct` bind) | `new Random().nextInt(rowValues.size())` | **每行** | 同上 |
| `write_groups.py:744`(`prepare` 非 bind) | `Math.random()` | 每批次 1 次 | 141 ns(全局争用) |

一处 `20` 行的批次在 8 线程下光这两处就花掉约 `1.5 μs`,是本 change 新增缺失判定总开销(1 次 0.7 ns)的**千倍以上**。

### 约束

- 缺失是**执行期**行为:生成器在 JMX 的 Groovy 脚本里写入判定逻辑,由每轮 tick 现场决定丢哪些格子。
- 缺失集合的构造 MUST 是确定性的(纯下标比较),随机只用于"本轮是否执行"这一次判定。
- `throughput` 是 `ConstantThroughputTimer` 的调度频率,sampler 触发次数不受缺失影响 —— 缺失只减少**落库行数**,不减少**SQL 触发次数**。

## Goals / Non-Goals

**Goals:**

- 让用户能按表配置"每轮少写多少个时间戳 / 多少个设备 ptag",两者同时配置时按交集生效。
- 让缺失的发生频率可配置(概率),表达真实链路上"偶发缺数"而非"每轮必缺"。
- 覆盖全部 3 种 mode 与 2 个 bind 分支,语义完全一致。
- 缺失配置的错误(漏写概率、越界) MUST 在解析期暴露,不留下"配了却不生效"的静默失效。
- 缺省配置下生成结果与现状逐字节一致。
- 顺带在同一个独立 commit 里修正既有代码的三类问题:全部随机调用点换 `ThreadLocalRandom`、空种子池尽早抛业务异常、`write_config[]` 同表唯一 + 大小写归一(均与缺失功能解耦,可独立回滚)。

**Non-Goals:**

- 不改变 `throughput` 的业务语义(缺失不减少 SQL 触发次数,只减少落库行数);缺失后**不做**速率补偿。
- 不改变 SetupTG 预烤的 SharedMemory 种子数据(缺失只在写入侧生效)。
- 不提供随机种子(seed)配置项,缺失不可复现是本期的既定取舍。
- 不提供"缺整轮"(某一轮一行都不写)的**独立开关** —— 该形态由 `missing.ts_count` / `missing.device_count` 取到全量隐含表达(计数允许等于总数),不需要额外开关。
- 不引入随机源抽象层(不新增 `RandomProvider` 之类),只做定点替换。

## Decisions

### D1:缺失判定 = 从后向前截断,设备与时间戳取交集

**决策**。一轮的网格是 `device_per_thread` 个设备 × `batch_lines` 个时间戳。当本轮执行缺失时:

- **从后向前截断**:设备维度丢弃下标最大的 `missing.device_count` 个,时间戳维度丢弃下标最大的 `missing.ts_count` 个。例如设备序列 `1、2、3、4、5` 截断 2 个 → 保留 `1、2、3`。
- **取交集**:一格 `(device_idx, ts_idx)` 被跳过 ⟺ 该格子的设备下标落在被丢弃的设备尾部 **且** 时间戳下标落在被丢弃的 ts 尾部。

判定由两个维度**分别进行**,各自产出一个布尔结果;一格被跳过 ⟺ 两个结果**同时为真**(交集):

```
device_hit = device_count == 0 || device_idx >= device_per_thread - device_count
ts_hit     = ts_count == 0 || ts_idx >= batch_lines - ts_count
skip(device_idx, ts_idx) = device_hit && ts_hit
```

某一维度的 count 为 `0` 时该维度的命中判定恒为真(不构成约束,视为全集),因此三种配置形态统一到同一套判定:

| 配置 | 缺失形态 | 丢弃格数 |
|---|---|---|
| 只配 `ts_count=2` | 尾部 2 个 ts 下**所有设备**的行 | `2 × device_per_thread` |
| 只配 `device_count=1` | 尾部 1 个设备在**所有 ts** 上的行 | `1 × batch_lines` |
| 两个都配 | 两者的**交集**(右下角 `M × N` 块) | `M × N` |

**备选方案**:

- **备选 A**:缺失集合用随机抽样(从本轮设备中随机抽 M 个、ts 中随机抽 N 个)。✗ user 明确要求简化:不必模拟到这么精细,随机抽样让实现复杂度与随机调用量都上一个台阶,表达能力却没增加。
- **备选 B**:两维度取**并集**(任一命中就丢)。✗ 与 user 明确要求的"取交集"相反。

**推论**:计数允许等于总数(`device_count <= device_per_thread`、`ts_count <= batch_lines`),因此**缺整轮**(该批次一行不写)是取值的自然结果,不需要独立开关。两维计数都取全量时,交集覆盖整个网格 → 该批次零行写入。缺整轮是合法配置,各路径的兜底见 D7。

### D2:概率触发 —— 每批次一次、per-thread

**决策**。每轮 tick 在进入双层循环前做一次伯努利判定(注入缺失逻辑时 `probability` 必然 ∈ `(0.0, 1.0]`,见 D6):

```
applyMissing = (missingProbability == 1.0) || (rnd.nextDouble() < missingProbability)
```

- 每批次判定一次(不是每格子一次)—— 与"每轮少写 N 个时间戳 / M 个设备"的表述粒度一致。
- 判定发生在写入线程内,各线程的 `nextDouble()` 序列互相独立,因此不同线程在同一时刻的缺失状态不对齐。这是概率语义的必然结果,符合"实际链路随机丢数"的建模需求。
- `probability = 1.0` → 每批次必然执行;`0.0` → 从不执行;`(0, 1)` → 每批次独立判定。
- **各线程独立判定**:每线程每批次各自判定一次,各线程的缺失触发状态互不影响 —— 这是本能力当前定义的语义。**暂不支持**"所有写入线程在同一批次同时缺失"的模拟:那需要跨线程的批次对齐与共享判定状态(各线程 tick 相位不同,"同一批次"没有可靠定义),不在本期范围。

**备选方案**:周期性参数(如"每 N 批次缺一次")。✗ user 明确选择概率表达;且周期性需要维护 per-thread 批次计数器,而概率只需一次 `nextDouble`。

### D3:配置形态 = 表级嵌套 `missing` 段

**决策**。缺失配置写成 `write_config[].missing` 嵌套段:

```yaml
write_config:
  - tbl_name: iot_monitor.t_cnc
    mode: prepare
    batch_lines: 5
    device_per_thread: 2
    missing:
      probability: 0.5      # 段存在时必填
      ts_count: 2           # 可选,缺省 0
      device_count: 1       # 可选,缺省 0
```

理由:

1. **消除静默失效**:嵌套后"配了 count 却漏配概率"在语法上无法表达 —— `probability` 是必填字段,漏写直接是解析错误。这比"平级 + 跨字段校验规则"更强:校验是解析期拦截,嵌套是错误配置写不出来。
2. **缺省语义单一开关**:"段不存在 = 不做缺失"。平级方案需要额外特例("两个 count 都为 0 → 视为关闭")。
3. **三个参数物理相邻**,读配置时不会漏看。
4. **为未来扩展留落点**:若将来要"设备维度常缺、时间戳维度偶缺"这类不对称概率,平级方案要往条目上摊字段,嵌套方案把 `probability` 升级成对象即可。

**与既有风格的差异**:`WriteConfig` 现有字段全是平级的(含 `col_tag_bind_mode` + `col_num_per_tag` 这对"开关 + 参数"组合)。嵌套段偏离这一风格,但那对先例本身就有同款静默失效(配了 `col_num_per_tag` 未开 mode 会被静默忽略),嵌套段代表的是更严谨的配置模式。本 change 不改动既有字段的写法。

### D4:随机源统一用 ThreadLocalRandom,并顺带修掉既有热点

**决策**。分两部分,**分成两个独立 commit**。

**(a) 缺失判定使用 `java.util.concurrent.ThreadLocalRandom.current()`**

不复用各写入路径现有的随机实现,也不使用除法取余伪随机。理由:

- 相对"除法取余伪随机":取余只快 0.4 ns/call,而缺失判定每批次只调 1 次,差异是 **0.4 ns/批次**,相对一轮写入的 μs 级开销完全不可测。取余伪随机还需要维护跨批次计数器(状态),且丢失"每批次独立判定"的随机性。**用 0.4 ns 换语义不划算。**
- 相对 `new Random()`:`new Random()` 每次要收集熵(单线程 32.7 ns)+ 静态 seed CAS 争用(8 线程 73.4 ns),是所有合法随机源里最贵的。
- `probability == 1.0` 时走常量分支,**不产生任何随机调用**。

**(b) 把生成器产出的 Groovy 脚本里的全部随机调用点换成 ThreadLocalRandom**

范围内是生成器 Groovy 脚本中的**全部**随机调用点(3 个文件 7 处),逐一定点替换,不做刻意排除:

| 文件 | 行 | 现状 | 改法 | 调用频次 |
|---|---|---|---|---|
| `write_groups.py` | `:186` | 内层循环内 `new Random().nextInt(rowValues.size())` | `ThreadLocalRandom.current().nextInt(...)` | 每行 |
| `write_groups.py` | `:252` | 内层循环内 `new Random().nextInt(total)` | 同上 | 每行 |
| `write_groups.py` | `:635` | 每批次 `def randomGen = new Random()` | `def randomGen = ThreadLocalRandom.current()`(后续 `randomGen.nextInt(...)` 调用点不变) | 每批次 |
| `write_groups.py` | `:744` | `startIdx = (int)(Math.random() * totalRows)` | 空池 → 抛业务异常直接退出;否则 `startIdx = ThreadLocalRandom.current().nextInt(totalRows)` | 每批次 |
| `rest_write_groups.py` | `:236` | 每批次 `def randomGen = new Random()` | `def randomGen = ThreadLocalRandom.current()` | 每批次 |
| `rest_write_groups.py` | `:329` | 同上 | 同上 | 每批次 |
| `query_groups.py` | `:489` | `lines.get((int)(Math.random() * lines.size()))` | `lines.get(ThreadLocalRandom.current().nextInt(lines.size()))` | 每次查询 |

替换一律**行为等价**:

- `new Random().nextInt(n)` → `nextInt(n)`:取值域同为 `[0, n)`,分布不变;变化仅在随机源从"每次新建(熵收集 32.7 ns + 静态 seed CAS 争用)"变为"每线程一个无锁实例"。
- `(int)(Math.random() * n)` → `nextInt(n)`:取值域同为 `[0, n)`,分布等价(`Math.random()` 底层是 `Random` 的 CAS 版本,`nextInt` 用 rejection sampling,两者都均匀)。

两处需要额外处理:

- `write_groups.py:744` 现状 `totalRows == 0` 时 `startIdx` 为 0,随后 `(startIdx + i) % totalRows` 会除零抛 `ArithmeticException`;直接换成 `nextInt(totalRows)` 会变成 `IllegalArgumentException`。替换时补 `totalRows > 0` 的三元早退,顺手消掉该除零隐患。
- `query_groups.py:489` 的 `lines_{param_idx}` 恒非空(`?: ['device_' + ...]` 兜底),`size() >= 1`,`nextInt` 不会因 0 抛异常,无需额外保护。

**提交切分**:

- commit 1 —— **既有代码修正**:随机源替换(7 处,行为等价)+ 空种子池失败模式修正(D11:loader 抛异常中断 + 6 个消费点抛业务异常)+ 配置校验硬化(D12:同表唯一 + 大小写归一)。三者都是对既有代码的定点修正,与缺失功能零耦合,可独立 review / 独立回滚。
- commit 2 —— 缺失功能(新增能力,依赖 commit 1 的干净基线)。

commit 1 **先于** commit 2 落地:让功能 commit 的基线已经是优化过的,避免"新增功能用了无锁随机源、老代码仍每行 new Random"出现在同一个 diff 里。

### D5:校验分两层

**决策**。

第一层 —— `MissingConfig` 自校验(Pydantic):

```python
class MissingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    probability: float = Field(..., ge=0.0, le=1.0)   # required:段存在时必填
    ts_count: int = Field(default=0, ge=0)
    device_count: int = Field(default=0, ge=0)
```

`probability` 用 `...`(required)实现"段存在则必填";`extra="forbid"` 实现"段内不得出现其它字段";`ge/le` 实现取值范围。漏写 `probability` 时的 Pydantic 错误消息天然含 `probability` 字样,满足 spec 的 Scenario 要求。

第二层 —— `WriteConfig` 跨字段校验(与 `batch_lines` / `device_per_thread` 的关系):

```python
@model_validator(mode="after")
def check_missing_counts_within_grid(self) -> "WriteConfig":
    m = self.missing
    if m is None:
        return self
    if m.ts_count > self.batch_lines:
        raise ValueError(
            f"missing.ts_count ({m.ts_count}) must be <= batch_lines ({self.batch_lines})"
        )
    if m.device_count > self.device_per_thread:
        raise ValueError(
            f"missing.device_count ({m.device_count}) must be <= device_per_thread ({self.device_per_thread})"
        )
    return self
```

**为什么不用外部 cross-ref validator**:两个 count 的上界依赖的是同一条 `WriteConfig` 内的 `batch_lines` / `device_per_thread`,不需要跨到 `TestModelConfig`,因此可以直接放 `@model_validator`。这与 `PubSubConfig` 把跨 model 的校验拆到外部 validator 的做法不同,原因是后者要查另一棵树。

**上界为什么是 `<=` 而不是 `<`**:计数取到全量时该批次零行写入(缺整轮),这是合法的缺失形态,由取值自然表达,不需要额外开关或额外校验规则。取"严格小于"会把一个语义完整的配置挡在门外,且让"缺整轮"变成需要专门论证的特例。

### D6:零回归 —— 缺失能力未启用时不注入

**决策**。生成器拼装 Groovy 脚本时,**仅当 `wc.missing is not None` 且 `wc.missing.probability > 0.0`** 时才插入缺失逻辑块:

- 未声明 `missing` 段 → 不注入(缺省零影响);
- `missing.probability == 0.0` → 不注入(显式关闭缺失写入,行为与未声明段完全一致)。

两种情况下生成的 JMX 与未引入本能力时逐字节一致。`probability == 0.0` 的显式声明不产生任何运行时开销,也不在脚本里留下恒假的死代码。

**副作用**:注入发生时 `probability` 必然落在 `(0.0, 1.0]`,因此运行时判定不必再检查 `probability > 0`(见 D2 / D8 的简化形式)。

### D7:缺整轮的处理

**决策**。计数取全量时,缺失触发会导致该批次零行写入 —— 这是合法配置而非错误,三条路径各自兜底,且都**不判为写入失败**:

- `direct` 两条路径:`rows` / `allSqls` 为空时,`insert_sql` 置为既有风格的注释串兜底(与 `allRows` 为空时同款),不产出 `VALUES` 为空的非法 INSERT。
- `prepare` 两条路径:sampler body 已有 `if (rowCount == 0) { log.warn(...); return }` 保护,跳过 JDBC 批次执行,不判为失败。
- `schemaless` 两条路径:body 为空会被既有 B1 断言捕获 —— 该断言原本用于捕获"种子数据为空"这类异常写入。需要区分两种空 body:preprocessor 在**因缺失导致**为空时置一个标记(如 `vars.put('__missing_skipped', 'true')`),B1 断言在该标记存在时放行;种子数据为空导致的空 body 不置标记,仍被捕获。这是本 change 对 schemaless 路径的唯一新增逻辑。

另有一条**运行时漂移**的边界:`device_per_thread` 是 UDV(`vars.get('device_per_thread')`),理论上可被外部改小于配置的 `missing.device_count`,此时阈值 `devicePerThread - missingDeviceCount` 可能 `<= 0` → 全部设备被丢。防御:当运行时设备数 `<= missing.device_count` 时,退化为"只按 ts 维度截断",保证至少留下时间戳维度未被丢弃的行(而不是直接 clamp 阈值 —— clamp 会静默改变缺失语义)。

注意这条防御与"缺整轮"是两回事:缺整轮是**配置显式取全量**(用户要的就是这一批没数据),而运行时漂移是**配置本意不是全量但运行时环境变了**,后者退化为部分截断以保住数据。

### D8:注入形态统一

**决策**。6 处注入的 Groovy 代码块形态一致:

```groovy
// write-missing-data DCR: 每批次按概率触发一次尾部截断(设备 × 时间戳,取交集)
def missingProbability = 0.5
def missingTsCount = 2
def missingDeviceCount = 1
def applyMissing = false
if (missingProbability == 1.0d) {
    applyMissing = true
} else {
    applyMissing = java.util.concurrent.ThreadLocalRandom.current().nextDouble() < missingProbability
}
def missingDeviceThreshold = devicePerThread - missingDeviceCount
def missingTsThreshold = batchLines - missingTsCount
// 两个维度分别判定,各自产出一个布尔结果;两者同时为真才跳过该格(交集)
// count 为 0 的维度恒命中 → 该维度不构成约束(视为全集)
def skipMissingRow = { int devIdx, int tsIdx ->
    boolean deviceHit = missingDeviceCount == 0 || devIdx >= missingDeviceThreshold
    boolean tsHit = missingTsCount == 0 || tsIdx >= missingTsThreshold
    return deviceHit && tsHit
}
```

调用位置与下标来源(设备下标一律取**本轮内 0-based 相对下标**,不是绝对设备号 `d`):

| 装配点 | 跳过判定插入位置 | 设备循环起点变量 | 设备下标 | ts 下标 | ts 循环变量 |
|---|---|---|---|---|---|
| `direct` 非 bind | 内层循环开头 | `localDeviceStart` | `d - localDeviceStart` | 内层计数 | `r` |
| `direct` bind | 内层循环开头 | `deviceStart` | `d - deviceStart` | 内层计数 | `r` |
| `prepare` 非 bind | 内层循环开头 | `deviceStart` | `d - deviceStart` | 内层计数 | `i` |
| `prepare` bind | 内层循环开头 | `deviceStart` | `d - deviceStart` | 内层计数 | `r` |
| `schemaless` 非 bind | 内层循环开头 | `deviceStart` | `d - deviceStart` | 内层计数 | `b` |
| `schemaless` bind | 内层循环开头 | `deviceStart` | `d - deviceStart` | 内层计数 | `b` |

调用形态统一为:

```groovy
if (applyMissing && skipMissingRow(devIdx, tsIdx)) { continue }
```

`&&` 的短路语义保证 `applyMissing` 为假时零额外开销(不调用闭包)。

**为什么用相对下标**:缺失集合的定义域必须与"本轮有哪些设备"严格一致。绝对设备号 `d` 的取值范围随 `device_start` / 多端协同变化,用相对下标则 `D` 与 `T` 的尾部语义在任何端都一致。

### D9:per-table 参数传递链路

**决策**。3 个缺失参数沿用现有"函数入参"风格逐层传递,不引入全局状态:

| 消费方 | 取值来源 | 传递方式 |
|---|---|---|
| `generate_write_thread_groups` | `wc.missing` | 调用装配函数时传 3 个标量参数 |
| `_build_inline_sql_preprocessor_script` | 入参 | 烘焙进 Groovy 块 |
| `_build_batch_prepared_preprocessor_body` | 入参 | 烘焙进 Groovy 块 |
| `_build_batch_prepared_bind_preprocessor_body` | 入参 | 烘焙进 Groovy 块 |
| `generate_rest_write_thread_group` | `wc.missing`(按 `db.table` 索引) | 调用 `_build_rest_write_preprocessor_script` 时传参 |

每个 `wc` 各自调一次装配函数,参数烘焙进该表 TG 的脚本 → 表级隔离在生成期天然成立,无需额外机制。

### D10:Python 侧 helper 与 Groovy 侧同构

**决策**。在 `src/utils/preprocessor_helpers.py` 提供一对同构实现:

- Python 版 `should_skip_row(device_idx, ts_idx, *, device_count, ts_count, device_per_thread, batch_lines) -> bool`:纯函数,两个维度分别判定后取交集,供单元测试直接验证判定式与边界;
- Groovy 版 `groovy_missing_data_decl(...)`:注入到 6 处脚本的代码块。

截断语义下判定式是纯比较,**不再需要任何随机源或集合操作**,Python 版无需 rng 参数 —— 这是相对早期"随机抽样"设计的最大简化。

### D11:空种子池一律尽早抛业务异常(上游 + 下游)

**决策**。种子 CSV 加载失败时,SetupTG 的 SharedMemoryLoader 吞掉异常并往 props 放空数组,写入侧因此拿到空的共享内存池。此时后续测试没有任何意义 —— 失败必须尽早暴露:

- **上游(loader)**:`SharedMemoryLoader` 在 CSV 文件不存在或加载过程抛异常时 MUST **抛异常中断**,不再 `log.error` + 置空数组;
- **下游(6 个消费点)**:池为空时 MUST 尽早抛出**带上下文的业务异常**并退出脚本,不得静默降级,也不得走到算术异常。

采用项目既有的运行时异常形态 `throw new RuntimeException(<描述>)`(与 `preprocessor_helpers.py` / `query_groups.py` / `rest_write_groups.py` 中 11 处一致,不新增异常类)。

loader 侧(`shared_memory_initializer.py` 的 Groovy 模板,两处):

```groovy
// ① CSV 文件不存在
if (!file.exists()) {
    throw new RuntimeException("SharedMemoryLoader: CSV file not found: " + csvPath)
}
// ② 加载过程抛异常
} catch (Throwable t) {
    throw new RuntimeException(
        "SharedMemoryLoader: failed to load CSV " + csvPath + ": " + t.getMessage(), t
    )
}
```

消费点侧:

```groovy
if (sharedRows == null || sharedRows.size() <= 0) {
    throw new RuntimeException(
        "SharedMemory pool empty for table " + tableName + " (key " + rowsKey + "): seed CSV load failed or produced no rows"
    )
}
```

注意 loader 抛异常后不再执行 `props.put(rowsKey, [])`,因此消费侧拿到的可能是 `null` 而非空数组 —— 判空 MUST 同时覆盖两者。

6 个消费点的现状与改法:

| 消费点 | 现状 | 改法 |
|---|---|---|
| `write_groups.py:743`(`prepare` 非 bind) | 无保护 → `:769` 的 `% totalRows` 除零 | 空池抛异常,直接退出 |
| `write_groups.py:227`(`direct` 非 bind) | warn + `insert_sql = "-- no rows in shared memory"` | 抛异常 |
| `write_groups.py:140`(`direct` bind) | warn + `insert_sql = "SELECT 1"` | 抛异常 |
| `write_groups.py:622`(`prepare` bind) | warn + 空 ArrayList | 抛异常 |
| `rest_write_groups.py:216`(`schemaless` bind) | warn + 空 body | 抛异常 |
| `rest_write_groups.py:295`(`schemaless` 非 bind) | warn + 空 body(靠 B1 断言捕获) | 抛异常 |

`tests/` 中无任何用例依赖这 6 处的空池早退行为(grep 0 匹配),改造成本低。

**与 B1 断言的关系**:`schemaless` 非 bind 原先靠"空 body → B1 断言捕获"暴露问题;改为抛异常后 sampler 直接 error(不再走 B1 断言),测试同样失败,但失败点更早、消息更明确。

**失败传播**:loader 抛异常 → SetupTG 的 JSR223Sampler 报 error → 后续写入/查询路径因池为空在消费点二次抛错 → 测试整体失败。这与现状的"loader 吞掉错误 + 全部 sampler 报成功 + 测试跑完显示全绿、实际一行数据都没写"有本质区别。

### D12:配置校验硬化 —— 同表唯一 + 大小写归一

**决策**。两条配置层面的修正。

**(a) 同表不可配置多条。** 在 `TestConfig` 的 `@model_validator(mode="after")` 中校验 `write_config[]` 内不得出现重复表,比较键为 `wc.tbl_name.lower()`(不区分大小写)。重复时抛 `ValueError`,在配置解析阶段失败。

理由:现状**没有任何重复校验**,而两条写入路径的驱动源不同,同表两条时行为不一致:

| 路径 | 驱动源 | 同表两条的后果 |
|---|---|---|
| JDBC(`direct` / `prepare`) | **配置条目驱动** —— `for wc in write_config`,每条目生成一个 TG | 生成两个同名 Write TG 并发写同一张表:落库行数与 throughput 翻倍,且缺失配置变成两套策略**叠加**而非择一 |
| `schemaless` | **model 的表驱动** —— 每张 ts_table 查一条配置 | `write_cfg_by_table[wc.tbl_name] = wc` 后者覆盖前者,前一条的缺失配置被**静默丢弃** |

两种结果都不是设计意图。主 spec 的 `write_config[]` 示例是每表一条(`t_cnc` / `t_motor`),且 `check_write_num_threads_consistency` 要求所有条目 `num_threads` 相同 —— 这条约束只在"多条目 = 多表并行发压"下才合理(各表均分实例线程数),若允许"同表多套配置",同表两套各要不同线程数很正常,不该被强制拉平。因此设计意图明确是**每张表一条**,由配置校验把它变成硬约束,而不是留给运行时行为去兜。

**(b) 大小写归一。** schemaless 路径建索引与查询统一用小写:`write_cfg_by_table[wc.tbl_name.lower()] = wc`,查询键 `f"{ts_db.name}.{ts_table.name}".lower()`。JDBC 路径已有 `wc.tbl_name.lower()` 归一化,schemaless 缺这一步 —— cfg 写 `IOT_MONITOR.T_CNC` 而 model 写 `iot_monitor.t_cnc` 时匹配失败,抛 `ValueError: missing write_config for ts_table`。归一后两条路径的大小写容忍度一致。

(a) 保证"一表一条",(b) 保证"一表能被找到"。

## Risks / Trade-offs

- **[概率参数导致落库行数不可精确断言]** → smoke 用统计口径断言(落库行数落在期望区间内),不做精确等值断言;单元测试只断言"脚本含缺失逻辑且判定式正确"。
- **[交集缺失量小于字面直觉]** → `ts_count=M`、`device_count=N` 同配时丢弃格数是 `M × N`(如 `2 × 1` → 丢 2/20 格 = 10%),而非 `M + N`。spec 的 Scenario「缺失格子数固定为 M × N」已把该口径写明;文档与示例配置中避免出现"缺 2 设备 + 缺 2 时间戳"这类会引发误读的措辞。
- **[随机源替换的收益集中在两处热点]** → 7 处里只有 `write_groups.py:186` / `:252`(每行一次 `new Random()`)与 `write_groups.py:744` / `query_groups.py:489`(`Math.random()` 全局 CAS 争用)有量级收益(8 线程下 73.4 ns/行 与 141 ns);其余 3 处 `new Random()` 每批次仅 1 次,收益约 32.7 ns 的熵收集。全量替换仍做,是为了口径一致、不留"某个文件还没换"的认知负担。
- **[随机源替换改变了种子行的序列相关性]** → `direct` 两条路径的种子行选择从"每行独立随机"变为"每批次一个随机源顺序取样"。**分布不变**,但同一批次内相邻行取到相邻种子的概率上升。若后续发现数据分布相关性问题,需回退 commit 1。`prepare` / `schemaless` / 查询侧三处的替换是分布完全等价的,无此风险。
- **[空种子池的既有失败模式不明确]** → 6 个消费点里 `prepare` 非 bind(`write_groups.py:743`)无任何保护,空池时 `startIdx` 为 0 后在 `:769` 的 `% totalRows` 处抛 `ArithmeticException: / by zero`;其余 5 处是 `log.warn` + 静默降级(不写数据但 sampler 报成功)—— 测试会"跑完全绿"却一行数据都没写。SetupTG 的 loader 更是直接 `log.error` + 置空数组把错误吞掉。本 change 的 commit 1 统一改为:loader 抛异常中断 + 消费点抛业务异常直接退出(见 D11)。
- **[同表多条的既有行为差异由配置校验消解]** → 现状 JDBC 路径同表两条生成两个同名 TG(落库行数与 throughput 翻倍、缺失策略变成叠加而非择一),schemaless 路径后者覆盖前者(前一条的缺失配置静默丢弃),两条路径不一致。commit 1 通过 D12(a) 在配置校验阶段拒绝同表多条,从源头消除该分叉;若将来确需"同一张表多套缺失策略",需先定义 `write_config[]` 的多条目语义,另开 change。
- **[schemaless 路径的大小写敏感由 commit 1 修正]** → 现状 schemaless 建索引用 cfg 原样字符串、查询用 model 的 name,两边大小写不一致时匹配失败(抛 `missing write_config for ts_table`),而 JDBC 路径有 `.lower()` 归一。commit 1 通过 D12(b) 统一 `to_lower`,消除该差异。
- **[注入点分散在 6 处,易漏改]** → 6 处共用同一段 Groovy 块与同一判定式;单测对 6 个装配点逐一断言"脚本含缺失逻辑块"。
- **[改动既有 Groovy 脚本影响既有行为]** → D6 保证未声明 `missing` 段时脚本逐字节不变;单测以"缺省 fixture 生成的脚本与改动前基线一致"作为回归闸门。

## Migration Plan

纯新增可选配置段,无数据迁移、无配置迁移。

- **启用**:在 `test_cfg.yaml::write_config[]` 中为需要的表声明 `missing` 段(`probability` 必填)。
- **回滚**:删除 `missing` 段即回到现状(生成器不注入缺失逻辑);既有代码修正是独立 commit,可单独回滚。
- **既有配置**:全部保持不变,行为不变。

## Open Questions

### 已收敛 ✅

1. 缺失判定用交集,单维配置时另一维视为全集 —— user confirmed, 2026-10-26。
2. 截断方式为**从后向前截断**(设备序列 `1、2、3、4、5` 截断 2 个 → 保留 `1、2、3`),不再用随机抽样 —— user confirmed, 2026-10-26。
3. 触发条件用概率,每批次判定一次 —— user confirmed, 2026-10-26。
4. 覆盖 `direct` + `prepare` + `schemaless` 三条路径(bind / 非 bind 均含)—— user confirmed, 2026-10-26。
5. 计数上界取 `<=`(等于总数即"缺整轮",是合法形态),超过总数在配置期拒绝 —— user confirmed, 2026-10-27。
6. 配置形态用表级嵌套 `missing` 段,段内 `probability` 必填;段名 `missing`;段存在但两个 count 都是 0 → 接受;`probability: 0.0` → 显式关闭 —— user confirmed, 2026-10-26。
7. 缺省概率 `0.0`(缺省不做缺失,缺陷模拟是 opt-in)—— user confirmed, 2026-10-26。
8. 随机源用 `ThreadLocalRandom`(基准:8 线程 0.7 ns/call,无锁无争用),不用除法取余伪随机 —— 依据见 D4。
9. **缺失后不做吞吐补偿**(缺失只减行数,不改变 sampler 触发频率,也不自动补发维持目标落库行数)—— user confirmed, 2026-10-26。
10. **各写入线程的缺失判定相互独立**,暂不支持"所有线程在同一批次同时缺失"的模拟 —— user confirmed, 2026-10-27。
11. **判定由设备维度与时间戳维度分别进行**,两者同时命中才跳过该格(交集)—— user confirmed, 2026-10-27。
12. **`missing.probability = 0.0` 时不注入缺失逻辑**(行为与未声明 `missing` 段完全一致,不留恒假死代码)—— user confirmed, 2026-10-27。
13. **既有代码修正与缺失功能分成两个 commit**,前者先落地;既有代码修正内部的三块(随机源替换 / 空种子池失败模式 / 配置校验硬化)合并在同一个 commit —— user confirmed, 2026-10-27。
14. **空种子池必须尽早抛业务异常**:上游 loader 不再吞错误置空(改为抛异常中断),下游 6 个消费点不再静默降级 —— user confirmed, 2026-10-27。
15. **同表不可配置多条**(`tbl_name.lower()` 比较,配置期 `ValueError`)+ **schemaless 路径大小写归一** —— user confirmed, 2026-10-27。
16. **D7 运行时设备数漂移防御**采用"退化为只按 ts 维度截断"(而非 clamp 阈值 + 告警),保住更多数据 —— user confirmed, 2026-10-27。

### 待 review ⏳

(无 —— 全部决策已闭环,进入 tasks 阶段。)
