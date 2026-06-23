# KaiwuDB SVT 通用测试计划生成器规格说明书

## 1. 概述

### 1.1 目标

开发一个通用的 JMeter 测试计划生成器，用于通过配置文件自动生成 KaiwuDB 数据库的场景测试脚本。该生成器能够根据用户需求生成任意规模和业务模型的测试场景。

### 1.2 范围

- 支持生成关系库和时序库的混合测试场景
- 支持自定义表结构（列数、列类型、主键、Primary Tag 等）
- 支持多种写入方式，按排期分阶段实现：T0 单条/批量直接 INSERT 语句执行；T1 单条/批量 PreparedStatement；T2 无模式写入
- 支持多种查询模式（JOIN、WHERE、聚合、分页等）
- 生成标准 JMeter 测试计划（.jmx 文件）
- 支持使用多个JMeter端协同发压来增大测试压力

---

## 2. 功能需求

配置文件分为模型配置（test_model.yaml）和测试配置（test_cfg.yaml），均为 yaml 格式。

### 2.0 配置字段定义

#### test_model.yaml

**库级别字段**

- `rel_dbs`：关系库配置列表
- `ts_dbs`：时序库配置列表
- `name`：库名
- `if_not_exists`：是否使用 `IF NOT EXISTS` 语法
- `with_encoding`：字符集，可选，无此属性时建库语句中不包含 `WITH ENCODING` 表达式
- `comment`：库注释
- `retentions`：数据保留策略，时序库专用
- `partition_interval`：分区间隔，时序库专用
- `tables`：库下的表列表

**表级别字段**

- `name`：表名
- `comment`：表注释
- `if_not_exists`：建表是否使用 `IF NOT EXISTS`
- `with_hash`：Hash 分桶数，时序表专用
- `ts_col`：时序表时间戳列配置
  - `name`：时间戳列名
  - `type`：时间戳列类型
  - `ms_step`：时间戳步长，单位毫秒。基准时间为每个写入线程在所属 `ThreadGroup` 的 `JDBCSampler` 下挂载的 `JSR223PreProcessor` 中一次性获取，后续每条记录的时间戳 = 基准时间 + n × ms_step（n 为已发送的批次序号，从 0 开始）。若按批次写入（如每次 insert 100 行），则由该批次的所有记录平均分配一个 ms_step 区间，即每条记录递增 ms_step / batch_lines 毫秒
- `primary_key_count`：关系表主键列总数
- `data_col_count`：数据列总数（关系表和时序表共用）
- `primary_tag_count`：时序表主 tag 列总数
- `regular_tag_count`：时序表一般 tag 列总数
- `primary_keys`：关系表主键列类型配置列表
- `data_cols`：数据列类型配置列表（关系表和时序表共用）
- `primary_tags`：时序表主 tag 列类型配置列表，其值绑定到设备后固定不变，用于唯一标识时序数据源
- `regular_tags`：时序表一般 tag 列类型配置列表，其值在初始化时绑定到设备（由 primary_tags 的笛卡尔积唯一标识）后固定不变，写入时不随时间变化

**列类型定义字段（适用于 `primary_keys`、`primary_tags`、`regular_tags`、`data_cols` 下的列表条目）**

- `col_type`：列的数据类型
- `type_proportion`：该类型在对应列组总数中的占比，取值范围 `(0, 1]`，同一列组下所有类型的占比之和应等于 `1.0`。生成器根据 `type_proportion × 列组总数` 计算该类型的实际列数
- `val_range`：列值取值范围
  - 数值类型：支持 `>`、`<`、`=`、`>=`、`<=`、区间表达式（如 `[min,max]`、`(min,max)` 等），支持浮点数，`(` 和 `)` 为开区间，`[` 和 `]` 为闭区间。`=` 表示固定值，`seed_num` 仍参与种子缓存行数计算。整数类型使用开区间时，若区间内不存在合法整数值（例如 `(1,2)` 对 int 类型），生成器在生成阶段**报错**
  - 字符串类型：正则表达式，目前只支持 `[\u4e00-\u9fffa-zA-Z0-9-_]` 字符集范围，数据为测试前预生成，无性能要求，主外键需严格引用
  - 枚举类型：以 `enum:` 开头，多个值用逗号分隔，枚举值仅允许包含数字、大小写字母、常用汉字（`[\u4e00-\u9fffa]`）、中横线 `-` 和下划线 `_`，不再支持对逗号或其他特殊字符进行转义。枚举类型同样支持 `seed_num`，生成种子数据时从枚举值列表中**顺序循环选取**；当 `seed_num` 小于枚举值数量时，取前 `seed_num` 个值；当 `seed_num` 大于枚举值数量时，按列表顺序循环填充至 `seed_num` 个
  - 外键引用：以 `ref:` 开头，格式为 `ref:库名.表名.列名`。`ref` 仅约束该列的取值范围**必须落在被引用表对应主键列的取值枚举范围内**，不约束本表的 `seed_num`。本表仍可单独指定 `seed_num`，生成器从被引用表的主键种子数据中采样取值。具有主外键关系时，两表种子数据不隔离
