# KWDB SVT 测试计划生成器规格 Review 记录

Review 日期：2026-06-02

---

## 严重矛盾

### 1. 写入方式的范围与示例/验收标准矛盾（已解决）

- 范围第13行说"当前仅支持 Stmt 方式，需预留扩展能力"
- 第7章未来扩展将 PreparedStatement 写入标为 P0
- 但 test_cfg.yaml 示例中 mode: batch_prepared 已是默认选项，且枚举值包含 single_insert/batch_insert/single_prepared/batch_prepared/schemaless
- 验收标准 6.1 第4条要求"写入方式可扩展，新增策略无需修改核心代码"

已明确排期：T0 单条/批量直接 INSERT；T1 单条/批量 PreparedStatement；T2 无模式写入。

---

## 关键语义不明确

### 2. "数据列类型占比"与显式配置矛盾（已解决）

2.1 节定义了"数据列类型占比"概念，似乎暗示生成器需要按占比自动分配列类型。
但 test_model.yaml 示例中每列的 type 都是精确指定的，不存在"占比"概念。
验收标准 6.1 第3条又说"允许±5%偏差，由配置生成阶段保证"。

问题：生成器是否支持两种配置模式？
- 模式A：用户显式指定每列类型（如当前示例）
- 模式B：用户只指定类型占比，生成器自动分配列类型

如果是模式A，"±5%偏差"这条验收标准没有意义，应删除或改为仅适用于模式B。

**解决措施**：统一采用模式B（按类型批量定义）。
- `data_cols` / `primary_tags` / `regular_tags` / `primary_keys` 下的条目统一改为 `col_type` + `type_proportion` + `val_range` + `seed_num` 的批量类型定义格式
- 表级别新增 `data_col_count`、`primary_tag_count`、`regular_tag_count`、`primary_key_count` 来声明各列组的总列数
- 列名由生成器按统一规则自动随机生成，配置中不再显式指定 `name`
- 各列组下所有 `type_proportion` 之和应等于 `1.0`，由配置生成阶段保证，因此删除原验收标准中"允许±5%偏差"的表述

### 3. 时序表时间戳生成机制不清晰（已解决）

ms_step 的语义（第64行）原文描述模糊：基准时间是一次性获取还是持续更新？batch 内时间戳是均匀分布还是严格递增？长期运行后时间戳是否会漂移？

已明确：基准时间为每个写入线程在测试启动时通过 BeanShell Sampler 一次性获取，后续每条记录的时间戳 = 基准时间 + n * ms_step（n 为已发送的批次序号，从0开始）。若按批次写入，则由该批次的所有记录平均分配一个 ms_step 区间，即每条记录递增 ms_step / batch_lines 毫秒。

### 4. device_per_thread 与连接池的关系模糊（已解决）

第113行注释："每连接负责写入的设备数"。

问题：这里说的是"每连接"还是"每线程"？JMeter 中 num_threads 是线程数，conn_pool_size 是连接池大小。如果 num_threads > conn_pool_size，多个线程复用同一个连接，那"每连接负责的设备数"是否 = device_per_thread * (num_threads / conn_pool_size)？还是说 device_per_thread 始终是按线程计算的，与连接复用无关？如果理解不一致，可能导致多端协同时设备号范围重叠或遗漏。

**解决措施**：明确 `device_per_thread` 为"每线程负责写入的设备数"，与连接池连接数（`conn_pool_size`）无关。每个线程独立负责一批设备，设备号按线程维度划分，连接复用不影响设备分配逻辑。

### 5. 多端协同设备号的计算口径（已解决）

第104行注释："下一发压端起始设备号 = 本端起始设备号 + 写入线程数 * 每线程写入设备数"。

问题：当 write_config 中有多张表（非 tbl_name: all）时，"写入线程数"是指单张表的线程数还是所有写入线程组的总线程数？不同表的设备范围是否有重叠风险？

**解决措施**：
- 明确 `write_config` 分条目指定表名时，每张表可独立配置 `num_threads` 和 `device_per_thread`
- 多端协同时，**每张表独立计算设备范围**：表 T 的下一发压端起始设备号 = 本端起始设备号 + 表 T 的 `num_threads` × 表 T 的 `device_per_thread`
- 不同表之间的设备范围可以重叠（数据相互独立，不同表的 primary_tags 代表不同实体），同一表在不同端之间保证不重叠
- 示例中增加 `t_motor` 表并展示两张表使用不同的 `num_threads` 和 `device_per_thread`

