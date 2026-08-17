---
comet_change: col-tag-bind-write
role: technical-design
canonical_spec: openspec
status: final
---

# col-tag-bind-write — 深度技术设计

## 1. Context

4000 列稀疏表（sparse fixture，commit `c14969f` / `9333117`）当前通过 `null_rate=0.99` + 全列 inline INSERT 实现"软稀疏"——但与生产负载的真实模式不符：

- **payload 浪费**：4000 列 INSERT + 99% NULL，wire/解析开销巨大；服务端要遍历全列做 NULL 处理。
- **缺语义**：实际生产里"设备 ↔ 列子集"是有意义的（设备 1 关心列 1-5，其他列对它无效），并非"全列都激活但 99% 是 NULL"。
- **路径不一致**：服务端 INSERT 路径与生产"按设备写相关列"的真实负载模式不匹配；smoke 结果无法代表生产性能。

本 DCR 引入"**列-tag 绑定写入模式**"：ptag 组合 → 映射函数 → 找到对应列子集 → inline INSERT 子集。与现有 5 种 `mode`（`single_insert` / `batch_insert` / `single_prepared` / `batch_prepared` / `schemaless`）**正交**，按 `write_config[].tbl_name` 项下**每表独立**配置 `col_tag_bind_mode` 开关。

约束（来自已有实现 + OpenSpec 收敛）：

- **列种子文件已存在**（`src/seed_data_generator/io.py` `read_column_seed` / `write_column_seed`，Orchestrator `_generate_table_seeds` 已调用），无需新增 IO。
- **行种子文件**（`{db}/{table}.csv`）是 row-aggregate，由 `build_row_aggregate` + `write_row_aggregate` 写入；列绑定模式应**跳过**此步骤。
- **KaiwuDB 部分列 INSERT 不需要列顺序匹配**（已查官网），只需值类型与列类型对应即可。
- **KaiwuDB 时序表 `ts` / `primary_tag` 通常 NOT NULL**；spec 约束要求 NOT NULL 列必须显式列入 INSERT。
- **现有 701+ pytest 不 regress**：`col_tag_bind_mode` 默认 `false`，所有现有 fixture 行为不变。

本 Design Doc 是 `openspec/changes/col-tag-bind-write/{proposal,design,specs}.md` 的**深度技术细化**，补充实现层细节、模块边界、Groovy 模板、测试策略与边界条件；不重写上游 OpenSpec 决策。

## 2. Goals / Non-Goals

**Goals**

- 新增每表独立 `col_tag_bind_mode` 开关：`write_config[].tbl_name` 项下新增 `col_tag_bind_mode: bool = False` + `col_num_per_tag: int = 0`。
- 启用时：Orchestrator 跳过该表**行种子文件**生成（`{db}/{table}.csv` 不写）；**列种子文件**复用现有 IO 继续生成。
- SetupTG **不生成 bind 表的行种子加载 sampler**（装配层 `seed_csv_paths` 过滤）：
  - `col_tag_bind_mode=false`：现有 SetupTG 行种子加载 sampler 不变（行为零修改）。
  - `col_tag_bind_mode=true`：装配层过滤，**完全不入** SetupTG 行种子加载器；改由新追加的 SetupTG **Bind sampler** 负责：加载列种子文件 + 按 `hash(ptag_tuple) mod num_threads` 初始化行内存，写到 `__SHARED_MEM_{db}_{table}_bind`。
  - bind 与全行 OR 关系：同一 test plan 中部分表 bind 部分表全行时，两种 sampler 共存（一个装全行表 props，另一个装 bind 表 props），命名空间隔离（`_bind` 后缀）。
- 写入 TG：ptag 组合 → `hash(ptag_tuple) mod num_threads` → 找到对应列子集 + 行值 → inline INSERT 子集列。
- INSERT 列名列表 = `ts` + 所有 `primary_tag` + 子集列名 + 显式 `NOT NULL` 的 `data_col`。
- 适用**所有 5 种 mode**（含 `schemaless`）。
- 列绑定表与全行表**可混合**（同一 test plan 中部分 sparse 列绑定 + 部分 rel 全行），用 `__SHARED_MEM_{db}_{table}` vs `__SHARED_MEM_{db}_{table}_bind` 命名空间区分。

**Non-Goals**

