## Context

种子数据生成模块负责根据配置中的 `val_range`、`seed_num`、`nullable`、`null_rate` 等字段生成测试所需的种子数据。生成的列种子文件供查询时 `?` 占位符采样使用，行种子总集在 JMeter SetupThreadGroup 中加载到共享内存，供写入线程拷贝装配数据。

## Goals / Non-Goals

**Goals:**
- 按列类型和 `val_range` 生成符合要求的随机数据
- 支持 NULL 值生成和随机打散
- 支持外键引用采样
- 支持枚举类型顺序循环选取
- 生成列种子文件（命名：`{列序号}_{列名}.{类型名}`）
- 生成行种子总集（列拼接、循环填充）

**Non-Goals:**
- 不支持自定义数据分布（如正态分布）
- 不支持数据关联生成（如外键引用后生成关联数据）
- 不支持种子数据的增量更新

## Decisions

### 数值类型生成使用 `utils/val_range_parser`

**Decision:** 种子数据生成模块复用 `utils/val_range_parser.py` 解析 `val_range` 中的区间表达式、枚举、外键引用和正则，在此基础上实现各类型的值生成逻辑。

**Rationale:**
- 区间表达式语法复杂（`[min,max]`、`(min,max)`、`>=`、`<=` 等），`utils/val_range_parser` 已统一封装
- 可直接复用其解析结果判断表达式类型，避免本模块重复识别
- 便于与外键引用、枚举、正则等格式保持一致的解析语义

**Alternatives considered:**
- **在生成逻辑中直接解析**: 代码重复，难以维护

### 字符串类型生成使用正则生成器

**Decision:** 使用第三方库（如 `xeger` 或 `rstr`）生成符合正则表达式的随机字符串。

**Rationale:**
- 规格书中支持正则表达式，需要随机生成匹配的字符串
- 正则引擎实现复杂，不宜自行实现
- 测试前预生成，无性能要求

**Alternatives considered:**
- **自行实现正则生成器**: 复杂且容易出错
- **限制为固定字符集**: 不符合规格书要求

### NULL 值打散策略

**Decision:** 生成非 NULL 值后，随机选择位置插入 NULL 值，然后打乱顺序。

**Rationale:**
- 实现简单
- 保证 NULL 值均匀分布
- 符合规格书要求

**Alternatives considered:**
- **顺序插入 NULL 值**: 不均匀，容易被索引优化
- **按比例随机决定每行是否为 NULL**: 计数难以精确

### 行种子总集格式

**Decision:** 行种子总集使用 CSV 格式保存，每表一个文件，文件名为 `{库名.表名}.csv`。使用 Python `csv` 模块加载，避免手动分割字符串导致的转义问题。

**Rationale:**
- CSV 格式通用性强，Excel 可直接打开编辑，便于人工校验和调试
- Python `csv` 模块自动处理字段内的分隔符（逗号）、引号、换行符等转义问题，安全可靠
- 每行对应一条记录，直接按行读取即可用于 prepared statement 参数绑定
- 以 `库名.表名.csv` 命名便于跨库场景下的文件管理和查找

**Alternatives considered:**
- **嵌套列表/字典结构**: 需要额外序列化/反序列化，不如 CSV 直观
- **Python pickle**: 二进制格式不可读，Python 专用，不便于跨工具使用
- **手动按逗号分割纯文本**: 字段内含逗号时会导致错误解析，不安全

**示例格式:**
```csv
id,name,age,description,created_at
1,Alice Smith,30,"Software engineer, likes Python",2024-01-01
2,Bob Johnson,25," ""The expert"" in AI",2024-01-02
3,Charlie Brown,35,"Multi-line
field",2024-01-03
```