### 6. 种子数据的笛卡尔积范围未界定（已解决）

关系表示例中：workshop_id(5) * workshop_name(5) * address(5) = 125 行。

问题：
- 时序表每次写入一行时，data_cols 的值是从该列种子缓存中随机采样，还是按笛卡尔积预绑定到设备上？如果是预绑定，primary_tags 的笛卡尔积决定设备数，那 data_cols 的 seed_num 是否还参与计算？
- enum 类型没有 seed_num（如 maintenance_shift、operator_shift），写入时如何取值？是枚举列表中均匀随机选，还是顺序循环？
- 有 ref 引用的列（如 workshop_id），其 seed_num 是被引用的表决定的，本表是否还能单独指定 seed_num？

**解决措施**：
- 明确写入时**每列从各自种子缓存中独立均匀随机采样**，各列之间不绑定、不保持笛卡尔积对齐关系。`data_cols` 的 `seed_num` 与 `primary_tags` 的笛卡尔积无关，仅决定该列自身种子缓存的大小
- 枚举类型同样支持 `seed_num`，生成种子数据时从枚举值列表中**顺序循环选取**；当 `seed_num` 小于枚举值数量时取前 `seed_num` 个值；当 `seed_num` 大于枚举值数量时按列表顺序循环填充至 `seed_num` 个
- `ref` 仅约束该列取值范围必须落在被引用表对应主键列的取值枚举范围内，**不约束本表的 `seed_num`**。本表仍可单独指定 `seed_num`，生成器从被引用表的主键种子数据中采样取值

### 7. 查询占位符 ? 与列的映射规则未定义（已解决）

"占位符中的?的赋值从对应的列种子缓存数据中采样获取"。

问题：
- "对应"如何确定？是通过解析 SQL 文本提取 表名.列名=? 的模式吗？
- 复杂 SQL 怎么办？如 JOIN、子查询、别名（a.machine_model=?）、函数参数中的 ? 如何映射到具体列？
- 如果 ? 出现在无法关联到具体列的位置（如 LIMIT ?），生成器应该报错还是跳过？

**解决措施**：
- 查询 SQL 中的列名必须使用按约定规则生成的列名（`col_*`、`ptag_*`、`rtag_*`、`pk_*`），生成器通过解析 SQL 文本提取 `列名=?` 或 `表名.列名=?` 的模式确定映射关系。约定列名具有唯一性前缀，可直接匹配
- JOIN、子查询等复杂场景通过解析 `别名.列名=?` 模式，结合别名与表名的映射关系确定目标列；函数参数中的 `?` 同样通过其所在的 `列名=函数(..., ?, ...)` 上下文解析
- 如果 `?` 出现在无法关联到具体列的位置（如 `LIMIT ?`），生成器在生成阶段**报错**，拒绝生成测试计划

---

## 边界缺失

### 8. 关系表是否也受 write_config 控制（已解决）

规格大量描述了时序表的持续写入逻辑，但对关系表的写入行为几乎没有说明。

已明确：关系表（rel_dbs）作为元数据表，仅在测试启动阶段初始化写入一次，不参与 write_config 中配置的持续发压；时序表（ts_dbs）为主要的性能测试对象，按照 write_config 配置持续写入。

### 9. with_hash: 100 未说明（已解决）

时序表示例中出现 with_hash: 100，但全文没有任何解释。这是 KaiwuDB 的 WITH HASH 分桶数吗？100 的含义是什么？是否必填？

**解决措施**：`WITH HASH` 是创建时序表的可选参数，用于定义分布式集群中 HASH 环的大小，`hash_value` 为整数，取值范围 `[1, 50000]`，默认值为 `2000`。已在规格书附录 8.2 中补充语法位置、参数说明、性能影响与推荐配置。

### 10. 时序表库级与表级 retentions 的优先级（已解决）

iot_monitor 库有 retentions: 3d，t_cnc 表也有 retentions: 3d。如果两者不一致，以谁为准？

**解决措施**：以表级别定义为准。当库级与表级 `retentions` 不一致时，实际按表级设置进行数据滚动。`SHOW CREATE TABLE` 显示的建表语句中会展示该表指定的 `retentions` 值（如未指定则显示默认值 `0s`）。已在规格书附录 8.2 中补充说明。

