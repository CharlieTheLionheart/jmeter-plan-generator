# write-missing-data Specification

## Purpose
TBD - created by archiving change write-missing-data. Update Purpose after archive.
## Requirements
### Requirement: write_config 表级缺失配置

缺失配置 MUST 挂在**表**这一层。`test_cfg.yaml::write_config[]` 的每个条目锚定**一张具体的表**(`tbl_name` 取 `{db}.{table}` 形式),`missing` 段是该条目的一部分,只作用于这张表。

配置层级 MUST 呈现为:

```
test_cfg.yaml
└── write_config[]                    ← 数组,每个元素锚定一张表
    ├── tbl_name: {db}.{table}        ← 表级锚点,{db}.{table} 形式
    ├── mode / throughput / batch_lines / device_per_thread / num_threads
    └── missing                       ← 该表的缺失配置段(可选)
        ├── probability               ← 必填(段存在时)
        ├── ts_count                  ← 可选,缺省 0
        └── device_count              ← 可选,缺省 0
```

同一张表的其余写入参数与 `missing` 段 MUST 同属这一个条目,MUST NOT 拆到别处声明。一个条目 MUST 只作用于它锚定的那一张表,MUST NOT 扩散到同库或同 model 的其它表。MUST NOT 存在库级或全局层的缺失默认值 —— 每张表要么在自己的条目里声明 `missing` 段,要么完全不声明,同库其它表的声明不影响它。

每张表的缺失取值上界 MUST 按该表自身的 `batch_lines` / `device_per_thread` 判定,与其它表的配置无关。

#### missing 段的字段

| 字段 | 类型 | 必填 | 缺省 | 含义 |
|---|---|---|---|---|
| `probability` | float | 段存在时必填 | — | 每写入批次下缺失数据的概率 |
| `ts_count` | int | 可选 | `0` | 每轮从尾部截断掉的时间戳数 |
| `device_count` | int | 可选 | `0` | 每轮从尾部截断掉的设备 ptag 数(设备 ptag = 第一个 primary tag 列,运行时派生为 `deviceCode`) |

- `probability` MUST 取值于 `[0.0, 1.0]`:`1.0` = 必然缺失,`0.0` = 关闭缺失写入。
- `ts_count` / `device_count` MUST 取非负整数。
- `missing` 段 MUST NOT 出现 `probability` / `ts_count` / `device_count` 之外的字段。
- `missing` 段不存在 MUST 表示该表不做任何缺失 —— 缺失模拟是显式开启的能力,缺省配置下写入行为 MUST 与未引入本能力时完全一致。
- `missing` 段存在但 `ts_count` 与 `device_count` 均为 `0` MUST 被接受(合法,但无缺失效果)。
- `missing.probability` 为 `0.0` MUST 被接受(显式关闭缺失写入)。

#### 缺失维度绑定到表结构

缺失判定的两个维度 MUST 绑定到该表自身的结构:

- **设备维度** MUST 绑定到该表的**第一个 primary tag 列** —— 该列在写入时的值由运行时派生的 `deviceCode` 填充;
- **时间戳维度** MUST 绑定到该表的**时间戳列**(`ts_col`);
- 两个维度的"尾部" MUST 以**本轮网格内的相对下标**定义:设备下标 `0` = 本轮第一个设备,时间戳下标 `0` = 本轮第一个时间戳;
- MUST NOT 以表内的列序号定义尾部 —— 缺失对象是"本轮网格中的第几个设备 / 第几个时间戳",而非"表中的第几列"。

#### 缺失字段无作用对象的挂载点

- `missing` 段 MUST 配置在**具体表**的条目上。配置在 `tbl_name: all` 的通配条目上不生效 —— 通配条目不产生任何表级写入行为,其上的缺失配置无作用对象。
- `missing` 段 MUST NOT 配置在关系表(`rel_dbs`)的条目上 —— 关系表仅在 SetupTG 阶段一次性初始化写入,不存在持续写入路径,缺失配置无作用对象。