- `seed_num`：该列类型需要生成的种子数据行数。生成器按各列的 `seed_num` 预生成**列种子文件**，在生成测试计划时同步输出到 `seeds/{table}/` 目录，供查询时 `?` 占位符采样使用。同一张表所有列的列种子文件按顺序逐个读取后，在 JMeter 运行时的 `SetupThreadGroup` 中拼接为**行种子数据总集**并放入共享内存，供后续写入线程组拷贝使用；行种子数据总集的行数等于该表所有列中最大的 `seed_num`，其余 `seed_num` 较小的列按自身种子顺序循环填充。写入时不再为每列单独随机采样，而是直接从共享的行种子总集中批量拷贝完整行。各表间非主外键种子数据隔离

  > **列种子文件命名约定**：`{列序号}_{列名}.{类型名}`，其中列序号按表中除时间戳列外的字段顺序从 1 开始自然数编号（如 `1_ptag_int8_1.int8`、`2_col_int8_1.int8`），读取时按列序号数值排序；类型名为规范化后的基本类型（不含长度/精度，如 `varchar` 而非 `varchar(10)`）。
- `nullable`：是否允许 NULL 值。`true` 表示列允许 NULL，且种子数据中将按 `null_rate` 比例填充 `null`；`false`（默认值）表示列不允许 NULL，DDL 生成时附加 `NOT NULL` 约束，种子数据中不包含 `null`
- `null_rate`：NULL 值在种子数据中的占比，取值范围 `[0.0, 1.0]`。仅当 `nullable` 为 `true` 时生效。`null` 数量 = `seed_num × null_rate`（四舍五入取整），生成的 `null` 值在列种子文件中逐行输出为 `null`（不区分大小写），且**计入 `seed_num` 总数**。NULL 值与非 NULL 值在种子文件中**随机打乱后输出**，使 `null` 均匀分散在整列种子数据中。`nullable` 为 `false` 时此字段无效，固定视为 `0.0`，且配置中若显式指定 `null_rate > 0.0` 视为非法；`nullable` 为 `true` 时 `null_rate` 允许为 `0.0`（允许 NULL 但占比为零，即实际不生成 NULL）

> **nullable 与 null_rate 示例**：
> - 某 `int4` 列：`seed_num=3`，`nullable=true`，`null_rate=0.33`，则生成 1 个 `null` 和 2 个固定随机值（如 `1`、`2`），列种子文件为（NULL 值打散后的一种可能分布）：
>   ```
>   1
>   null
>   2
>   ```
> - 某 `float4` 列：`seed_num=10`，`nullable=true`，`null_rate=0.2`，则生成 2 个 `null` 和 8 个固定随机值，列种子文件为（NULL 值打散后的一种可能分布）：
>   ```
>   0.0000000
>   null
>   1.0000000
>   2.0000000
>   null
>   3.0000000
>   4.0000000
>   5.0000000
>   6.0000000
>   7.0000000
>   ```
> - 某 `float4` 列：`seed_num=10`，`nullable=false`，`null_rate=0.0`（无效），则生成 10 个固定随机值，无 `null`：
>   ```
>   0.0000000
>   1.0000000
>   2.0000000
>   3.0000000
>   4.0000000
>   5.0000000
>   6.0000000
>   7.0000000
>   8.0000000
>   9.0000000
>   ```

