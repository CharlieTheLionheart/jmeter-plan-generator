# jmx_skeleton_generator 模块实现问题清单

> 来源：对比 `docs/designs/kwdb-svt-test-plan-generator-design.md` 与 `docs/specs/kwdb-svt-test-plan-generator-spec.md`
> 生成时间：2026-07-08

---

## 🔴 严重（影响功能正确性）

### [严重-1] single_insert / batch_insert 模式完全跳过，无写入线程组
**文件**: `src/jmx_skeleton_generator/generators/write_groups.py:39-41`
**描述**: `write_groups.py` 中过滤掉了 `single_prepared` / `batch_prepared` 以外的所有模式（single_insert、batch_insert、schemaless），导致时序表在配置这些模式时完全不生成写入线程组。
**修复方向**: 将所有模式（single_insert、batch_insert、single_prepared、batch_prepared、schemaless）都纳入写入线程组生成逻辑，参考设计文档 §3.7 策略模式实现。
> **暂不修复原因**: 此问题依赖于 `strategies/` 策略模式模块的实现，而策略模式模块（严重-5）本身还未创建。递归分析后发现 `strategies/` 的实现又依赖于 `prepared_insert_template_generator` 和 `shared-memory-initializer` 等前置模块，需按依赖顺序实现。

严重-1 问题分析
问题代码：write_groups.py:120-121


for wc in write_config:
    if wc.mode not in ("single_prepared", "batch_prepared"):
        continue  # ← 这里跳过了 single_insert、batch_insert、schemaless
问题：过滤逻辑只允许 single_prepared 和 batch_prepared 通过，导致其他三种模式的写入线程组完全不生成。

修复方向：根据设计文档 §3.7 策略模式，需要将写入逻辑抽象为 5 种策略：

模式	策略类	实现方式
single_insert	SingleInsertStrategy	JDBCSampler 单条 INSERT
batch_insert	BatchInsertStrategy	JDBCSampler batch
single_prepared	SinglePreparedStrategy	JDBCSampler + 占位符
batch_prepared	BatchPreparedStrategy	JSR223Sampler + Groovy batch
schemaless	SchemalessStrategy	JSR223Sampler + LineProtocol
todolist 说明的依赖链：


严重-1 修复
    ↓ 依赖
write-strategies (严重-5 未实现)
    ↓ 依赖
prepared-insert-template ✅ 已实现
shared-memory-initializer ❓ 需确认

---

### [严重-2] batch_prepared 应使用 JSR223Sampler 而非 JDBCSampler（已修复）
**文件**: `src/jmx_skeleton_generator/generators/write_groups.py:63-68`
**描述**: batch_prepared 模式使用 `JDBCSampler`，但设计文档 §3.6 明确说明该模式需要真正的 JDBC batch（addBatch/executeBatch），必须使用 JSR223Sampler + Groovy 脚本。
**修复方向**: 参考设计文档 §3.6「JSR223Sampler（batch_prepared）」中的完整 Groovy 脚本，在 batch_prepared 模式下生成 JSR223Sampler 而非 JDBCSampler。

---

### [严重-3] batch_prepared 缺少 JSR223PreProcessor（已修复）
**文件**: `src/jmx_skeleton_generator/generators/write_groups.py`
**描述**: 设计文档 §3.6 明确要求 batch_prepared 模式下 JSR223PreProcessor 负责从共享内存行种子总集随机拷贝连续 batch_lines 行、装配时间戳和第一个 ptag，写入线程变量 `__BATCH_ROWS_${tableName}` 供 JSR223Sampler 读取。当前完全缺失。
**修复方向**: 参考设计文档 §3.6「JSR223Sampler（batch_prepared）」中的 JSR223PreProcessor 脚本，在写入线程组中为 batch_prepared 模式挂载对应的 PreProcessor。

---