- 不改变 DDL 生成（DDL 仍是全列）。
- 不改造 sparse fixture 默认 `null_rate=0.99` 路径（保留做回归基线）。
- 不新增列种子文件 IO 接口（复用现有 `read_column_seed` / `write_column_seed`）。
- 不引入新 Python 第三方依赖（Groovy 运行时拼字符串）。
- 不重构 `_build_inline_sql_preprocessor_script` 函数签名（仅扩展入参 + 内部分支）。
- 不修复 `LoopController.loops=1` 导致 shig canonical smoke factory/workshop 行数为 0 的旧问题（与本 DCR 无关）。

## 3. Architecture & Data Flow

### 3.1 模块边界

```
+-------------------------------------------------------------------+
| config_parser/models.py::WriteConfig (新增字段)                   |
|   + col_tag_bind_mode: bool = False (per-table)                   |
|   + col_num_per_tag: int = 0 (per-table)                          |
+-------------------------------------------------------------------+
                          |
                          v
+-------------------------------------------------------------------+
| seed_data_generator/orchestrator._generate_table_seeds (修改)     |
|   + table.col_tag_bind_mode=true → 跳过 write_row_aggregate()     |
|   + 列种子文件继续生成（write_column_seed）                       |
+-------------------------------------------------------------------+
            |                                    |
            v                                    v
+--------------------------------+   +---------------------------------+
| write_column_seed (现有)        |   | write_row_aggregate (现有)      |
| → seeds/{db}/{table}/{idx}_    |   | → seeds/{db}/{table}.csv        |
|   {name}.csv (列种子)           |   |   仅 col_tag_bind_mode=false    |
+--------------------------------+   +---------------------------------+
            |                                    |
            v                                    v
+-------------------------------------------------------------------+
| SetupTG JSR223 Sampler × N（per-table 修改 + 追加新 sampler）     |
|   + 现有 sampler: 加载行种子 → __SHARED_MEM_{db}_{table}          |
|     (if table.col_tag_bind_mode: continue)                        |
|   + 新 sampler: 加载列种子 + hash 分组 → __SHARED_MEM_{db}_{      |
|     table}_bind (按 group_id 索引)                                |
+-------------------------------------------------------------------+
                          |
                          v
+-------------------------------------------------------------------+
| 写入 TG（修改 _build_inline_sql_preprocessor_script 入参）        |
|   + col_tag_bind_mode=false: 全行 INSERT (现状)                    |
|   + col_tag_bind_mode=true:                                      |
|     - ptag_tuple = (ptag_values)                                 |
|     - group_id = hash(ptag_tuple) mod num_threads                 |
|     - 列名列表 = __SHARED_MEM_..._bind[group_id].col_names        |
|     - 行值列表 = __SHARED_MEM_..._bind[group_id].row_values       |
|     - INSERT (ts, ptags..., col_subset...) VALUES (...)           |
+-------------------------------------------------------------------+
                          |
                          v
+-------------------------------------------------------------------+
| KaiwuDB server (DDL 全列，INSERT 子集列)                          |
|   + 未填列落默认值（NULL 或 NOT NULL 报错）                        |
|   + 性能收益：wire 体积 ~N×col_num_per_tag/data_col_count         |
+-------------------------------------------------------------------+
```

### 3.2 SetupTG 启动序列（列绑定 OR 全行）

```
[SetupThreadGroup, num_threads=1, scheduler, duration=60, loops=1]
  │
  ├─[A] 现有 JSR223PreProcessor (per-table, 行种子加载)   ← 加 if 分支
  │     读 seeds/{db}/{table}.csv → 写 props
  │       __SHARED_MEM_{db}_{table} (全行 List<List<String>>)
  │       __SHARED_MEM_{db}_{table}_columns (header)
  │     if table.col_tag_bind_mode:
  │         continue (跳过该表行种子加载)
  │
  ├─[B] 新增 JSR223PreProcessor (per-table, 仅 col_tag_bind 表)
  │     读 seeds/{db}/{table}/*.csv (列种子, 现有)
  │     按 ptag 注入 device_code 占位 → 拼 ptag_tuple
  │     group_id = hash(ptag_tuple) mod num_threads
  │     每组行数 = seed_num
  │     写 props
  │       __SHARED_MEM_{db}_{table}_bind
  │         = {group_id → {col_names: [...], row_values: [...]}}
  │
  └─[C] 现有 SetupTG 装配顺序保持 (Login + DDL pre-create
        HTTP or JDBC + SharedMemory) 零改动
```