**Python 加载代码示例:**
```python
import csv

def load_row_seeds(csv_path):
    """加载行种子 CSV 文件，返回行列表，每行是一个参数列表"""
    with open(csv_path, 'r', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)  # 第一行为列名（可选）
        rows = list(reader)    # 每行直接作为 prepared statement 的参数
        return header, rows

# 使用示例（在 JMeter JSR223PreProcessor 中）
header, rows = load_row_seeds('seeds/tsdb.ts_table.csv')
# rows[i] 直接用于 cursor.execute("INSERT ... VALUES (?, ?, ...)", rows[i])
```

### 列种子文件格式

**Decision:** 列种子文件使用 CSV 格式保存，每列一个文件。普通列种子文件命名：`{列序号}_{列名}.{类型名}`；被引用的主键列种子文件：`{列序号}_{列名}.{类型名}.ref`。

**Rationale:**
- 与行种子总集保持一致的 CSV 格式，简化代码实现
- Python `csv` 模块自动处理字段内含换行符、逗号、引号等特殊字符的场景（通过引号包裹），无需自定义转义规则
- 当 `val_range` 为正则表达式生成的字符串包含换行符时，CSV 能正确转义和解析
- Excel 可直接打开编辑，便于人工校验和调试
- ⚠️ **注：** Python `csv` 模块对文件扩展名不敏感，`.ref` 文件内容采用 CSV 格式时，`csv.reader()` 完全可以正常解析

**Alternatives considered:**
- **一行一个值的纯文本格式**: 需要手动处理换行符转义（如 `\n`），容易出错；与行种子总集格式不一致，增加维护成本
- **JSON Lines 格式**: 标准格式但与行种子总集不一致，需要两套读取逻辑
- **统一改为 .csv 扩展名**: 扩展名对 `csv` 模块无影响，`.ref` 扩展名可用于快速区分文件类型（被引用的主键列 vs 普通列）

**示例格式（普通列）:**
```csv
value
Alice Smith
Bob Johnson
"Multi-line
field"
```

**示例格式（主键列 .ref 文件）:**
```csv
value
1
2
3
```

**Python 加载代码示例:**
```python
import csv

def load_column_seeds(csv_path):
    """加载列种子 CSV 文件，返回值列表"""
    with open(csv_path, 'r', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)  # 第一行为固定列名 "value"
        values = [row[0] for row in reader]  # 读取每行的第一列
        return values

# 使用示例
values = load_column_seeds('seeds/tsdb.t_table/1_ptag_int8_1.int8')
# .ref 文件同样适用
pk_values = load_column_seeds('seeds/rel_db.t_workshop/1_pk_int8_1.int8.ref')
```

**写入代码示例（正确处理换行符）:**
```python
import csv

def save_column_seeds(csv_path, values):
    """保存列种子到 CSV 文件"""
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['value'])  # 写入表头
        for val in values:
            if val is None:
                writer.writerow(['null'])  # NULL 值写入为 "null"
            else:
                writer.writerow([str(val)])  # 其他值转换为字符串写入

# 使用示例
values = ['line1\nline2', 'line3', None]
save_column_seeds('seeds/tsdb.t_table/1_col_varchar.varchar', values)
# 输出 CSV:
# value
# "line1
# line2"
# line3
# null
```

### 外键引用采样机制

**Decision:** 采用预生成主键列种子文件策略。关系表主键在初始化前预先生成列种子文件并单独保存，时序表引用该主键的tag列从该文件采样，关系表自身初始化也使用该文件填充主键。

**业务约束:**
- 一般不做时序表之间的关联查询，只有时序表和关系表之间的关联
- 关联方式：关系表的主键作为时序表的普通tag
- 核心要求：保证关系表的所有主键可以保存并被时序表引用

**实现策略:**
1. **生成阶段：预生成关系表主键列种子**
   - 在生成关系表种子数据前，先识别哪些主键列被时序表引用（扫描配置中所有时序表的 `val_range="ref:关系库.关系表.主键列"`）
   - 对每个被引用的主键列，根据其配置的 `seed_num` 预生成列种子数据
   - 将预生成的列种子数据单独保存为独立文件，路径为 `seeds/{关系库}.{关系表}/{列序号}_{列名}.{类型名}.ref`
   - 该文件包含该主键列的所有种子值，行数 = 该列配置的 `seed_num`