> **列名生成规则**：列名按固定格式 `{列类型前缀}_{列数据类型}_{序号}` 生成，非完全随机。各列组内按 `type_proportion` 分配完实际列数后，按顺序编号（从 1 开始的正整数）。列类型前缀如下：
> - `col`：普通数据列（`data_cols`）
> - `ptag`：Primary Tag（`primary_tags`）
> - `rtag`：Regular Tag（`regular_tags`）
> - `pk`：关系表主键列（`primary_keys`）
>
> 示例：`col_int8_1`、`ptag_varchar_1`、`rtag_int4_5`、`pk_int8_1`

#### test_cfg.yaml

**库连接配置（`conn_config`）**

- `param_name`：参数名
  - `db_url`：连接数据库的url
  - `conn_pool_size`：连接池大小。该值由配置文件编写者（人或具备 JMeter 测试计划生成 Skill 的智能体）根据测试场景决定，一般建议设置为足够所有读写线程复用即可。该值会暴露为可调节的流水线参数，由实际测试确定
  - `device_start`：起始设备号基准，支持使用多个JMeter端进程横向扩展。多端协同时各表以此为基准独立计算各自的设备范围：某张表的下一发压端起始设备号 = 本端起始设备号 + 该表的 `num_threads` * 该表的 `device_per_thread`
  - `test_duration`：场景测试持续时间，单位秒。对应 JMeter 线程组的 `ThreadGroup.duration` 属性，也会暴露为可调整的流水线参数
- `default`：默认值

**写入配置（`write_config`）**

- `tbl_name`：表名，`all` 表示所有表使用相同的写入配置，每张表生成独立的写入线程组；若不同表需要不同的写入参数，则需分条目指定表名，每张表可独立配置
- `throughput`：单端目标写入吞吐量，单位次/分钟。每张表的写入线程组独立挂载 ConstantThroughputTimer，Timer 仅对该线程组生效
- `mode`：数据写入模式
  - `single_insert`：单条直接 INSERT 写入（T0）
  - `batch_insert`：批量直接 INSERT 写入（T0）
  - `single_prepared`：单条 PreparedStatement 写入（T1）
  - `batch_prepared`：批量 PreparedStatement 写入（T1）
  - `schemaless`：无模式写入（T2）
- `batch_lines`：批次写入记录条数，`batch` 和 `schemaless` 模式下可提供，未提供默认每批次写入 1 条
- `device_per_thread`：每线程负责写入的设备数，与连接池连接数（`conn_pool_size`）无关。每个线程独立负责一批设备，设备号按线程维度划分
- `num_threads`：写入线程组并发数，也可以设置为 `conn_pool_size`，大于 `conn_pool_size` 时所有写入线程和查询线程共享和复用连接

> **当前版本多表线程数约束**：当 `write_config` 分条目为不同表指定写入配置时，各表的 `num_threads` 必须保持相同。该限制用于简化每秒写入列数据数的计算与控制，并避免多张表使用不同 `num_threads` 时 JMeter 全局同名变量（如 `${num_threads}`）冲突的问题。后续版本将迭代支持按表独立指定 `num_threads`，届时通过表级独立变量名或线程组内常量值解决变量隔离。

> **多端协同时设备号计算**：每张表独立计算设备范围。表 T 的下一发压端起始设备号 = 本端起始设备号 + 表 T 的 `num_threads` × 表 T 的 `device_per_thread`。不同表的设备范围可以重叠（数据相互独立），同一表在不同端之间不重叠。

**查询配置（`query_config`）**

- `query`：查询 SQL 模板。SQL 中的列名（包括 SELECT、WHERE、JOIN、GROUP BY 等子句中的列）必须使用按**列名生成规则**生成的约定列名（如 `col_int8_1`、`ptag_varchar_1`、`rtag_float4_2`、`pk_int8_1` 等），不允许使用任意自定义名称。查询中的占位符 `?` 在测试运行时由生成器从对应列的**种子缓存文件**中读取并随机采样赋值；多参数查询时每个 `?` 从其关联列的种子缓存中独立均匀随机采样
- `throughput`：单端目标查询吞吐量，单位次/分钟。每个查询生成独立的查询线程组并独立挂载 ConstantThroughputTimer
- `num_threads`：查询线程并发数，不显式声明时默认值为 1