### [严重-4] 缺少"初始化共享内存种子区" SetupThreadGroup
**文件**: `src/jmx_skeleton_generator/generators/skeleton.py`
**描述**: 设计文档 §2.2 线程组编排要求两个 SetupThreadGroup：(1) DDL 执行 + 关系表初始化；(2) 初始化共享内存种子区（单线程从列种子文件拼接行种子总集，放入 props 全局共享内存）。当前只实现了第一个。
**修复方向**: 在 skeleton.py 中添加第二个 SetupThreadGroup，参考设计文档 §5.2 阶段 1 的 Groovy 脚本，装配行种子总集并通过 `props.put("__SHARED_MEM_${tableName}", rows)` 存入全局共享内存。
> **暂不修复原因**: 此 SetupThreadGroup 的 JSR223Sampler 需要依赖 `shared-memory-initializer` 模块提供行种子总集装配逻辑，而该模块尚未实现。此问题需等 `shared-memory-initializer` 模块实现完成后再补充。

---

### [严重-5] strategies/ 策略模式完全不存在
**文件**: `src/strategies/`（目录不存在）
**描述**: 设计文档 §3.7 定义了完整的 WriteStrategy 抽象基类和 5 种策略（single_insert、batch_insert、single_prepared、batch_prepared、schemaless），以及 STRATEGY_REGISTRY 注册表。当前 src/strategies/ 目录完全不存在，所有写入逻辑堆在 write_groups.py 一个函数里，无法扩展。
**修复方向**: 按设计文档 §3.7 创建 strategies/ 目录，实现 WriteStrategy ABC 和 5 种策略，在 write_groups.py 中通过 STRATEGY_REGISTRY 调度。
> **暂不修复原因**: 递归依赖分析发现：策略模式的 `batch_prepared` 分支需要 `prepared_insert_template_generator` 模块提供 INSERT 模板，而该模块也是新实现且尚未完成。需要先实现 `prepared_insert_template_generator`，再实现策略模式，最后策略模式才能被 `write_groups.py` 使用。

---

## 🟠 高（影响测试运行）

### [高-1] throughput 双大括号字面量 bug（已修复）
**文件**: `src/jmx_skeleton_generator/generators/write_groups.py:58`
**描述**: `f"${{{{write_throughput}}}}"` 经 Python f-string 格式化后输出为字面字符串 `{{write_throughput}}`，不是有效的 JMeter 变量引用 `${write_throughput}`，导致 ConstantThroughputTimer 无法正常工作。
**修复方向**: 改为 `f"${{write_throughput}}"`（单层大括号在 f-string 中需双写）。

---

### [高-2] 查询 queryType 用 Select Statement 而非 Prepared Select Statement（已修复）
**文件**: `src/jmx_skeleton_generator/generators/query_groups.py:59`
**描述**: 设计文档 §3.6 要求所有查询统一使用 `Prepared Select Statement`，当前代码使用 `Select Statement`。
**修复方向**: `query_type="Prepared Select Statement"`。

---

### [高-3] 查询缺少 JSR223PreProcessor 参数绑定（已修复）
**文件**: `src/jmx_skeleton_generator/generators/query_groups.py`
**描述**: 设计文档 §3.6 要求每个查询 JDBCSampler 下挂载 JSR223PreProcessor，在运行时从列种子文件随机采样绑定 `?` 占位符。当前只有 JDBCSampler，参数绑定机制完全缺失。
**根因**: openspec 过程文档（spec.md + tasks.md）与设计文档（design.md §3.6）存在信息传递断层：spec.md 只要求"放 placeholder JDBCSampler"，从未定义 JSR223PreProcessor 参数绑定任务；tasks.md 的 task 6.x 也只规划了骨架。设计文档 §5.3 的 `bind_query_params(sql, tables)` 算法也有缺陷：`QueryConfig` 无 `tbl_name` 字段，但查询 SQL 本身包含 `db.table`，可直接提取。
**修复**: `query_groups.py` 已添加 `_extract_table_path()`（从 SQL FROM 子句提取 `db.table`）、`_replace_placeholders_with_vars()`（SQL 中 `?` → `${param_N}`）、`_build_query_param_script()`（Groovy 参数绑定脚本，通过 `*_{col_name}.csv` glob 模式定位种子文件）。openspec spec.md 和 tasks.md 亦同步修正，补充了完整的 JSR223PreProcessor 需求和 task 6.4。

---

