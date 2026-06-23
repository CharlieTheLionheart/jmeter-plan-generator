## Why

在 KaiwuDB SVT 测试计划生成器中，多个模块都需要处理两类通用任务：

1. **JMeter XML 元素创建**：`jmx_builder` 及相关的 JMX 生成模块需要反复创建 `<jmeterTestPlan>`、`<HashTree>`、`<stringProp>`、`<boolProp>` 等 JMeter 特有 XML 节点，手动构建容易出错且重复代码多。
2. **`val_range` 表达式解析**：配置解析、种子数据生成等模块都需要理解 `>=N`、`[a,b]`、`enum:v1,v2`、`ref:db.table.col` 等表达式格式。

将这些通用能力下沉到独立的 `utils` 模块，可以减少重复实现，统一约定，并降低各业务模块的复杂度。

## What Changes

- 新增 `src/utils/__init__.py`
- 新增 `src/utils/xml_helpers.py`，作为本 change 的核心交付物之一，提供：
  - 创建 JMeter 标准 XML 元素的便捷函数
  - 添加 `<stringProp>` / `<boolProp>` / `<longProp>` / `<doubleProp>` 等属性的辅助函数
  - 生成 `<HashTree>` 层级结构的辅助函数
  - 将 XML 树序列化为字符串（保留缩进）
  - **新增**：创建 JSR223PreProcessor 组件的辅助函数，支持将各策略生成的 SQL、script 等参数注入
- 新增 `src/utils/val_range_parser.py`，作为本 change 的核心交付物之一，提供：
  - 比较运算符表达式解析：`>=N`、`<=N`、`>N`、`<N`、`=N`
  - 区间表达式解析：`[a,b]`、`(a,b)`、`[a,b)`、`(a,b]`，区分开闭边界
  - 枚举表达式解析：`enum:v1,v2,...`
  - 外键引用解析：`ref:库名.表名.列名`
  - 正则表达式解析：`^...$`
  - 返回结构化的解析结果，供下游模块使用
- **新增** `src/utils/preprocessor_helpers.py`，为 write-strategies 模块提供公共逻辑：
  - 共享内存读取工具函数：`read_shared_memory(table_name)`
  - 行数据复制工具函数：`clone_rows(rows)`
  - 时间戳计算工具函数：`calculate_timestamps(base_time, batch_seq, ms_step, batch_lines)`
  - 设备号计算工具函数：`calculate_device_number(device_start, thread_num, device_per_thread, row_index)`
  - 占位符替换工具函数：`replace_placeholder(value, device_number)`
  - PreProcessor 脚本模板生成器：`generate_preprocessor_template(strategy_specific_parts)`

## Capabilities

### New Capabilities

- `utils`: 通用工具能力，包括 XML 元素便捷创建和 `val_range` 表达式解析

### Modified Capabilities

（无）

## Impact

- `jmx-skeleton-generator` 及其他 JMX 生成模块依赖 `utils/xml_helpers.py`
- `seed-data-generator` 依赖 `utils/val_range_parser.py` 生成符合范围约束的种子数据
- `config-parser` 可复用 `utils/val_range_parser.py` 进行 `val_range` 格式校验
- 无新增外部依赖：`xml_helpers.py` 使用 Python 标准库 `xml.etree.ElementTree`，`val_range_parser.py` 使用标准库 `re` 等