> **备注**：查询统一使用 PreparedStatement 执行，参数通过 SQL 中的 `?` 占位符绑定。生成阶段解析 `列名=?` 或 `表名.列名=?` 模式建立占位符与列种子缓存的映射；运行时由 `JSR223 PreProcessor` 从对应列的种子缓存中随机采样并注入 `queryArguments`。若占位符无法关联到具体列（如 `LIMIT ?`），生成器在生成阶段直接报错，拒绝生成测试计划。

test_model.yaml
```
rel_dbs:
  - name: iot_metadata
    if_not_exists: true
    with_encoding: utf-8
    comment: 工业互联网元数据库
    tables:
      - name: t_workshop
        if_not_exists: true
        comment: 车间表
        primary_key_count: 1
        data_col_count: 2
        primary_keys:
          - col_type: int8
            type_proportion: 1.0
            val_range: ">=1"
            seed_num: 5
        data_cols:
          - col_type: varchar(16)
            type_proportion: 0.5
            val_range: "^[\u4e00-\u9fffa-zA-Z0-9-_]{2,10}$"
            seed_num: 5
          - col_type: varchar(32)
            type_proportion: 0.5
            val_range: "^[\u4e00-\u9fffa-zA-Z0-9-_]{2,10}$"
            seed_num: 5
ts_dbs:
  - name: iot_monitor
    if_not_exists: true
    retentions: 3d
    partition_interval: 1d
    comment: 工业互联网时序监控数据数据库
    tables:
      - name: t_cnc
        if_not_exists: true
        retentions: 3d
        comment: 数控机床表
        with_hash: 100
        ts_col:
          name: ts
          type: timestamptz
          ms_step: 1000
        primary_tag_count: 2
        regular_tag_count: 2
        data_col_count: 4000
        primary_tags:
          - col_type: float8
            type_proportion: 0.5
            val_range: ">=1"
            seed_num: 10
          - col_type: int8
            type_proportion: 0.5
            val_range: "ref:iot_metadata.t_workshop.pk_int8_1"
            seed_num: 5
        regular_tags:
          - col_type: varchar(10)
            type_proportion: 1.0
            val_range: "^[\u4e00-\u9fffa-zA-Z0-9-_]{2,10}$"
            seed_num: 2
        data_cols:
          - col_type: int8
            type_proportion: 0.25
            val_range: ">=1"
            seed_num: 10
          - col_type: double
            type_proportion: 0.25
            val_range: ">=0.0"
            seed_num: 100
          - col_type: varchar(10)
            type_proportion: 0.25
            val_range: "enum:M1,M2,M3"
            seed_num: 3
          - col_type: varchar(2)
            type_proportion: 0.25
            val_range: "enum:O1,O2,O3"
            seed_num: 3
      - name: t_motor
        if_not_exists: true
        retentions: 3d
        comment: 电机振动监测表
        with_hash: 50
        ts_col:
          name: ts
          type: timestamptz
          ms_step: 500
        primary_tag_count: 1
        regular_tag_count: 1
        data_col_count: 100
        primary_tags:
          - col_type: int8
            type_proportion: 1.0
            val_range: ">=1"
            seed_num: 50
        regular_tags:
          - col_type: varchar(10)
            type_proportion: 1.0
            val_range: "enum:A1,A2,A3,A4,A5"
            seed_num: 5
        data_cols:
          - col_type: float4
            type_proportion: 0.5
            val_range: ">=0.0"
            seed_num: 20
            nullable: true
            null_rate: 0.1
          - col_type: float4
            type_proportion: 0.5
            val_range: ">=0.0"
            seed_num: 20
            nullable: false
            null_rate: 0.0
```