### 11. val_range 语法边界（已解决）

- 数值型支持多种区间表示（>=1、[min,max] 等），但开区间 (min,max) 对整数类型怎么处理？例如 (1,2) 对 int 类型意味着没有合法值，是否要校验并报错？
- 枚举值转义规则：enum:M1,M2,M3 中用 \ 转义逗号，但 \ 本身用 \\ 转义。如果枚举值包含 : 怎么办？是否支持 enum: 前缀后的值中包含 :？

**解决措施**：
- 整数类型使用开区间时，若区间内不存在合法整数值（例如 `(1,2)` 对 int 类型），生成器在生成阶段**报错**
- 枚举值限定字符集范围，仅允许包含数字、大小写字母、常用汉字（`\u4e00-\u9fffa`）、中横线 `-` 和下划线 `_`，与 varchar 类型的生成字符范围保持一致。不再支持对逗号、冒号等特殊字符的转义，由此彻底规避枚举值解析歧义

### 12. regular_tags 与 data_cols 的写入行为差异（已解决）

在 KaiwuDB 中，regular_tags 是设备的静态属性，data_cols 是时序数据。规格没有说明：
- 写入时 regular_tags 的值是像 primary_tags 一样绑定到设备上固定不变，还是运行时随机变化？
- 查询时 regular_tags 是否可以出现在 WHERE 条件中？

**解决措施**：
- regular_tags 的值**绑定到设备上固定不变**，与 primary_tags 保持一致：每个设备（由 primary_tags 的笛卡尔积唯一标识）在初始化时分配固定的 regular_tags 值，后续写入中不随时间变化
- 查询时 regular_tags 和 primary_tags 均**可以出现在 WHERE 条件中**，但 query 属性中 SQL 模板的语法正确性由模板编写者或 KaiwuDB DDL Skill 保障，生成器不负责校验 SQL 语义合法性

---

## 建议补充的细节

13. 输出物表格过于简单，未包含 seed 数据、DDL 脚本。建议补充 seed 缓存文件、DDL 脚本到输出物列表。（已解决）

**解决措施**：
- 列种子缓存文件（供查询时 `?` 占位符采样）已在规格书输出物表格中补充
- 行种子数据在写入时由 JMeter 运行时从内存中的列种子缓存动态采样组装，不额外持久化输出，已在 `seed_num` 定义中补充说明
- DDL 脚本无需作为独立输出物，建库建表语句已内嵌于测试计划或由模板编写者保障

14. 附录 8.1 关系表类型有 INT8，但示例中用 int8。建议明确类型名是否大小写敏感。（已解决）

**解决措施**：SQL 中数据类型名称大小写不敏感，生成器内部统一按全小写处理，输出 DDL 及模板中的类型名均为小写形式。已在规格书附录 8.1 中补充说明。

15. throughput 在 JMeter 中是全局目标还是每线程目标。建议明确 ConstantThroughputTimer 的 CalculateThroughputBasedOn 设置（如 all active threads）。（已解决）

**解决措施**：ConstantThroughputTimer 的 `calcMode` 固定为 `0`（This thread only），每个线程独立计算并达到配置中 `throughput` 数值的目标吞吐量（**不**除以 num_threads）。线程组总吞吐量 = `throughput × num_threads`，集群总吞吐量 = `throughput × num_threads × 端数`。配置值即每线程目标，不存在均分。已在规格书 §2.2 中补充配置示例。

16. conn_pool_size 在多个 JDBC Connection Configuration 间如何共享。建议明确每个线程组独立配置连接池还是共享连接池。（已解决）

**解决措施**：`conn_pool_size` 由配置文件编写者（人或具备 JMeter 测试计划生成 Skill 的智能体）根据测试场景决定，一般建议设置为足够所有读写线程复用即可。该值会暴露为可调节的流水线参数，由实际测试确定。已在规格书 `db_config` 定义中补充说明。

17. test_cfg.yaml 中 db_config 定义了 test_duration 参数（第107行，默认 604800 秒），该参数在 JMeter 中如何体现（Duration Assertion？Scheduler？）。建议明确是通过 Thread Group 的 Duration 字段还是其他方式控制。（已解决）

**解决措施**：`test_duration` 对应 JMeter 线程组的 `ThreadGroup.duration` 属性，也会暴露为可调整的流水线参数。已在规格书 `db_config` 定义中补充说明。