混合表场景（如 sparse 列绑定 + rel 全行）：
- SetupTG [A] sampler 遍历所有表，col_tag_bind_mode 表跳过行种子加载；全行表正常加载行种子。
- SetupTG [B] sampler 仅遍历 col_tag_bind_mode 表，加载列种子 + hash 分组。
- 两个 sampler 并行存在（OR 关系，非互斥），各自命名空间不同。

### 3.3 写入 TG 模板（列绑定路径）

```
[ThreadGroup, num_threads=T, duration=test_duration, scheduler]
  │
  ├─ConstantThroughputTimer (write_throughput UDV)
  │
  ├─JSR223PreProcessor (Groovy: 列子集 INSERT)   ← 修改 _build_inline_sql_...
  │   // 1. 读 SharedMemory
  │   def rowsKey = "__SHARED_MEM_" + tableName.replace('.', '_') + "_bind"
  │   def bindGroups = org.apache.jmeter.util.JMeterUtils.getJMeterProperties()
  │       .get(rowsKey) as Map
  │   if (bindGroups == null || bindGroups.isEmpty()) {
  │       log.error("BindWrite: shared groups empty for " + rowsKey)
  │       vars.put("insert_sql", "-- empty bind groups")
  │       return
  │   }
  │
  │   // 2. 计算当前 ptag_tuple → group_id
  │   def ptagTuple = ptagValues as List  // 运行时取 device_code + 其他 ptag
  │   def threadCount = ctx.getThreadGroup().getNumThreads()
  │   def groupId = Math.abs(ptagTuple.hashCode()) % threadCount
  │
  │   // 3. 查组 → 取 col_names + row_values
  │   def group = bindGroups.get(String.valueOf(groupId)) as Map
  │   def colNames = group.get("col_names") as List
  │   def rowValues = group.get("row_values") as List
  │   def rowIdx = new Random().nextInt(rowValues.size())
  │   def cells = rowValues.get(rowIdx) as List
  │
  │   // 4. 拼 INSERT (ts + ptags + 子集列)
  │   def allCols = ["ts"] + ptagNames + colNames
  │   def tsStr = "'" + tsFmt.format(new java.util.Date(System.currentTimeMillis())) + "'"
  │   def ptagVals = ptagValues  // 注入
  │   def values = [tsStr] + ptagVals + cells
  │   def insert = "INSERT INTO " + tableName + " (" + allCols.join(",") + ") VALUES ("
  │              + values.join(",") + ")"
  │   vars.put("insert_sql", insert)
  │
  ├─JDBCSampler (Prepared Update Statement or Update Statement)
  │   Query: ${insert_sql}
  │
  └─ConstantThroughputTimer 维持 QPS
```

### 3.4 schemaless 路径集成（HTTP / InfluxDB Line）

```
[ThreadGroup (REST Write)]
  │
  ├─JSR223PreProcessor (Groovy: 拼 InfluxDB Line body, 子集列)
  │   // 1. 读 __SHARED_MEM_{db}_{table}_bind (与 SQL 路径同一 namespace)
  │   def bindGroups = ... get(rowsKey + "_bind") as Map
  │   def group = bindGroups.get(String.valueOf(groupId)) as Map
  │   def colNames = group.get("col_names") as List
  │   def rowValues = group.get("row_values") as List
  │
  │   // 2. 拼 InfluxDB Line（measurement, ptag=..., field=..., field=... ts）
  │   def line = buildLineSubset(measurement, ptagNames, colNames, rowIdx,
  │                               deviceStart, devicePerThread, ts)
  │   vars.put('request_body', line)
  │
  └─HTTPSamplerProxy (HTTP Write, POST ${rest_api.write_url_path})
      Body: ${request_body}
      customizedSslContext: ${rest_api.ca_cert_path} (仅 https_mode=tls)
```

**列绑定 vs 全行**：共享 SetupTG [B] sampler 写出的 `__SHARED_MEM_{db}_{table}_bind`，仅在写入 TG 的 PreProcessor 消费方式不同（SQL 拼 INSERT，REST 拼 InfluxDB Line）。

### 3.5 数据结构对比

| 模式 | SharedMemory key | Value 类型 |
|------|------------------|-----------|
| 全行（现有） | `__SHARED_MEM_{db}_{table}` | `List<List<String>>`（行为单位） |
| 列绑定（新增） | `__SHARED_MEM_{db}_{table}_bind` | `Map<String, Map>`（group_id → {col_names, row_values}） |