test_cfg.yaml
```
conn_config:
  - param_name: db_url
    default: jdbc:kaiwudb://127.0.0.1:26257/defaultdb
  - param_name: conn_pool_size
    default: 20
  - param_name: device_start
    default: 1
  - param_name: test_duration
    default: 604800
write_config:
  - tbl_name: t_cnc
    throughput: 60
    mode: batch_prepared
    batch_lines: 10
    device_per_thread: 10
    num_threads: 20
  - tbl_name: t_motor
    throughput: 30
    mode: batch_prepared
    batch_lines: 5
    device_per_thread: 5
    num_threads: 10
query_config:
  - query: "select last(col_float8_1) from iot_monitor.t_cnc where iot_monitor.t_cnc.ptag_varchar_1=?"
    throughput: 4
  - query: "select count(1) from iot_monitor.t_cnc where iot_monitor.t_cnc.ptag_varchar_1=? group by iot_monitor.t_cnc.rtag_varchar_1"
    throughput: 0.016666667
  - query: "select max(col_int_1),rtag_varchar_1 from iot_monitor.t_cnc left join iot_metadata.t_workshop on iot_monitor.t_cnc.ptag_int8_1=iot_metadata.t_workshop.pk_int8_1 where iot_monitor.t_cnc.ptag_int8_1=? group by rtag_varchar_1"
    throughput: 0.016666667
```

其中模型配置（test_model.yaml）用于生成数据库场景测试所需的建库建表语句以及向表写入数据时的模拟种子数据，测试配置（test_cfg.yaml）用于生成 jmx 测试计划中的初始化线程组、写入线程组及查询线程组中的测试采样器

> **写入范围说明**：关系表（`rel_dbs`）作为元数据表，仅在 `SetupThreadGroup` 中初始化写入一次（预生成全部种子数据后批量写入），不参与 `write_config` 中配置的持续发压；时序表（`ts_dbs`）为主要的性能测试对象，按照 `write_config` 配置持续写入。

### 2.1 数据列类型占比

数据列类型占比由配置中的 `type_proportion` 定义，表示某类型在对应列组（`primary_keys`、`data_cols`、`primary_tags`、`regular_tags`）总数中的占比。例如某表 `data_col_count` 为 4000，`data_cols` 中某类型的 `type_proportion` 为 0.25，则该类型实际生成 1000 列。各列组下所有类型的 `type_proportion` 之和应等于 `1.0`。该占比在生成 `test_model.yaml` 模板时由设计者或自动化工具（如 LLM skill）根据业务场景需求确定，生成器仅按配置精确实现。

### 2.2 吞吐量实现与线程组编排

生成器通过 JMeter 的 **ConstantThroughputTimer** 控制目标吞吐量，编排规则如下：

- **初始化线程组**：分为两个 `SetupThreadGroup`，均在普通线程组之前执行：
  - `SetupThreadGroup (DDL 执行)`：负责建库建表 DDL 以及关系表元数据种子初始化写入。
  - `SetupThreadGroup: 初始化共享内存种子区`**：使用**单线程**执行一次，为每张时序表从列种子文件拼接出完整的**行种子数据总集**，放入全局共享内存。所有写入线程共享同一块内存，不再按线程拆分，也不再使用单独的实时数据生成线程组。行种子总集的行数为该表各列 `seed_num` 的最大值，其余列按自身种子顺序循环填充；列数据按列种子文件名中的列序号顺序读取。
- **写入线程组**：每张表生成独立的写入线程组。`tbl_name: all` 时，所有表各自拥有独立的写入线程组，但共享相同的 `throughput`、`mode`、`batch_lines`、`device_per_thread`、`num_threads` 等配置值；若不同表需要不同的写入参数，则 `write_config` 中需分条目指定表名，每张表可独立配置 `throughput`、`mode`、`batch_lines`、`device_per_thread`、`num_threads`。写入线程组的 `JDBCSampler` 下挂载 `JSR223PreProcessor`，负责：
  - 每个线程首次执行时一次性获取基准时间；
  - 每次写入前，从该表共享的行种子总集中**随机取一个起始行号**，拷贝连续 `batch_lines` 行作为本次写入数据；若 `起始行号 + batch_lines` 超过总集行数，则从总集开头取剩余行（循环回绕）；
  - 在本地拷贝出的 batch 上**装配时间戳**（时间戳 = 基准时间 + n × ms_step），然后提交写入。
