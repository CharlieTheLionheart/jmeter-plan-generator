## Context

列名生成器负责根据配置中的 `type_proportion` 分配实际列数，并按照固定格式生成列名。这是连接配置解析和各个生成模块的桥梁，确保列名在 DDL、种子数据、JMX 等所有模块中保持一致。

## Goals / Non-Goals

**Goals:**
- 使用 `floor + 贪心` 算法精确分配列数
- 按固定格式 `{前缀}_{类型}_{序号}` 生成列名
- 规范化数据类型（去除长度/精度）
- 返回列名列表和列序号映射

**Non-Goals:**
- 不支持自定义列名格式
- 不验证列名的数据库合法性
- 不处理保留字冲突

## Decisions

### 使用 floor + 贪心算法

**Decision:** 采用两阶段分配：第一阶段 `floor(count × proportion)` 分配基础列数，第二阶段按小数部分从大到小贪心分配剩余配额。

**Rationale:**
- 确保各类型列数之和严格等于总数
- 算法公平，小数部分大的类型优先获得剩余配额
- 简单高效，时间复杂度 O(n)

**Alternatives considered:**
- **ceil + 随机减**: 可能导致总数不足或需要后续调整
- **按比例四舍五入**: 总数可能超出需要回退

### 列名前缀映射字典

**Decision:** 使用字典映射列组类型到前缀：`{"data_cols": "col", "primary_tags": "ptag", "regular_tags": "rtag", "primary_keys": "pk"}`。

**Rationale:**
- 清晰易读，便于维护
- 支持未来扩展新的列组类型

**Alternatives considered:**
- **硬编码在 if-else 中**: 难以维护
- **使用枚举类**: 增加复杂度，字典足够

### 数据类型规范化逻辑

**Decision:** 使用正则表达式去除长度/精度修饰符，保留基本类型名。

**Rationale:**
- 列名中的类型名应为基本类型（如 `varchar` 而非 `varchar(16)`）
- 简化命名，提高可读性
- 与种子文件命名约定一致

**Alternatives considered:**
- **保留完整类型**: 列名过长
- **使用类型代码**: 不直观

## Risks / Trade-offs

### Risk: 列名冲突
**Mitigation:** 前缀 + 类型 + 序号的设计天然避免冲突，序号按类型递增。

### Trade-off: 列名中保留原始类型大小写
**Rationale:** 配置中使用小写，输出时统一小写，符合 KaiwuDB SQL 语法不区分大小写的特点。

## Migration Plan

无需迁移。这是一个新功能模块。
