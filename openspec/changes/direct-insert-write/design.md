## Context

直接 INSERT 写入是 T0 阶段的核心功能，用于向时序表持续写入测试数据。写入线程组从共享内存中随机拷贝行数据，装配时间戳和设备号，然后通过 JDBCSampler 执行 SQL。

## Goals / Non-Goals

**Goals:**
- 实现 `single_insert` 模式（单条 INSERT）
- 实现 `batch_insert` 模式（批量 INSERT）
- 从共享内存拷贝行数据
- 装配时间戳和第一个 Primary Tag
- 生成 JSR223PreProcessor Groovy 脚本
- 实现关系表一次性初始化写入

**Non-Goals:**
- 不支持 PreparedStatement（由 write-strategies 变更实现）
- 不支持 schemaless 写入（由 write-strategies 变更实现）

## Decisions

### 使用 JSR223PreProcessor 准备数据

**Decision:** 在 JDBCSampler 前挂载 JSR223PreProcessor，使用 Groovy 脚本准备批次数据。

**Rationale:**
- JDBCSampler 的 `queryArguments` 需要动态值
- Groovy 支持 JSR223 编译缓存，性能好
- 便于从共享内存和线程变量读写数据

**Alternatives considered:**
- **JMeter CSV DataSet**: 不支持动态行拷贝
- **BeanShell PreProcessor**: 不支持编译缓存，性能差

### 共享内存使用 JMeter props

**Decision:** 使用 `props.put()` 和 `props.get()` 在 SetupThreadGroup 中初始化共享内存，写入线程组读取。

**Rationale:**
- `props` 是全局属性，跨线程组可见
- `vars` 是线程局部变量，不适用
- 简单直接，无需额外依赖

**Alternatives considered:**
- **JMeter 文件共享**: 需要文件系统操作，复杂度高

### 第一个 Primary Tag 占位符处理

**Decision:** 首个 ptag 列不生成列种子文件；`${device_code}` 占位符在行种子总集 CSV 中由 `build_row_aggregate` 注入，运行时由写入线程组的 JSR223PreProcessor 替换为 `device_{设备号}`。

**Rationale:**
- 符合设计文档要求
- 设备号由线程索引和配置计算，便于多端协同
- 占位符约定明确，易于识别

**Alternatives considered:**
- **从设备号生成器采样**: 增加复杂度
- **硬编码固定值**: 不符合测试场景

### 关系表初始化写入策略

**Decision:** 关系表在 SetupThreadGroup 中使用 batch_insert 策略一次性写入，不参与持续发压。

**Rationale:**
- 符合规格书要求（关系表作为元数据表）
- 列种子生成逻辑与时序表一致，可复用
- 使用 Loop Controller 处理大数据集

**Alternatives considered:**
- **使用实时数据生成线程组**: 已废弃，使用共享内存机制
- **不写入关系表**: 不符合规格书要求

### 时间戳计算公式

**Decision:** 使用公式 `base_time + batch_seq * ms_step + i * (ms_step / batch_lines)` 计算每行时间戳。

**Rationale:**
- `base_time` 在每个线程首次执行时获取一次，减少系统调用
- `batch_seq` 记录已发送批次序号，保证时间戳递增
- 行内时间戳均匀分布，符合规格书要求

**Alternatives considered:**
- **每次执行都获取当前时间**: 不保证批次内时间戳均匀分布

### 线程索引获取方式

**Decision:** 使用 JMeter 内置函数 `${__threadNum}` 获取线程索引，用于多端协同的设备号计算。

**设备号公式：**
- 全局设备起始值：`local_device_start = device_start + ${__threadNum} * device_per_thread`
- 行内设备号：`device_number = device_start + ${__threadNum} * device_per_thread + (row_index % device_per_thread)`

**Rationale:**
- `${__threadNum}` 是 JMeter 官方内置函数，返回线程索引（从0开始）
- 稳定可靠，无需解析线程名字符串
- 支持多端协同场景下的设备号计算
- JMeter 自动管理线程索引，无需手动维护状态

**Alternatives considered:**
- **解析 `${__threadName}` 变量**: 线程名格式为 "Thread Group Name 1-1"，无法可靠解析；线程名格式可能随 JMeter 版本变化
- **使用线程本地计数器**: 需要额外的状态管理，增加复杂度
- **使用 JMeter 用户定义变量**: 需要在 SetupThreadGroup 中预先设置所有线程的变量，多线程场景下难以管理

## Risks / Trade-offs

### Risk: 共享内存竞争
**Mitigation:** 读取操作无副作用，写入线程只读不写。写入线程拷贝行数据到本地，不影响共享内存。

### Risk: 时间戳精度问题
**Mitigation:** 使用 `java.sql.Timestamp`，精度到纳秒级，满足测试需求。

### Trade-off: 列种子文件中保留占位符
**Rationale:** 占位符约定明确，便于识别和替换。如果查询使用该列，需要特殊处理。

### 表名使用限定名

**Decision:** 所有生成的 INSERT 语句中的表名必须使用带数据库名的限定名格式（`database.table_name`），与 DDL 生成器保持一致。

**Rationale:**
- 与 DDL 生成器统一，整个测试计划使用一致的表名格式
- 避免数据库上下文切换导致的引用歧义
- 支持在单个测试计划中操作多个数据库
- 提高测试计划的可读性和维护性

**Alternatives considered:**
- **使用非限定名**: 需要在 INSERT 语句前维护当前数据库状态，增加复杂度
- **动态数据库上下文**: 在 JMX 中维护当前数据库，复杂度高且容易出错

**示例:**
```sql
-- 正确：使用限定名
insert into iot_monitor.t_cnc (ts, ptag_int8_1, col_int8_1) values (?, ?, ?)
insert into iot_metadata.t_workshop (pk_int8_1, col_varchar_1) values (?, ?)

-- 错误：使用非限定名（除非已执行 USE iot_monitor）
insert into t_cnc (ts, ptag_int8_1, col_int8_1) values (?, ?, ?)
```

### SQL 标识符和关键字统一使用小写

**Decision:** 生成的 INSERT 语句中，所有 SQL 标识符（包括表名、列名）和 SQL 关键字（如 INSERT INTO、VALUES 等）统一使用小写，与 DDL 生成器保持一致。

**Rationale:**
- 与 DDL 生成器统一，整个测试计划使用一致的 SQL 规范
- 虽然 KaiwuDB 对未加引号标识符的大小写不敏感，但统一使用小写可以提高测试计划的可读性和一致性
- 便于维护和调试
- 简化大小写转换逻辑，避免不同模块使用不同大小写规范

**Alternatives considered:**
- **关键字大写标识符小写**: 与 DDL 生成器不一致
- **保持原样**: 可能产生大小写不一致的问题

**示例:**
```sql
-- 正确：所有标识符和关键字统一小写
insert into iot_monitor.t_cnc (ts, ptag_int8_1, col_int8_1) values (?, ?, ?)
insert into iot_metadata.t_workshop (pk_int8_1, col_varchar_1) values (?, ?)

-- 错误：使用了大写（虽然 KaiwuDB 支持，但不规范）
INSERT INTO iot_monitor.t_cnc (ts, ptag_int8_1, col_int8_1) VALUES (?, ?, ?)
```

## Migration Plan

无需迁移。这是一个新功能模块。