### [高-4] 查询 throughput 除以线程数为设计错误（设计文档已修正）
**文件**: `docs/designs/kwdb-svt-test-plan-generator-design.md §3.6 ConstantThroughputTimer 小节`
**描述**: ~~设计文档要求 `throughput = ${throughput} / ${num_threads}`~~。经确认为设计错误：JMeter `ConstantThroughputTimer` 在 `calcMode=0`（Total throughput）下已自动在所有活跃线程间均分吞吐量，每线程独立计算时不需手动除以 `num_threads`。设计文档 §3.6 已修正为直接引用 `${write_throughput}` / `${read_throughput}`，`query_groups.py` 中的实现（直接引用 `${read_throughput}`）已正确，无需修改代码。

---

### [高-5] 缺少设备号计算逻辑（设计文档已修正职责边界）
**文件**: `docs/designs/kwdb-svt-test-plan-generator-design.md §3.6「多端设备号计算」小节`
**描述**: ~~设计文档要求在写入线程组 PreProcessor 中计算 `localDeviceStart = deviceStart + myIndex * devicePerThread`~~。经确认，设备号范围的**多 JMeter 实例间划分**属于调用方流水线的职责，测试计划生成器仅生成单一实例的测试计划。测试计划生成器应暴露 `device_start` / `device_per_thread` / `num_threads` 等 UDV 变量供调用方注入，而**实例内**的设备号计算（`localDeviceStart = deviceStart + threadIndex * devicePerThread`）在写入线程组 JSR223PreProcessor 中实现。
**修复方向（已修正）**: 设计文档 §3.6「多端设备号计算」小节已更新，明确职责边界：多端划分由调用方负责，实例内设备号计算在 PreProcessor 中实现。`write_groups.py` 中 batch_prepared 的 JSR223PreProcessor 已包含设备号计算逻辑（见 `BATCH_PREPARED_PREPROCESSOR_SCRIPT` 中的 `localDeviceStart` 计算）。

---

## 🟡 中（功能缺失或不一致）

### [中-1] schemaless 写入模式完全未实现（已修复）
**文件**: `src/jmx_skeleton_generator/generators/write_groups.py`
**描述**: schemaless 模式被 continue 跳过（与 single_insert/batch_insert 一样），设计文档 §3.7 给出了完整的 SchemalessWriteStrategy 实现说明。
**修复方向**: 实现 schemaless 写入策略，使用 JSR223Sampler + Groovy line protocol 格式。

---

### [中-2] QueryConfig.mode 字段应被移除但仍保留（已修复）
**文件**: `src/config_parser/models.py:333,343`
**描述**: 设计文档 v1.4 明确"移除 query_config 的 mode 属性，统一使用 prepared_statement"，但 config_parser/models.py 中 QueryConfig 仍保留 `mode: QueryMode` 字段。
**修复方向**: 从 QueryConfig 中删除 `mode` 字段及相关校验逻辑。

---

### [中-3] username/password 变量在 UDV 中缺失（已修复）
**文件**: `src/jmx_skeleton_generator/generators/test_plan.py:49-54` + `src/jdbc_datasource/jdbc_data_source_generator.py:81-82`
**描述**: 设计文档 §3.6 UDV 示例包含 db_username/db_password 两个变量，但 test_plan.py UDV 生成逻辑中未包含；jdbc_data_source_generator.py 中硬编码了 `"${db_user}"` 默认值，而 UDV 中从未定义该变量。
**修复方向**: (1) 在 UDV 中添加 db_username 和 db_password 字段（需同步修改 ConnConfig 模型）；(2) 或将 jdbc_data_source_generator.py 中的默认值与 UDV 实际生成的变量名对齐。

---

### [中-4] hashTree 层级结构与设计存在偏差（已修复）
**文件**: `src/jmx_skeleton_generator/generators/assembler.py:107-111`
**描述**: 设计文档 §3.6 给出了严格的 JMX 层级结构（component + hashTree 交替），当前 assemble 方法将所有 elements 平铺在 test_plan_hash 下，JDBCDataSource 自身的 hashTree 未被正确处理。
**修复方向**: 检查并修正 assemble() 方法中 hashTree 的嵌套关系，确保 JDBCDataSource、SetupThreadGroup、ThreadGroup 等每个组件后都有独立的 hashTree。