混合表场景：`__SHARED_MEM_db_t1`（全行）+ `__SHARED_MEM_db_t2_bind`（列绑定）共存于同一 JMeter `props`，互不冲突。

## 4. Implementation Details

### 4.1 `WriteConfig` 新增字段（`src/config_parser/models.py`）

签名扩展：

```python
class WriteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tbl_name: str
    mode: Literal["single_insert", "batch_insert", "single_prepared",
                   "batch_prepared", "schemaless"] = "batch_prepared"
    write_threads: int = 1
    write_throughput: Optional[float] = None
    batch_lines: int = 1
    # 新增 ↓↓↓
    col_tag_bind_mode: bool = False
    col_num_per_tag: int = 0
```

Pydantic 校验（`model_validator(mode="after")`）：

- `col_tag_bind_mode=true` 时 `col_num_per_tag > 0`：否则 `ValueError("col_num_per_tag must be > 0 when col_tag_bind_mode=true")`。
- `col_tag_bind_mode=true` 时**所有 5 种 mode** 都允许（含 `schemaless`），无 mode 限制。
- `col_tag_bind_mode=true` 时该表必须至少 1 个 `primary_tag`（在 main 入口检查，因为 TableConfig 不在 WriteConfig 内）。

约束说明：
- `col_num_per_tag > data_col_count` 由 main 入口校验（因为 WriteConfig 不知道 TableConfig 的 data_col_count，需 main 装配时查 model）。

### 4.2 Orchestrator 跳过行种子文件（`src/seed_data_generator/orchestrator.py`）

`_generate_table_seeds` 签名扩展：

```python
def _generate_table_seeds(
    db: DatabaseConfig,
    table: TableConfig,
    output_dir: Path,
    refs: dict[str, list[Any]],
    ref_paths: dict[str, Path],
    *,
    skip_row_aggregate: bool = False,  # 新增
) -> list[Path]:
```

行为：
- 列种子文件**始终生成**（与 `skip_row_aggregate` 无关）。
- `skip_row_aggregate=true`：跳过最后两步
  - `header, rows = build_row_aggregate(table_dir, first_ptag_info=first_ptag_info)`
  - `write_row_aggregate(aggregate_path, header, rows)`
  - `generated.append(aggregate_path)`
- 返回 `generated` 列表（仅包含列种子文件）。

`generate_seeds` 顶层循环：

```python
for db in model.rel_dbs + model.ts_dbs:
    for table in db.tables:
        # 查 write_config 中该表的 col_tag_bind_mode
        write_cfg = find_write_config_for_table(test_cfg, db.name, table.name)
        skip = write_cfg and write_cfg.col_tag_bind_mode
        files = _generate_table_seeds(db, table, output_dir, refs, ref_paths,
                                       skip_row_aggregate=skip)
```

新增 `find_write_config_for_table(test_cfg, db_name, table_name) -> Optional[WriteConfig]` 工具函数（放 `src/config_parser/models.py` 或 `src/kwjdbc_svt/main.py`）。

### 4.3 SetupTG sampler 修改 + 追加（`src/jmx_skeleton_generator/generators/write_groups.py`）

现有 SetupTG 加载行种子文件 sampler（生成器代码 grep `props.get("__SHARED_MEM` 找到具体位置）：

```python
# 现有（伪代码，源自 write_groups.py:77 附近的 __SHARED_MEM_{db}_{table} 写入逻辑）
def generate_shared_memory_setup_thread_group(seed_csv_paths):
    for path in seed_csv_paths:
        # ... 加载 CSV → 写 props.__SHARED_MEM_{db}_{table}
```

修改方案（最小侵入）：
- 现有 sampler 接收新的 `write_configs: List[WriteConfig]` 参数（内部按 `{db}.{table}` 索引成 `write_cfg_by_table: Dict[(db, table), WriteConfig]`），遍历时 `if write_cfg_by_table[(db, table)].col_tag_bind_mode: continue`。
- 新增 sampler（独立函数）`generate_bind_setup_thread_group(seed_csv_paths, write_configs, num_threads)`：
  - 遍历所有 col_tag_bind_mode 表，读列种子文件 → 按 hash 分组 → 写 `__SHARED_MEM_{db}_{table}_bind`。
- main 入口根据 `any(wc.col_tag_bind_mode for wc in write_configs)` 决定是否追加新 sampler。