- **查询线程组**：`query_config` 中的每个查询条目生成独立的查询线程组，各自挂载独立的 ConstantThroughputTimer，以满足不同查询的不同频率需求。
- **Timer 作用范围**：ConstantThroughputTimer 挂载在线程组级别，仅对该线程组生效，不参与跨线程组的吞吐量分配
- **Timer 配置**：`calcMode` 固定为 `0`（This thread only），即每个线程独立计算目标吞吐量。`throughput` 参数值为该线程组总吞吐量除以线程数（`${throughput} / ${num_threads}`），每个线程承担均分后的吞吐量目标。示例如下：
  ```xml
  <ConstantThroughputTimer guiclass="TestBeanGUI" testclass="ConstantThroughputTimer" testname="吞吐量控制" enabled="true">
    <stringProp name="throughput">${__BeanShell(${write_throughput} / ${num_threads},)}</stringProp>
    <intProp name="calcMode">0</intProp>
  </ConstantThroughputTimer>
  ```
- **多端协同**：多 JMeter 端协同发压时，各端使用相同的测试计划（包括 throughput 配置），仅通过 `device_start` 参数划分各自负责的写入设备范围，实现横向扩展。单端 throughput 目标值不变，集群总吞吐量为单端吞吐量 × 端数。每张表独立计算设备范围：表 T 的下一发压端起始设备号 = 本端起始设备号 + 表 T 的 `num_threads` × 表 T 的 `device_per_thread`。不同表之间的设备范围可以重叠（数据相互独立），同一表在不同端之间保证不重叠。

> **多表写入线程数约定**：当前版本多张时序表的写入线程组共用全局 `${num_threads}` 变量，因此 `write_config` 分条目配置时各表 `num_threads` 必须相同。后续版本支持按表独立指定 `num_threads` 后，生成器将为每张表生成独立的变量名（如 `${t_cnc_num_threads}`）或在线程组内使用常量值，避免全局变量冲突。

---

## 3. 非功能需求

- 写入方式支持插件化扩展

---

## 4. 输出物

| 文件 | 格式 | 必填 | 说明 |
|------|------|------|------|
| 测试计划 | .jmx | 是 | JMeter 测试计划文件 |
| 列种子缓存文件 | 文本 | 是 | 每张表每列按 `seed_num` 预生成的种子数据，供查询时 `?` 占位符采样赋值以及运行时装配行种子总集。文件命名约定为 `{列序号}_{列名}.{类型名}`，列序号按表中除时间戳列外的字段顺序从 1 开始自然数编号，读取时按列序号数值排序；类型名为规范化后的基本类型（不含长度/精度） |

---

## 5. 依赖要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| python | 3.12+ | 脚本运行环境 |

---

## 6. 验收标准

### 6.1 功能验收

- [ ] 能够正确区分关系库和时序库
- [ ] 关系表正确生成主键，时序表正确生成 Primary Tag
- [ ] 各表数据列类型分布与 test_model.yaml 中的配置一致（允许±5% 偏差，由配置生成阶段保证）
- [ ] 生成的 JMX 文件可在 JMeter 5.5+ 中正确打开和执行
- [ ] 写入方式可扩展，新增策略无需修改核心代码

### 6.2 质量验收

- [ ] 配置错误有清晰的错误提示
- [ ] 代码测试覆盖率 > 80%

---

## 7. 未来扩展

| 功能 | 排期 | 说明 |
|------|------|------|
| PreparedStatement 写入 | T1 | T0 基础上提高写入性能 |
| 外键关系生成            | T1 | 支持更复杂的关联场景 |
| 支持无模式写入          | T2 | 模拟真实数据接入场景 |

---

## 8. 附录

### 8.1 KaiwuDB 数据类型参考

SQL 中数据类型名称大小写不敏感，生成器内部统一按全小写处理，输出 DDL 及模板中的类型名均为小写形式（如 `int8`、`varchar` 等）。

#### 关系表数据类型
- 数值类型：int2, int4, int8, float4, float8, decimal, serial
- 布尔类型：bool
- 字符类型：bit, bit(n), varbit, varbit(n), bytes, varbytes, char, nchar, varchar, nvarchar, collate, blob, clob
- 时间和日期类型：timestamp, timestamptz, date, time, interval
- JSON 类型：jsonb
- 数组类型：array
- INET 类型：inet
- UUID 类型：uuid

#### 时序表数据类型

