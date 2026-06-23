## Context

`utils` 模块定位为测试计划生成器的通用工具层，不直接对应业务功能，但被多个业务模块依赖。当前主要覆盖三类工具能力：

- **XML 工具**：JMeter 测试计划是结构固定的 XML 文件，多个 JMX 生成模块都需要按相同约定创建元素。
- **取值范围解析器**：`val_range` 是配置文件中的核心表达式字段，配置校验和种子数据生成都需要正确解析其语义。
- **PreProcessor 工具**：多个写入策略（single_insert、batch_insert、single_prepared、batch_prepared）都需要生成 JSR223PreProcessor，存在大量公共逻辑可提取（时间戳计算、设备号计算、占位符替换等）。

## Goals / Non-Goals

**Goals:**
- 提供一套简洁、稳定的 JMeter XML 元素创建辅助函数
- 统一解析所有规格书中定义的 `val_range` 表达式格式
- 返回结构化的解析结果，便于下游模块分发处理
- 提供 PreProcessor 公共逻辑的抽象和工具函数
- 保持零外部依赖

**Non-Goals:**
- 不生成完整的 `.jmx` 文件（由 `jmx-skeleton-generator` 等业务模块负责）
- 不生成实际的种子数据（由 `seed-data-generator` 负责）
- 不执行业务规则校验（如”整数开区间内是否存在合法整数”由 `config-parser` 负责）
- 不处理 JMeter 插件或非标准元素
- 不实现特定写入策略的业务逻辑（由 `write-strategies` 负责）

## Decisions

### XML 工具使用标准库 `xml.etree.ElementTree`

**Decision:** `xml_helpers.py` 基于 Python 标准库 `xml.etree.ElementTree` 实现。

**Rationale:**
- 无需引入 `lxml` 等第三方依赖
- JMX XML 元素结构相对固定，标准库足以满足需求
- 便于保留 JMeter 对属性名和元素顺序的特定要求

**Alternatives considered:**
- **lxml**: 功能更强，但需要额外依赖
- **字符串模板拼接**: 容易出错，难以维护

### val_range 解析器使用正则分类识别

**Decision:** `val_range_parser.py` 使用正则表达式对表达式进行分类，再按类型提取字段，返回结构化的数据对象。

**Rationale:**
- 表达式类型之间互斥，按类型分发逻辑清晰
- 正则足以覆盖当前所有格式
- 解析结果可被 `config-parser` 和 `seed-data-generator` 复用

**Alternatives considered:**
- **在业务模块中直接解析**: 会导致 `config-parser` 和 `seed-data-generator` 重复实现
- **使用解析器组合子库**: 增加外部依赖，当前复杂度不需要

### 解析结果采用数据类封装

**Decision:** 定义 `ValRange` 数据类（或使用 TypedDict），暴露以下字段：
- `raw`: 原始表达式字符串
- `kind`: 表达式类型枚举（`comparison`、`interval`、`regex`、`enum`、`ref`、`unknown`）
- 按类型填充的字段，例如 `lower_bound`、`upper_bound`、`lower_inclusive`、`upper_inclusive`、`enum_values`、`regex_pattern`、`ref_db`、`ref_table`、`ref_column` 等

**Rationale:**
- 下游模块通过 `kind` 即可快速分发
- 强类型字段便于 IDE 提示和单元测试

**Alternatives considered:**
- **返回普通字典**: 不够直观，容易拼写错误
- **返回自定义对象并附带方法**: 如 `is_enum()`、`sample()` 等，但 `sample()` 属于种子生成逻辑，放在解析器中会混淆职责

## Risks / Trade-offs

### Risk: `val_range` 解析规则与业务校验规则耦合
**Mitigation:** 解析器仅负责识别格式并提取字段，不判断业务合法性（如区间是否为空、枚举值字符集等），由 `config-parser` 负责校验。

### Risk: `xml_helpers` 需要随着 JMeter 版本变化而调整
**Mitigation:** 仅封装当前 JMeter 5.5+ 使用的核心元素和属性，遇到版本差异时在 `xml_helpers` 中统一修改。

### Trade-off: `val_range` 的正则生成不在本模块实现
**Rationale:** 字符串生成策略由 `seed-data-generator` 决定，解析器只需提供正则原串，保持职责单一。

### PreProcessor 公共逻辑提取

**Decision:** 将各写入策略的公共逻辑提取到 `preprocessor_helpers.py` 模块，包括：
- 时间戳计算、设备号计算、占位符替换
- 行数据复制、行级数据处理
- PreProcessor 脚本模板生成器，基于 `xml_helpers.py` 生成的 JSR223PreProcessor 组件

**注意**：共享内存读取和初始化逻辑已移至 `shared-memory-initializer` 模块，本模块不再包含相关函数。

**Rationale:**
- 避免在 5 个策略中重复实现相同的逻辑
- 统一 PreProcessor 生成规范，便于维护和调试
- 支持通过策略注入特定部分（如 SQL 模板、批量大小等）

**Alternatives considered:**
- **在每个策略中独立实现**: 导致代码重复，维护成本高
- **在 WriteStrategy 基类中提供默认实现**: 部分策略可能需要完全不同的逻辑，不够灵活

## Migration Plan

**步骤:**
1. 实现 `xml_helpers.py` 和 `val_range_parser.py` 基础功能
2. **新增**：编写 `preprocessor_helpers.py` 的单元测试用例
3. **新增**：实现 `preprocessor_helpers.py` 中的公共逻辑函数：
   - `clone_rows(rows)`
   - `calculate_timestamps(base_time, batch_seq, ms_step, batch_lines)`
   - `calculate_device_number(device_start, thread_num, device_per_thread, row_index)`
   - `replace_placeholder(value, device_number)`
   - `generate_preprocessor_template(strategy_specific_parts)`

**注意**：`read_shared_memory(table_name)` 函数已移至 `shared-memory-initializer` 模块。
4. **新增**：验证 PreProcessor 公共逻辑函数通过单元测试
5. **新增**：为 `write-strategies` 模块提供示例代码，展示如何使用 `preprocessor_helpers.py`