#### Scenario: 不声明 missing 段即不做缺失

- **WHEN** 用户在 `write_config[]` 条目中不声明 `missing` 段
- **THEN** 该表不做任何缺失,写入行为与未引入本能力时完全一致
- **AND** 配置解析不抛异常

#### Scenario: 显式声明完整 missing 段

- **WHEN** 用户配置 `missing: {probability: 0.5, ts_count: 2, device_count: 1}`
- **THEN** 解析后的配置逐字段等于用户声明的值

#### Scenario: missing 段存在但漏写 probability 被拒绝

- **WHEN** 用户配置 `missing: {ts_count: 2}`(未声明 `probability`)
- **THEN** 配置解析失败,错误消息含 `probability`
- **AND** 生成器在 fixture 解析阶段即失败,不产出 JMX

#### Scenario: missing 段存在但两个 count 均为 0 被接受

- **WHEN** 用户配置 `missing: {probability: 0.5}`(两个 count 均取缺省 `0`)
- **THEN** 配置解析通过,不抛异常
- **AND** 该表每轮都不跳过任何格子(无格子可缺)

#### Scenario: probability 为 0 表示显式关闭缺失写入

- **WHEN** 用户配置 `missing: {probability: 0.0, ts_count: 2}`
- **THEN** 配置解析通过,不抛异常
- **AND** 该表每轮都不跳过任何格子,落库行数与未配置缺失时一致

#### Scenario: 缺失段与该表的写入参数同属一个条目

- **WHEN** 用户为表 `iot_monitor.t_cnc` 配置 `mode: prepare`、`batch_lines: 5`、`device_per_thread: 2`、`missing: {probability: 0.5, ts_count: 2, device_count: 1}`
- **THEN** 写入参数与 `missing` 段写在同一个 `write_config[]` 条目内,`tbl_name` 为 `iot_monitor.t_cnc`
- **AND** 该表的缺失判定使用本条目 `missing` 段的 `ts_count=2` 与 `device_count=1`

#### Scenario: 一个条目只作用一张表

- **WHEN** 同一份 `write_config[]` 中表 A 声明 `missing: {probability: 0.5, ts_count: 2}`、表 B 不声明 `missing` 段
- **THEN** 表 A 少写 `2 × device_per_thread_A` 行
- **AND** 表 B 每轮仍写入 `device_per_thread_B × batch_lines_B` 行,行数不受表 A 影响

#### Scenario: 两张表配置不同形态的缺失策略

- **WHEN** 表 A 配置 `missing: {probability: 0.5, ts_count: 2, device_count: 0}`(仅缺时间戳),表 B 配置 `missing: {probability: 0.5, ts_count: 0, device_count: 1}`(仅缺设备)
- **THEN** 表 A 缺失其时间戳尾部 2 个下标下**所有设备**的行
- **AND** 表 B 缺失其设备尾部 1 个下标下**所有时间戳**的行
- **AND** 表 A 的缺失不影响表 B 的落库行数,表 B 的缺失不影响表 A 的落库行数

#### Scenario: 取值上界按各自表的参数判定

- **WHEN** 表 A 配置 `batch_lines: 3` + `missing.ts_count: 2`(合法),表 B 配置 `batch_lines: 10` + `missing.ts_count: 9`(合法)
- **THEN** 两张表均通过校验
- **AND** 若表 B 改为 `missing.ts_count: 10`,则仅表 B 的校验失败,表 A 不受影响

#### Scenario: 不存在库级默认值

- **WHEN** 同一库 `iot_monitor` 下表 A 声明了 `missing` 段,表 B 未声明
- **THEN** 表 A 按其 `missing` 段执行缺失,表 B 不做任何缺失
- **AND** 表 B 的行为不受表 A 的声明影响

#### Scenario: 配置在 all 通配条目上的 missing 段不生效

