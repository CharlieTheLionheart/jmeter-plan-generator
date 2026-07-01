# Tasks: utils

## 0. 状态确认与范围固化

- [ ] 0.1 确认 `val_range_parser.py` 已是稳定实现，无需重构（见 §1）
- [ ] 0.2 确认 `xml_helpers.py` 和 `preprocessor_helpers.py` 为本期新增范围
- [ ] 0.3 确认测试文件路径：`tests/utils/test_xml_helpers.py`、`tests/utils/test_preprocessor_helpers.py`
- [ ] 0.4 更新 `src/utils/__init__.py` 导出公共 API

## 1. val_range_parser 收尾（已实现，补充边界测试）

- [ ] 1.1 补充空字符串解析测试用例（期望抛 `ValueError`）
- [ ] 1.2 补充纯空白字符串解析测试用例（期望抛 `ValueError`）
- [ ] 1.3 补充非法区间（如 `[100,1]`）测试用例（期望抛 `ValueError`）
- [ ] 1.4 补充枚举值含空字符串（如 `enum:A,,B`）测试用例（期望抛 `ValueError`）
- [ ] 1.5 补充非法 regex（无锚点）测试用例（期望抛 `ValueError`）
- [ ] 1.6 运行全部 val_range_parser 测试并通过

## 2. xml_helpers 基础结构

- [ ] 2.1 创建 `src/utils/xml_helpers.py`
- [ ] 2.2 实现 `create_element(tag, attrib=None)` 返回 `xml.etree.ElementTree.Element`
- [ ] 2.3 实现 `add_hash_tree(parent)` 追加 `<HashTree/>` 并返回子元素
- [ ] 2.4 实现 `add_string_prop(parent, name, value)` 追加 `<stringProp name="{name}">{value}</stringProp>`
- [ ] 2.5 实现 `add_bool_prop(parent, name, value)` 追加 `<boolProp name="{name}">{value}</boolProp>`
- [ ] 2.6 实现 `add_long_prop(parent, name, value)` 追加 `<longProp name="{name}">{value}</longProp>`
- [ ] 2.7 实现 `add_double_prop(parent, name, value)` 追加 `<doubleProp name="{name}">{value}</doubleProp>`
- [ ] 2.8 实现 `add_int_prop(parent, name, value)` 追加 `<intProp name="{name}">{value}</intProp>`
- [ ] 2.9 实现 `add_element_prop(parent, name, element_type, arguments)` 追加 `<elementProp>` 结构

## 3. xml_helpers 序列化与边界

- [ ] 3.1 实现 `to_string(element, encoding="utf-8")` 返回格式化的 XML 字符串
- [ ] 3.2 验证缩进行为：2 空格缩进，一致缩进层级
- [ ] 3.3 验证特殊字符转义：`<`、`>`、`&`、中文内容输出正确
- [ ] 3.4 验证空元素（无子元素）序列化不异常
- [ ] 3.5 验证 JMeter 5.5+ 命名空间属性正确

## 4. xml_helpers 单元测试

- [ ] 4.1 测试 `create_element` 带/不带属性
- [ ] 4.2 测试 `add_hash_tree` 返回子元素且可继续嵌套
- [ ] 4.3 测试 `add_string_prop`、`add_bool_prop`、`add_long_prop`、`add_double_prop` 元素结构正确
- [ ] 4.4 测试属性覆盖：同名属性后者覆盖前者
- [ ] 4.5 测试 `to_string` 缩进、空元素、特殊字符（`<`、`&`、中文）输出无乱码
- [ ] 4.6 测试生成 XML 可被 `xml.etree.ElementTree.parse()` 解析（round-trip）
- [ ] 4.7 运行全部 xml_helpers 测试并通过

## 5. preprocessor_helpers 工具函数

- [ ] 5.1 创建 `src/utils/preprocessor_helpers.py`
- [ ] 5.2 实现 `clone_rows(rows)` — 返回 `[row.clone() for row in rows]`
- [ ] 5.3 实现 `calculate_timestamps(base_time, batch_seq, ms_step, batch_lines)` 返回 `List[java.sql.Timestamp]`
- [ ] 5.4 实现 `calculate_device_number(device_start, thread_num, device_per_thread, row_index)` 返回设备号
- [ ] 5.5 实现 `replace_placeholder(value, device_number)` 将 `${device_code}` 替换为 `device_{device_number}`
- [ ] 5.6 边界测试：`device_per_thread <= 0` 时不抛异常（返回安全值或标注需上游校验）
- [ ] 5.7 边界测试：`ms_step < batch_lines` 时时间戳计算不退化（保留整数除法行为说明）

## 6. PreProcessor 脚本模板生成

- [ ] 6.1 实现 `generate_preprocessor_template(strategy_specific_parts)` 返回完整 Groovy 脚本字符串
- [ ] 6.2 模板包含：共享内存读取调用、行克隆、时间戳计算、设备号计算、占位符替换
- [ ] 6.3 验证模板语法为合法 Groovy（可被 `groovy -e ""` 解析）
- [ ] 6.4 确认 `read_shared_memory` 相关逻辑不在本模块（由 `shared-memory-initializer` 提供）

## 7. preprocessor_helpers 单元测试

- [ ] 7.1 测试 `clone_rows` 返回新列表，原列表不受影响
- [ ] 7.2 测试 `calculate_timestamps` 输出类型为 `List[datetime]`
- [ ] 7.3 测试 `calculate_device_number` 公式正确：`device_start + thread_num * device_per_thread + (row_index % device_per_thread)`
- [ ] 7.4 测试 `replace_placeholder` 正确替换 `${device_code}`
- [ ] 7.5 测试 `replace_placeholder` 原字符串不含占位符时不修改
- [ ] 7.6 测试 `generate_preprocessor_template` 返回非空字符串
- [ ] 7.7 运行全部 preprocessor_helpers 测试并通过

## 8. 模块集成与导出

- [ ] 8.1 更新 `src/utils/__init__.py` 导出：
  - `from utils.xml_helpers import create_element, add_hash_tree, add_string_prop, add_bool_prop, add_long_prop, add_double_prop, add_int_prop, add_element_prop, to_string`
  - `from utils.val_range_parser import ValRangeType, Interval, ValRange, parse_val_range`
  - `from utils.preprocessor_helpers import clone_rows, calculate_timestamps, calculate_device_number, replace_placeholder, generate_preprocessor_template`
- [ ] 8.2 验证 `python -c "from utils import *"` 不抛异常
- [ ] 8.3 运行全部 utils 模块测试并通过

## 9. Review 修复验证

- [ ] 9.1 确认 val_range_parser 的边界条件（空白字符 strip）已在实现中体现
- [ ] 9.2 确认 xml_helpers 的 `to_string` 行为已在 spec 中补充（无 spec 变更则用注释记录）
- [ ] 9.3 确认 `elementProp`、`collectionProp` 等复杂元素暂不支持（待 `jmx-skeleton-generator` 明确需求后再扩展）

## 10. 代码审查

- [ ] 10.1 提交代码审查（review.md findings 全部解决后方可合并）