---

## 📋 修复优先级建议

模块依赖层次图（已实现标记）

第1层（底层基础）:  
┌─────────────────────────────────────────────────────────────────────────┐
│  utils ───────────────────────────────────────────────────────────────┐  │
│  ✅ 已实现                                                            │  │
│  ├── xml_helpers.py      ✅                                           │  │
│  └── val_range_parser.py ✅                                           │  │
└─────────────────────────────────────────────────────────────────────────┘  │
                                                                         │
第2层:                                                                    │
┌─────────────────────────────────────────────────────────────────────────┐  │
│  config-parser ────────────────────────────────────────────────────┐   │  │
│  ✅ 已实现  (严重-1 所在模块)                                        │   │  │
│  ├── models.py  ✅                                                   │   │  │
│  └── parser.py  ✅                                                   │   │  │
└─────────────────────────────────────────────────────────────────────────┘   │
                                                                         │
第3层:                                                                    │
┌──────────────┐ ┌──────────────────┐ ┌──────────────────────────────┐    │
│column-namer  │ │ ddl-generator    │ │ seed-data-generator          │    │
│✅ 已实现     │ │ ✅ 已实现        │ │ ✅ 已实现                    │    │
│              │ │ (严重-4, 严重-5) │ │                              │    │
└──────────────┘ └──────────────────┘ └──────────────────────────────┘    │
                                                                         │
第4层（中间层）:                                                          │
┌──────────────┐ ┌──────────────────┐ ┌────────────────────┐ ┌─────────┐ │
│shared-      │ │ jdbc-datasource  │ │ prepared-insert-   │ │         │ │
│memory-      │ │ ✅ 已实现        │ │ template ✅ 已实现 │ │         │ │
│initializer  │ │                  │ │                    │ │         │ │
│✅ 已实现     │ │                  │ │                    │ │         │ │
└──────────────┘ └──────────────────┘ └────────────────────┘ │         │ │
                                                          │         │ │
┌──────────────────────────────────────────────────────────┴─────────┴─┐ │
│  jmx-skeleton-generator ──────────────────────────────────────────┐   │ │
│  ✅ 已实现 (generators/ 目录存在)                                  │   │ │
└─────────────────────────────────────────────────────────────────────┘   │
                                                                         │
第5层（应用层）:                                                          │
┌──────────────────┐ ┌──────────────┐ ┌────────────────────┐ ┌─────────┐│
│ direct-insert-   │ │ write-       │ │ query-             │ │through- ││
│ write            │ │ strategies   │ │ functionality      │ │put-     ││
│ ❌ 未实现        │ │ ❌ 未实现    │ │ ❌ 未实现          │ │control  ││
│                  │ │              │ │                    │ │❌ 未实现││
└──────────────────┘ └──────────────┘ └────────────────────┘ └─────────┘│
                                        │                                  │
┌────────────────────────────────────────┴────────────────────────────────┐│
│  multi-end-coordination ──────────────────────────────────────────────┐ │
│  ❌ 未实现                                                             │ │
└────────────────────────────────────────────────────────────────────────┘│
                                        │                                   │
第6层:                         ┌─────────┴─────────┐                        │
│  main-entry ─────────────────│                   │────────────────────┘  │
│  ❌ 未实现                   │                   │                        │
└──────────────────────────────┴───────────────────┴───────────────────────┘
汇总
模块	状态	备注
utils	✅ 已实现	xml_helpers, val_range_parser
config-parser	✅ 已实现	严重-1 所在
column-namer	✅ 已实现	
ddl-generator	✅ 已实现	严重-4, 严重-5 所在
seed-data-generator	✅ 已实现	
shared-memory-initializer	✅ 已实现
jdbc-datasource	✅ 已实现	
prepared-insert-template	✅ 已实现	
jmx-skeleton-generator	✅ 已实现	
direct-insert-write	❌ 未实现	
write-strategies	❌ 未实现	
query-functionality	❌ 未实现	
throughput-control	❌ 未实现	
multi-end-coordination	❌ 未实现	
main-entry	❌ 未实现	