**通用数据类型（所有列可用）**
- 时间类型：timestamp, timestamptz
- 数值类型：int2, int4, int8, float4, float8
- 布尔类型：bool
- 字符类型：char, varchar, nchar, nvarchar

**Tag 列类型限制（适用于 `primary_tags` 和 `regular_tags`）**
- 不支持 timestamp、timestamptz、nvarchar 和 geometry 数据类型
- 字符类型最大长度不超过 128 字节

**Primary Tag 类型额外限制（仅适用于 `primary_tags`）**
- Primary Tag 列总数最多不超过 4 个
- 所有 Primary Tag 列必须用 `NOT NULL` 约束定义，**不支持 `nullable` 属性（固定视为 `false`）**
- 不支持浮点类型（float4、float8）和除 varchar 之外的变长数据类型
- varchar 类型长度默认 64 字节，最大长度为 128 字节

> **nullable 默认值说明**：`primary_tags` 中 `nullable` 强制为 `false`；`regular_tags`、`primary_keys`、`data_cols` 中 `nullable` 默认值为 `false`，可在配置中显式指定为 `true`

### 8.2 KaiwuDB DDL 语法参考

#### retentions 优先级

时序表支持在库级别和表级别分别定义 `retentions` 数据保留策略。当库级与表级设置不一致时，**以表级别定义为准**。

例如，若数据库 `iot_monitor` 的 `retentions` 为 `3d`，而表 `t_cnc` 的 `retentions` 为 `5d`，则该表实际按 `5d` 的生命周期进行数据滚动。`SHOW CREATE TABLE` 语句显示的建表语句中会展示该表指定的 `retentions` 值（如未指定则显示默认值 `0s`），说明表的生命周期参数在创建表时即已确定。

#### WITH HASH

`WITH HASH(<hash_value>)` 是创建时序表时的可选参数，用于定义分布式集群中 HASH 环的大小，以决定最大 Range 分片数量。

**语法位置**：必须放在可选参数的最后位置，如：
`[RETENTIONS <keep_duration>] [DICT ENCODING] [COMMENT [=] <comment_text>] [WITH HASH(<hash_value>)]`

**参数说明**：
- `hash_value`：整数，取值范围 `[1, 50000]`，默认值为 `2000`
- 例如 `WITH HASH(100)` 表示最多可产生 100 个不同的 Range 分片

**性能影响与推荐配置**：
- HASH 值过小：多个设备的数据集中在少数 Range 中，形成写入热点
- HASH 值过大：Range 数量过多，增加管理开销

建议根据预期设备数量选择合适的 HASH 值：

| 预期设备数 | 推荐 HASH 值 |
|-----------|-------------|
| ≤ 1,000 | < 1,000 |
| ≤ 50,000 | < 5,000 |
| ≤ 1,000,000 | < 10,000 |

**示例**：
```sql
CREATE TABLE sensors (
    ts TIMESTAMP NOT NULL,
    value FLOAT
) TAGS (sensor_id INT NOT NULL)
  PRIMARY TAGS (sensor_id)
  WITH HASH(20);
```

#### KaiwuDB建库DDL

1. 语法：
CREATE TS DATABASE database_name [RETENTIONS keep_duration] [PARTITION INTERVAL interval] [COMMENT [=] comment_text];

2. 参数说明：
- keep_duration：直接写数值和单位（如 50d），无需加单引号，支持的时间单位有：
  + 天（D 或 DAY）
  + 周（W 或 WEEK）
  + 月（MON 或 MONTH）
  + 年（Y 或 YEAR）
- interval：直接写数值和单位（如 2d），无需加单引号
- 可选参数必须按照 [RETENTIONS ] [PARTITION INTERVAL ] [COMMENT [=] ] 的顺序配置

3. 正确示例：
CREATE TS DATABASE iot_monitor PARTITION INTERVAL 1d;

#### KaiwuDB建表DDL

1. 语法：
CREATE TABLE table_name (
    k_timestamp TIMESTAMP/TIMESTAMPTZ NOT NULL,
    column_name1 data_type1,
    column_name2 data_type2,
    ...
) TAGS (
    primary_tag data_type NOT NULL,
    tag_name1 data_type1,
    tag_name2 data_type2,
    ...
) PRIMARY TAGS (primary_tag);