新 sampler 的 Groovy PreProcessor 模板（每张 col_tag_bind 表一份）：

```groovy
// JSR223PreProcessor (groovy): Bind 模式 SetupTG 列种子加载 + hash 分组
def db = "<db_name>"
def table = "<table_name>"
def ptagColumns = [<ptag_names>]  // 注入
def dataColumns = [<data_col_names>]  // 注入
def numThreads = ${num_threads}    // UDV
def seedNum = ${seed_num}          // UDV

// 1. 读列种子文件（从 generated CSV 路径）
def tableDir = "<seeds_dir>/${db}/${table}"
def columnFiles = new FileNameByRegexFinder("^\\d+_.*\\.csv\$").list(tableDir)
Map<String, List<String>> colValues = [:]
for (f in columnFiles) {
    def name = f.replaceAll("^\\d+_(.*)\\.csv\$", "\$1")
    colValues[name] = new File(tableDir, f).readLines().collect { it.replaceAll('"', '') }
}

// 2. 按 device_code + 其他 ptag 模拟 ptag_tuple → group_id
//    device_code = "device_" + (deviceStart + (rowIdx % devicePerThread))
Map<String, Map> groups = [:]
for (int rowIdx = 0; rowIdx < seedNum; rowIdx++) {
    def deviceCode = "device_" + (deviceStart + (rowIdx % devicePerThread))
    def ptagTuple = [deviceCode] + ptagColumns.drop(1).collect { colValues[it][rowIdx % colValues[it].size()] }
    int groupId = Math.abs(ptagTuple.hashCode()) % numThreads

    def colsSubset = dataColumns.take(colNumPerTag)  // 简化：每组固定前 N 列
    // 实际：可按 colNumPerTag 取列种子值（多组可共享同一 col 子集或不同）
    def rowVals = colsSubset.collect { colValues[it][rowIdx % colValues[it].size()] }

    if (!groups.containsKey(String.valueOf(groupId))) {
        groups[String.valueOf(groupId)] = [col_names: colsSubset, row_values: []]
    }
    groups[String.valueOf(groupId)].row_values.add(rowVals)
}

// 3. 写 props
def rowsKey = "__SHARED_MEM_${db}_${table}_bind"
org.apache.jmeter.util.JMeterUtils.getJMeterProperties().put(rowsKey, groups)
log.info("BindSetup: ${rowsKey} groups=" + groups.size())
```

**简化说明**：原计划每组共享同一组列子集（`colsSubset.take(colNumPerTag)` 固定前 N 列），减少复杂度；如需"每组不同列子集"，可在分组时引入 `group_id` 决定列起始 offset（`dataColumns[(groupId * colNumPerTag) % dataColumns.size(), ...]`），详见 §5 Open Question 0（已收敛——选固定前 N 列）。

### 4.4 写入 TG 列子集逻辑（`_build_inline_sql_preprocessor_script`）

现有函数签名扩展：

```python
def _build_inline_sql_preprocessor_script(
    *,
    db: str,
    table: str,
    columns: List[str],           # 完整 SQL 列（含 ts + ptags + data_cols）
    first_ptag_column: Optional[str],
    device_per_thread: int,
    column_types: Optional[List[str]] = None,
    ms_step: int = 1000,
    batch_lines: int = 1,
    col_tag_bind_mode: bool = False,    # 新增
    col_num_per_tag: int = 0,           # 新增
    num_threads: int = 1,               # 新增（hash mod 用）
) -> str:
```

实现要点（Groovy 脚本生成）：

- `col_tag_bind_mode=false`：生成现有全行 INSERT Groovy（行为不变）。
- `col_tag_bind_mode=true`：
  - `rows_key = f"__SHARED_MEM_{db}_{table}_bind"`（不是 `_bind`）。
  - 读 `props.get(rows_key)` 为 `Map<groupId, {col_names, row_values}>`。
  - 计算 `group_id = hash(ptag_tuple) mod num_threads`。
  - 查 `groups[group_id].col_names` 取子集列名；查 `groups[group_id].row_values[random]` 取子集值。
  - INSERT 列名 = `[ts] + ptag_names + groups[group_id].col_names`（NOT NULL 列强制列入）。
  - INSERT 值 = `[ts_fmt] + ptag_runtime_values + row_values_subset`。