- **WHEN** 用户的 `write_config[]` 只有一条 `tbl_name: all` 的条目,其上声明了 `missing: {probability: 0.5, ts_count: 2}`
- **THEN** 该缺失配置不对任何表生效
- **AND** 生成器不因该配置产生任何表级写入行为

#### Scenario: 配置在关系表上的 missing 段无作用对象

- **WHEN** 用户为某张关系表配置了 `missing: {probability: 0.5, ts_count: 2}`
- **THEN** 该配置不影响任何写入结果(关系表无持续写入路径)

#### Scenario: 设备维度对应第一个 primary tag 列

- **WHEN** 表 `iot_monitor.t_cnc` 的第一个 primary tag 为 `ptag_varchar_1`,配置 `missing: {probability: 1.0, device_count: 1}`、`device_per_thread: 2`
- **THEN** 被跳过的是本轮第 2 个设备(其 `ptag_varchar_1` 值为该设备对应的 `deviceCode`)的全部行
- **AND** 被跳过的行数等于该表 `batch_lines` 的取值

#### Scenario: 时间戳维度对应本轮时间序列的尾部

- **WHEN** 表 `iot_monitor.t_cnc` 配置 `missing: {probability: 1.0, ts_count: 2}`、`batch_lines: 5`
- **THEN** 被跳过的是本轮第 4、第 5 个时间戳(`baseTime + 3 × ms_step` 与 `baseTime + 4 × ms_step`)对应的全部设备的行
- **AND** 被跳过的行数等于该表 `device_per_thread` 的取值

#### Scenario: 尾部不按表内列序号定义

- **WHEN** 表含多个 data 列且 `missing.ts_count: 1`
- **THEN** 被跳过的是本轮最后一个**时间戳**下所有设备的行,与该表有多少个 data 列无关

### Requirement: 缺失配置的取值校验

生成器 MUST 在配置解析阶段校验 `missing` 段的取值范围,越界时抛 `ValueError`,不进入 JMX 生成阶段:

| 字段 | 合法范围 | 越界后果 |
|---|---|---|
| `missing.ts_count` | `0 <= v <= batch_lines` | 超过总数 → 无效 |
| `missing.device_count` | `0 <= v <= device_per_thread` | 超过总数 → 无效 |
| `missing.probability` | `0.0 <= v <= 1.0` | 概率越界语义无定义 |

计数类字段取到**全量**(等于该表本轮的总时间戳数 / 总设备数) MUST 被接受 —— 缺失触发时该批次不写任何数据(**缺整轮**),这是合法的缺失形态。

`missing` 段存在但未声明 `probability` MUST 在解析阶段被拒绝 —— 该情形会让缺失永不触发,形成"配了缺失参数却完全不生效"的静默失效。

#### Scenario: missing.ts_count 等于 batch_lines 被接受(缺整轮)

- **WHEN** 用户配置 `batch_lines: 5` 且 `missing.ts_count: 5`
- **THEN** 配置校验通过,不抛 `ValueError`
- **AND** 缺失触发时该批次不写任何数据

#### Scenario: missing.device_count 等于 device_per_thread 被接受(缺整轮)

- **WHEN** 用户配置 `device_per_thread: 4` 且 `missing.device_count: 4`
- **THEN** 配置校验通过,不抛 `ValueError`
- **AND** 缺失触发时该批次不写任何数据

#### Scenario: 计数超过总数被拒绝

- **WHEN** 用户配置 `batch_lines: 5` 且 `missing.ts_count: 6`
- **THEN** 配置校验抛 `ValueError`,错误消息含 `ts_count`
- **AND** 生成器在 fixture 解析阶段即失败,不产出 JMX

#### Scenario: missing.probability 越界被拒绝

- **WHEN** 用户配置 `missing.probability: 1.5`(或 `-0.1`)
- **THEN** 配置校验抛 `ValueError`,错误消息含 `probability`

#### Scenario: 边界内取值通过校验