2. 参数说明：

- 第一列必须是时间戳列，且列名必须为 k_timestamp，数据类型为 TIMESTAMP 或 TIMESTAMPTZ，且必须设置为 NOT NULL。
- 数据列（column_name）：存储时序数据的具体数值。
- 标签列（TAGS）：存储元数据信息（如设备 ID、地理位置等）。
- 主标签必须命名为 primary_tag，且数据类型必须为 VARCHAR，同时设置为 NOT NULL。

3. 正确示例：
CREATE TABLE meters (
    k_timestamp TIMESTAMP NOT NULL,
    current FLOAT,
    voltage INT,
    phase FLOAT
) TAGS (
    primary_tag VARCHAR NOT NULL,
    location VARCHAR(20)
) PRIMARY TAGS (primary_tag);

### 8.3 术语表

| 术语 | 说明 |
|------|------|
| SVT | Scenario Verification Test，场景验证测试 |
| Primary Tag | 时序表的主键列组，用于唯一标识时序数据源 |
| Stmt | JDBC Statement，标准 SQL 执行方式 |
| JMX | JMeter 测试计划文件格式 |

---

## 9. 修订历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.6 | 2026-06-18 | liujin | 按 design-review-2026-06-11 第 13 项，明确当前版本 `write_config` 分条目配置多表时各表 `num_threads` 必须相同，避免 JMeter 全局同名变量冲突；后续版本再迭代支持按表独立指定 `num_threads`。在 §2.0 写入配置和 §2.2 吞吐量实现中补充相关约束与约定 |
| 1.5 | 2026-06-16 | liujin | 重新设计共享内存种子机制：行种子数据总集仅在 `SetupThreadGroup` 中初始化一次，所有写入线程共享同一块内存；移除独立的实时数据生成线程组；写入线程从行种子总集中随机取起始行并拷贝连续 `batch_lines` 行，超出末尾时回绕到开头；列种子文件命名改为 `{列序号}_{列名}.{类型名}`；同步修订 §2.0、§2.2、§4 相关描述 |
| 1.4 | 2026-06-15 | liujin | 移除 `query_config` 的 `mode` 属性，查询不再支持 `statement`（将参数拼接到 SQL 语句中直接查询）模式，统一使用 `prepared_statement` 执行；在 §2.0 查询配置说明中增加备注，明确 `?` 占位符绑定规则及无法绑定时的报错行为 |
| 1.3 | 2026-06-10 | liujin | **设计阶段人工 review 发现的回溯修改**：列类型定义（`ColTypeConfig`）新增 `nullable`（bool）和 `null_rate`（double）两个属性。`nullable` 控制列是否允许 NULL 及 DDL 中是否生成 `NOT NULL` 约束；`null_rate` 控制种子数据中 NULL 值的占比，NULL 值计入 `seed_num` 总数。明确 `nullable=false` 时 `null_rate` 必须固定为 `0.0`。修订 §2.0 列类型定义字段说明及示例；修订 §8.1 Primary Tag 限制，明确 `primary_tags` 中 `nullable` 强制为 `false` |
| 1.2 | 2026-06-04 | liujin | 新增附录 8.2「KaiwuDB DDL 语法参考」，补充时序表库级与表级 `retentions` 优先级说明（以表级别定义为准），以及 `WITH HASH` 语法说明（参数含义、取值范围、性能影响与推荐配置） |
| 1.1 | 2026-06-03 | liujin | 允许 `write_config` 分条目指定表名时独立配置 `num_threads` 和 `device_per_thread`；明确多端协同时每张表独立计算设备范围；示例中增加 `t_motor` 表展示独立配置；明确写入时每列从各自种子缓存独立随机采样；枚举类型支持 `seed_num` 并定义顺序循环选取规则；明确 `ref` 不约束本表 `seed_num`；明确列名生成规则为 `{列类型前缀}_{列数据类型}_{序号}`；修订 8.1 数据类型参考，增加 Tag 列和 Primary Tag 的类型限制条件；修订查询配置定义，明确 SQL 中的列名须使用约定列名，`?` 占位符从列种子缓存文件采样赋值；输出物增加列种子缓存文件 |
| 1.0 | 2026-05-21 | liujin | 初始版本 |