NOT NULL 列强制列入（spec 约束）：在生成器层面，把 NOT NULL `data_col` 追加到子集列名（即使 `col_num_per_tag` 不够，也要加）；具体逻辑：

```python
# 伪代码
if col_tag_bind_mode:
    # 子集列 = groups[group_id].col_names
    subset = groups[group_id].col_names
    # 追加 NOT NULL data_col（如有）
    not_null_data_cols = [c.name for c in table.data_cols if c.nullable is False]
    full_subset = list(dict.fromkeys(subset + not_null_data_cols))  # 保序去重
    insert_cols = ["ts"] + [ptag.name for ptag in table.primary_tags] + full_subset
```

### 4.5 schemaless 集成（`src/jmx_skeleton_generator/generators/rest_write_groups.py`）

现有 `generate_rest_write_thread_group` 扩展：

- 新增 `write_configs: Optional[List[WriteConfig]] = None` 入参（内部索引为 `Dict[(db, table), WriteConfig]`）。
- 对每个 col_tag_bind_mode 表，Groovy PreProcessor 改为读 `__SHARED_MEM_{db}_{table}_bind`，按 group_id 取子集列名 + 值，**只填 InfluxDB Line 的 `field_set` 部分**（tag_set 部分仍按所有 ptag + regular_tag 填）：
  ```
  <measurement>,<ptag1>=device_<n>,<ptag2>=<v>,<tag1>=<v> <field_subset1>=<v>,<field_subset2>=<v> <ts>
  ```
  注意：InfluxDB Line 协议中 `field_set` 顺序不重要，但必须包含所有非空 field；未在子集的 field 不出现 → server 用上次值或 NULL（InfluxDB Line 语义）。

### 4.6 main 路由（`src/kwjdbc_svt/main.py`）

主入口在生成 seed 文件前，遍历 `test_cfg.write_configs`（`List[WriteConfig]`），构建 `write_cfg_by_table: Dict[(db, table), WriteConfig]`，传给 Orchestrator（§4.2）+ SetupTG 生成器（§4.5）+ 写入 TG 生成器（§4.4）。

主入口额外校验：

```python
for db in model.rel_dbs + model.ts_dbs:
    for table in db.tables:
        wc = find_write_config_for_table(test_cfg, db.name, table.name)
        if wc and wc.col_tag_bind_mode:
            # 校验 1: col_num_per_tag > 0
            if wc.col_num_per_tag <= 0:
                raise ValueError(f"col_num_per_tag must be > 0 for {db.name}.{table.name}")
            # 校验 2: col_num_per_tag <= data_col_count
            if wc.col_num_per_tag > table.data_col_count:
                raise ValueError(
                    f"col_num_per_tag ({wc.col_num_per_tag}) > "
                    f"data_col_count ({table.data_col_count}) for "
                    f"{db.name}.{table.name}"
                )
            # 校验 3: 至少 1 个 primary_tag
            if isinstance(table, TsTableConfig) and table.primary_tag_count == 0:
                raise ValueError(
                    f"col_tag_bind_mode requires at least 1 primary_tag for "
                    f"{db.name}.{table.name}"
                )
```

### 4.7 列绑定 Schema 例子

```yaml
# tests/kwjdbc_svt/fixtures/test_model_col_bind.yaml (新)
ts_dbs:
  - name: iot_monitor
    tables:
      - name: meters
        if_not_exists: true
        with_hash: 100
        primary_tag_count: 1
        primary_tags:
          - {name: device_id, type: varchar(64)}
        regular_tag_count: 0
        data_col_count: 4000
        data_cols: [<4000 int8 / varchar 列>]

# tests/kwjdbc_svt/fixtures/test_cfg_col_bind.yaml (新)
write_configs:
  - tbl_name: iot_monitor.meters
    mode: batch_prepared
    write_threads: 4
    col_tag_bind_mode: true
    col_num_per_tag: 5    # 每 ptag 写 5 列
```

## 5. 测试策略