- **WHEN** 用户配置 `batch_lines: 5` + `missing.ts_count: 5` + `missing.probability: 0.5`、`device_per_thread: 4` + `missing.device_count: 4` + `missing.probability: 0.5`
- **THEN** 配置校验通过,不抛 `ValueError`

### Requirement: 缺失判定按尾部截断,设备与时间戳取交集

一轮(一次 Write TG sampler tick)产出的数据是 `device_per_thread` 个设备 × `batch_lines` 个时间戳的二维网格。当本轮执行缺失时,MUST 采用**尾部截断**方式确定缺失格子:

- 缺失设备 = 网格中设备下标最大的 `missing.device_count` 个(尾部);
- 缺失时间戳 = 网格中时间戳下标最大的 `missing.ts_count` 个(尾部);
- 一格 `(device_idx, ts_idx)` 被跳过 ⟺ 该格子的设备下标命中缺失设备 **且** 时间戳下标命中缺失时间戳(**交集**)。

缺失 MUST 由两个维度**分别判定**:

- **设备维度**:该格所属的设备是否落在被丢弃的设备尾部;
- **时间戳维度**:该格所属的时间戳是否落在被丢弃的时间戳尾部。

一格被跳过 MUST 当且仅当两个维度的判定结果**同时为真**(交集):

```
# 只对**已配置**的维度取交集(count=0 的维度未配置,不参与判定)
device_hit = device_idx >= device_per_thread - device_count     # device_count > 0 时
ts_hit     = ts_idx >= batch_lines - ts_count                     # ts_count > 0 时
skip(device_idx, ts_idx) = device_hit && ts_hit
```

某一维度的 count 为 `0` 时该维度**未配置**,**不参与判定**(既不命中、也不否决另一维)。

#### Scenario: 只配时间戳数 → 尾部时间戳下所有设备都缺

- **WHEN** 配置 `missing.ts_count=2`、`missing.device_count=0`、`device_per_thread=4`、`batch_lines=5`
- **THEN** 时间戳下标为 3 与 4 的**全部 4 个设备**的行都被跳过
- **AND** 时间戳下标为 0 / 1 / 2 的行全部照常写入

#### Scenario: 只配设备数 → 尾部设备在所有时间戳上都缺

- **WHEN** 配置 `missing.device_count=1`、`missing.ts_count=0`、`device_per_thread=4`、`batch_lines=5`
- **THEN** 设备下标为 3 的**全部 5 个时间戳**的行都被跳过
- **AND** 设备下标为 0 / 1 / 2 的行全部照常写入

#### Scenario: 两个维度都配 → 取交集

- **WHEN** 配置 `missing.device_count=2`、`missing.ts_count=2`、`device_per_thread=4`、`batch_lines=5`
- **THEN** 仅当设备下标 ∈ {2, 3} **且** 时间戳下标 ∈ {3, 4} 的格子被跳过,本轮被跳过的格子数为 `2 × 2 = 4`
- **AND** 命中缺失设备但未命中缺失时间戳的格子照常写入,反之亦然

#### Scenario: 缺失格子数固定为 M × N

- **WHEN** 配置 `missing.device_count=M > 0` 且 `missing.ts_count=N > 0`,`device_per_thread=D`、`batch_lines=B`
- **THEN** 本轮被跳过的格子数恒为 `M × N`
- **AND** 本轮实际写入行数为 `D × B - M × N`

#### Scenario: 设备下标为本轮内相对下标

- **WHEN** 配置 `device_start: 10`、`device_per_thread: 3`、`missing.device_count: 1`
- **THEN** 被跳过的设备是本轮第 3 个设备(绝对设备号 `12`),`device_start` 的绝对设备号语义不受影响

#### Scenario: 缺失只影响本轮,不影响后续轮次的网格结构

- **WHEN** 连续两轮都执行了缺失
- **THEN** 两轮的缺失位置相同(均由尾部下标决定),且两轮的网格结构(设备集合、时间戳序列)均与未配置缺失时一致

### Requirement: 缺失执行按概率触发,每写入批次判定一次