2. **关系表初始化阶段：使用预生成的列种子文件**
   - 初始化关系表数据时，对于被引用的主键列，直接读取对应的 `.ref` 文件作为主键列种子
   - 按照该文件中的值顺序填充关系表的主键列
   - 确保关系表的主键值与预生成的列种子文件完全一致，保证引用正确性

3. **时序表生成阶段：从预生成的列种子文件采样**
   - 当时序表的某列配置为 `val_range="ref:关系库.关系表.主键列"` 时，不进行实时采样
   - 直接从 `seeds/{关系库}.{关系表}/{列序号}_{列名}.{类型名}.ref` 文件中随机选取值
   - 采样方式：**无放回随机抽样**，确保时序表tag列的值都来自关系表实际存在的主键
   - 如果时序表的 `seed_num` 大于关系表主键的 `seed_num`，则循环使用关系表主键列种子文件中的值

4. **查询阶段：从预生成的列种子文件采样**
   - 生成查询语句时，如果查询条件中涉及 `val_range="ref:关系库.关系表.主键列"` 的列
   - 查询参数也从对应的 `.ref` 文件中随机选取
   - 保证查询参数一定在关系表主键范围内，避免查询不存在的主键值

**文件命名约定:**
- 被引用的主键列种子文件：`seeds/{库名}.{表名}/{列序号}_{列名}.{类型名}.ref`
- 普通列种子文件：`seeds/{库名}.{表名}/{列序号}_{列名}.{类型名}`
- 行种子总集：`seeds/{库名}.{表名}.csv`

**示例:**
```
配置：
关系表：rel_db.t_workshop，主键列 pk_int8_1，seed_num=100
时序表：ts_db.t_table，普通tag列 rtag_int8_1，val_range="ref:rel_db.t_workshop.pk_int8_1"，seed_num=500

执行流程：
1. 扫描发现 pk_int8_1 被时序表引用
2. 预生成 pk_int8_1 的列种子数据（100个值），保存到 seeds/rel_db.t_workshop/1_pk_int8_1.int8.ref
3. 初始化关系表 t_workshop 时，读取 1_pk_int8_1.int8.ref 填充主键列
4. 生成时序表 t_table 时，从 1_pk_int8_1.int8.ref 中采样（循环使用5次以填充500个tag值）
5. 查询时如果条件涉及 rtag_int8_1，也从 1_pk_int8_1.int8.ref 中随机选取参数
```

**Rationale:**
- 避免循环依赖：只有时序表引用关系表主键，不存在关系表引用时序表的情况，无需拓扑排序
- 保证数据一致性：预生成的主键列种子文件被关系表初始化和时序表引用共享使用，确保引用关系正确
- 简化实现：无需复杂的缓存管理机制，直接通过文件系统共享种子数据
- 支持跨库引用：`.ref` 文件路径包含库名，天然支持跨库引用场景

**Alternatives considered:**
- **拓扑排序 + 动态采样**：虽然更通用，但当前业务场景不存在循环依赖，引入复杂度不必要
- **内存中缓存共享引用**：需要设计缓存生命周期管理，文件共享更简单可靠

## Risks / Trade-offs

### Risk: 正则生成库可能不支持完整正则语法
**Mitigation:** 在文档中说明支持的正则语法子集（当前仅支持 `[一-鿿a-zA-Z0-9-_]` 字符集）。

### Risk: 枚举值数量远小于 seed_num 导致模式明显
**Mitigation:** 这是预期行为，规格书已说明顺序循环选取。用户应合理配置 `seed_num`。

### Risk: 外键引用采样导致测试数据不独立
**Mitigation:** 符合规格书要求，主外键关系数据不应隔离。

### Trade-off: 不支持种子数据持久化
**Rationale:** 种子数据在生成阶段写入文件，供 JMeter 运行时读取。持久化已通过文件系统实现。

## Migration Plan

无需迁移。这是一个新功能模块。