| 层级 | 覆盖 | 文件 |
|------|------|------|
| 单元 | WriteConfig 字段 + Pydantic 校验 | `tests/config_parser/test_col_tag_bind_config.py` (新) |
| 单元 | Orchestrator skip_row_aggregate | `tests/seed_data_generator/test_orchestrator_col_bind.py` (新) |
| 单元 | SetupTG sampler if 分支 + 追加新 sampler | `tests/jmx_skeleton_generator/test_setup_bind_sampler.py` (新) |
| 单元 | _build_inline_sql_preprocessor_script 列绑定分支 | `tests/jmx_skeleton_generator/test_inline_sql_bind.py` (新) |
| 单元 | rest_write_groups 列绑定分支 | `tests/jmx_skeleton_generator/test_rest_write_bind.py` (新) |
| 单元 | hash(ptag_tuple) mod num_threads 多对一分布 (8.7) | `tests/jmx_skeleton_generator/test_hash_distribution.py` (新) |
| 集成 | `_run_pipeline` 端到端 col_tag_bind=true | `tests/kwjdbc_svt/test_main_col_bind.py` (新) |
| 集成 | 混合表场景（部分全行 + 部分列绑定） | `tests/kwjdbc_svt/test_main_col_bind_mixed.py` (新) |
| Smoke | sparse 4000 列 col_tag_bind=true 10s | `/tmp/jmeter-col-bind-sparse` |
| Smoke | schemaless 路径 col_tag_bind=true 10s | `/tmp/jmeter-col-bind-schemaless` |
| 全量 | 现有 701+ pytest 不 regress | `tests/` |

反退化测试（tasks.md §8.7 / §8.8）：
- **§8.7 单元测试**：`test_hash_distribution_no_degeneracy`：构造 16 个不同 ptag tuple，`num_threads=4`，断言至少 2 个不同 `group_id`（hash 不退化为单组）。
- **§8.8 冒烟测试**：跑 jmeter 验证多个 ptag 组合在 JTL 中对应至少 2 个不同 INSERT 列子集（避免 hash 退化）。

不重复造覆盖：
- 列种子文件 IO（`read_column_seed` / `write_column_seed`）已有测试，本 DCR 不重测。
- 现有 SetupTG 行种子加载 sampler 测试保留，只加 if 分支断言。

## 6. 风险与回滚

| 风险 | 缓解 |
|------|------|
| SetupTG [A] sampler 漏写 if 分支 → col_tag_bind 表仍写行种子 → SetupTG 内存爆 | 新单元测试 + IT 断言 props 仅有 `_bind` key |
| `_build_inline_sql_preprocessor_script` 列绑定分支拼错列名 → server 报 column not found | 单元测试覆盖所有 5 种 mode + NOT NULL 列强制列入 |
| hash 退化为单组（所有 ptag 同一 group_id）→ 列子集不变 | §8.7/§8.8 反退化测试强制约束 |
| `find_write_config_for_table` 在 mixed 表场景查错表 → 误启用模式 | 单元测试覆盖 (db, table) 完全匹配 |
| 混合表 `__SHARED_MEM_{db}_{table}` 与 `_bind` 命名冲突 | Decision 5 已锁命名；JMeter props 字符串 key 不冲突 |
| schemaless 列绑定路径在 InfluxDB Line 协议下语义不符 | server 把未填 field 当 NULL（与现有 INSERT NULL 行为一致） |
| 列数超过 4000 时 SetupTG Groovy 字符串超 64 KB 编译上限 | `col_num_per_tag` ≤ 4000，SetupTG Groovy 模板 < 8 KB；不触发 |
| 回滚：`col_tag_bind_mode=false` 默认值，**整 feature 关闭** → 现有 fixture 不变 | 单个 commit 可原子回滚 |

## 7. 验收

- 全量 `python -m pytest tests/` 通过（baseline 701+）。
- 新增 8+ pytest case 覆盖 WriteConfig 校验 / Orchestrator skip / SetupTG sampler / 列绑定 INSERT / hash 分布 / mixed table / schemaless 集成。
- sparse 4000 列 col_tag_bind=true smoke：10s 跑通，`db_shig_sparse.t_cnc` `count(*) = setup_runs × num_threads × device_per_thread`，ptag 列非 NULL。
- schemaless col_tag_bind=true smoke：SetupTG 3/3 + Write 10/10 + Query 1/1，DB `count(*) from iot_monitor.meters` = 期望行数。
- 反退化测试 §8.7 + §8.8 通过。
- docs/specs/kwdb-svt-test-plan-generator-spec.md §131-136 增补 `col_tag_bind_mode` 描述。
- docs/refs/kaiwudb-schemaless-write-reference.md 增补列绑定模式说明（如果适用）。
- todolist.md 标记 DCR 进度（commit hash + smoke 行数）。

## 8. 开放问题

无（9 个 Open Questions 已在 OpenSpec design.md 全部收敛）。