每一写入批次 MUST 至多做一次"是否执行本次截断"的判定:

- 判定为真时,本轮按"缺失判定按尾部截断"的要求跳过对应格子;
- 判定为假时,本轮全部格子照常写入(与未配置缺失时一致);
- `missing.probability = 1.0` 时每批次必然执行缺失;`missing.probability = 0.0` 时每批次都不执行(缺失写入被关闭);
- 判定 MUST 发生在写入线程内,各写入线程之间的缺失触发状态 MUST 相互独立 —— 当前语义为"各线程独立判定",不支持所有写入线程在同一批次同时缺失;
- 判定 MUST NOT 依赖跨线程共享状态。

#### Scenario: 概率为 1.0 → 每批次必然缺失

- **WHEN** 配置 `missing: {probability: 1.0, ts_count: 2}`
- **THEN** 每一批次都按尾部截断跳过对应格子

#### Scenario: 概率为 0.0 → 关闭缺失写入

- **WHEN** 配置 `missing: {probability: 0.0, ts_count: 2}`
- **THEN** 每一批次都不跳过任何格子,落库行数与未配置缺失时一致

#### Scenario: 概率为 0.5 → 每批次独立判定

- **WHEN** 配置 `missing: {probability: 0.5, ts_count: 2}`
- **THEN** 每批次以 0.5 的概率执行一次截断,不同批次之间判定结果相互独立

#### Scenario: 各线程判定相互独立

- **WHEN** 多个写入线程并发执行,配置 `missing.probability` 介于 0 与 1 之间
- **THEN** 各写入线程的缺失触发状态相互独立,一个线程触发缺失不影响其它线程
- **AND** 当前语义不支持所有写入线程在同一批次同时缺失

### Requirement: 缺失判定的每批次随机开销受限

缺失判定引入的随机调用 MUST 限制为每批次至多 1 次概率判定。缺失格子集合 MUST 由确定性的下标比较得出,MUST NOT 依赖随机抽样、随机排序或随机集合查找。

随机源 MUST 为线程安全且无跨线程争用的实现,不得因缺失能力降低写入吞吐。

#### Scenario: 每批次随机调用次数上界

- **WHEN** 配置 `missing: {probability: 0.5, ts_count: 2, device_count: 2}`
- **THEN** 每批次缺失判定只进行 1 次概率判定,不产生任何与缺失集合构造相关的随机调用

#### Scenario: 缺失集合构造不消耗随机数

- **WHEN** 连续多批次执行缺失且概率为 1.0
- **THEN** 每批次被跳过的格子位置完全相同(尾部下标决定),不随批次变化

### Requirement: 缺失能力覆盖全部写入路径

缺失判定 MUST 在全部 3 种写入 mode 生效,且每种 mode 的 `col_tag_bind_mode` 分支与非 bind 分支均生效:

| mode | 路径 | 分支 |
|---|---|---|
| `direct` | inline SQL INSERT | 非 bind / bind |
| `prepare` | PreparedStatement batch | 非 bind / bind |
| `schemaless` | REST InfluxDB Line Protocol | 非 bind / bind |

各路径 MUST 使用同一条判定式与同一套"本批次内相对下标"语义,落库效果一致。

#### Scenario: direct 模式生效

- **WHEN** 配置 `mode: direct` 且声明了 `missing` 段
- **THEN** 生成的 JSR223PreProcessor 脚本中包含缺失判定逻辑,被跳过的格子不进入 INSERT 的 `VALUES` 列表

#### Scenario: prepare 模式生效

- **WHEN** 配置 `mode: prepare` 且声明了 `missing` 段
- **THEN** 生成的 JSR223PreProcessor 脚本中包含缺失判定逻辑,被跳过的格子不进入 `batchRows`

#### Scenario: schemaless 模式生效

- **WHEN** 配置 `mode: schemaless` 且声明了 `missing` 段
- **THEN** 生成的 JSR223PreProcessor 脚本中包含缺失判定逻辑,被跳过的格子不进入 HTTP body 的 Line 列表

