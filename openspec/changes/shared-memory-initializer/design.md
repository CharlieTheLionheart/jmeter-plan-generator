## Context

共享内存初始化模块负责将种子数据从 CSV 文件加载到 JMeter 共享变量中。CSV 文件由 `seed-data-generator` 生成，Groovy 加载脚本由本模块生成并包装成 JSR223PreProcessor XML 组件。

## Goals / Non-Goals

**Goals:**
- 从 CSV 文件读取行种子总集
- 生成 Groovy 加载脚本
- 使用 `utils/xml_helpers` 生成 JSR223PreProcessor XML
- 采用 `List[List[Any]]`（行优先）数据结构
- 支持写入策略（直接写入、PreparedStatement）

**Non-Goals:**
- 不生成种子数据（由 `seed-data-generator` 负责）
- 不实现写入逻辑（由 `write-strategies` 负责）
- 不处理共享变量的生命周期管理（由 JMeter 运行时管理）

## Decisions

### 共享内存数据结构设计

**Decision:** 共享内存存储两个变量：
1. `__SHARED_MEM_{table_name}`：`List[List[Any]]` - 行优先的二维数组
2. `__SHARED_MEM_{table_name}_columns`：`List<String>` - 列名列表（固定顺序）

**Rationale:**
- **行优先存储优势**：
  - 直接写入：`"values (${row.collect{"'$it'"}.join(',')})"` 一行构造
  - Prepare stmt：`pstmt.setString(i+1, row[i])` 直接按索引绑定
  - Batch prepared：批量绑定性能最优，无Map查找开销
  - 行拷贝：`row.clone()` 直接实现
- **列顺序保证**：
  - DDL生成器按配置列顺序生成建表语句
  - seed-data-generator按列序号顺序读取列种子文件并拼接
  - CSV第一行为列名，后续按列顺序存储
- **内存占用最小**：相比`List[Map<String, Any>>`节省大量key重复开销

**Groovy脚本示例：**
```groovy
// 加载共享内存
def rows = props.get("__SHARED_MEM_table_name")
def columns = props.get("__SHARED_MEM_table_name_columns")

// 直接写入
def row = rows[rowIdx]
def sql = "insert into table (${columns.join(',')}) values (${row.collect{"'$it'"}.join(',')})"

// Prepare stmt
pstmt.setLong(1, row[0])      // ts
pstmt.setInt(2, row[1])       // ptag_int8_1
pstmt.setInt(3, row[2])       // col_int8_1

// 行拷贝
def cloned = rows[startIdx..<endIdx].collect { it.clone() }
```

**Alternatives considered:**
- **Map<String, List[Any]>**：需要双重映射（列名→列表+列名→索引），代码复杂
- **List[Map<String, Any>>**：内存占用最大，批量绑定需逐行Map查找

### CSV 文件格式依赖

**Decision:** CSV 文件格式由 `seed-data-generator` 保证：第一行为列名，后续行为数据，按列顺序存储。

**Rationale:**
- 避免重复解析逻辑
- 保证数据一致性
- CSV 格式通用，Excel 可编辑

**Alternatives considered:**
- **自定义格式**：增加复杂度，不易调试
- **JSON 格式**：解析复杂，性能差

### Groovy 脚本使用 JMeter `props`

**Decision:** 使用 `props.put()` 存储共享变量，使用 `props.get()` 读取。

**Rationale:**
- JMeter 标准方式
- 跨线程共享
- 符合 JMeter 变量作用域

**Alternatives considered:**
- **vars 对象**：仅单线程有效
- **全局变量**：作用域过大

## Risks / Trade-offs

### Risk: CSV 文件路径不存在
**Mitigation:** 在脚本中添加异常处理，记录错误日志。

### Risk: Groovy 脚本安全性和复杂性
**Mitigation:** 简化脚本逻辑，仅实现数据加载。未来可考虑将脚本提取为独立文件。

### Trade-off: 不支持增量加载
**Rationale:** 测试场景数据量固定，一次性加载即可。

## Migration Plan

无需迁移。这是一个新功能模块。