#### Scenario: bind 分支生效

- **WHEN** 配置 `col_tag_bind_mode: true` 且声明了 `missing` 段(任意 mode)
- **THEN** 对应 bind 分支的脚本中包含缺失判定逻辑

### Requirement: 缺失能力未启用时生成结果不变

当 `write_config[]` 条目未声明 `missing` 段,或声明了 `missing` 段但 `missing.probability = 0.0`(显式关闭缺失写入)时,生成器 MUST NOT 向 Groovy 脚本注入任何缺失逻辑,生成的 JMX 与未引入本能力时逐字节一致。

#### Scenario: 缺省 fixture 生成结果与基线一致

- **WHEN** 使用不含 `missing` 段的既有 fixture 生成 JMX
- **THEN** 生成的脚本内容与本能力引入前的基线逐字节一致(不含缺失判定相关标识符)

#### Scenario: probability 为 0 时同样不注入缺失逻辑

- **WHEN** 用户配置 `missing: {probability: 0.0, ts_count: 2}`
- **THEN** 生成的脚本内容与未声明 `missing` 段时逐字节一致(不含缺失判定相关标识符)
- **AND** 该表每一轮仍写入全部 `device_per_thread × batch_lines` 个格子

#### Scenario: 未声明 missing 段时不产生任何跳过

- **WHEN** 配置未声明 `missing` 段
- **THEN** 每一轮的全部 `device_per_thread × batch_lines` 个格子都写入,落库行数与未配置缺失时一致

### Requirement: 缺失不改变写入吞吐语义

缺失 MUST 只减少落库行数,MUST NOT 改变 `ConstantThroughputTimer` 的调度频率与 sampler 触发次数。被跳过的格子对应的行不落库,但该批次 sampler 仍照常触发与计时。

#### Scenario: 缺失后 sampler 触发次数不变

- **WHEN** 配置 `missing: {probability: 1.0, ts_count: 2}`,其余写入参数与不配置缺失时相同
- **THEN** 同一时间窗口内 Write TG 的 sampler 触发次数与不配置缺失时相同
- **AND** 落库行数减少,减少量等于被跳过的格子数

### Requirement: 缺整轮不产生非法写入

当缺失配置导致某批次没有任何格子被写入时(缺整轮:计数取全量;或运行时设备数小于配置的 `missing.device_count`),各写入路径 MUST NOT 产出非法写入语句,MUST NOT 把该批次判为写入失败:

- `direct`:MUST NOT 生成 `VALUES` 为空的 INSERT;
- `prepare`:MUST NOT 发起空的 JDBC 批次;
- `schemaless`:MUST NOT 因 body 为空而触发失败断言 —— 该情形 MUST 与"种子数据为空导致的空 body"区分开,后者仍 MUST 被断言捕获。

#### Scenario: direct 路径缺整轮时不产出空 VALUES

- **WHEN** `direct` 模式下某批次所有格子均被跳过
- **THEN** 不生成 `VALUES` 为空的 INSERT 语句
- **AND** 该批次记为写入成功(只是没有数据落库)

#### Scenario: prepare 路径缺整轮时不发起空批次

- **WHEN** `prepare` 模式下某批次所有格子均被跳过
- **THEN** 采样器跳过 JDBC 批次执行并记录告警日志
- **AND** 该批次不判为失败

#### Scenario: schemaless 路径缺整轮时不判失败

- **WHEN** `schemaless` 模式下某批次因缺失导致 body 为空
- **THEN** 该批次不触发失败断言
- **AND** 因种子数据为空导致的空 body 仍被断言捕获

#### Scenario: 运行时设备数小于缺失设备数时不产生空写入

- **WHEN** 运行时实际设备数小于 `missing.device_count`
- **THEN** 该批次仍写入非空数据,不产生 `VALUES` 为空的 INSERT / 空 HTTP body

