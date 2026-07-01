# Tasks: shared-memory-initializer

## 0. 范围与依赖确认

- [ ] 0.1 确认本模块职责：生成 CSV 加载 Groovy 脚本和 JSR223PreProcessor XML 组件，供写入线程组从共享内存读取行数据
- [ ] 0.2 确认依赖：`utils/xml_helpers`（必须先于本模块实现）
- [ ] 0.3 确认依赖：`seed-data-generator` 输出的 CSV 文件格式约定
- [ ] 0.4 确认被 `jmx-skeleton-generator` 的 SharedMemorySetupThreadGroup 调用
- [ ] 0.5 确认与 `utils/preprocessor_helpers.py` 的职责划分：`utils` 负责时间戳/设备号计算等通用辅助函数，本模块负责共享内存读取脚本生成

## 1. 模块骨架

- [ ] 1.1 创建 `src/shared_memory_initializer/__init__.py` 导出 `SharedMemoryInitializerGenerator`
- [ ] 1.2 创建 `src/shared_memory_initializer/shared_memory_initializer.py` 模块文件
- [ ] 1.3 添加模块 docstring 说明本模块职责：CSV 加载、共享内存存储结构、Groovy 脚本生成

## 2. Groovy 加载脚本生成

- [ ] 2.1 实现 `generate_groovy_loader_script(table_name, csv_path)` 函数
- [ ] 2.2 脚本使用 `new File(csvPath).eachLine` 读取 CSV
- [ ] 2.3 第一行作为 header 解析为列名列表，存入 `props.put("__SHARED_MEM_{db}.{table}_columns", columnList)`
- [ ] 2.4 数据行解析为 `List<List<String>>`，存入 `props.put("__SHARED_MEM_{db}.{table}", rows)`
- [ ] 2.5 CSV `null` 字符串转换为 Groovy `null` 对象
- [ ] 2.6 处理 CSV 特殊字符（逗号、引号、换行符），使用 `csv.reader()` 语义
- [ ] 2.7 验证生成的 Groovy 脚本语法正确（可用 `groovy -e ""` 解析）

## 3. JSR223PreProcessor XML 组件生成

- [ ] 3.1 实现 `create_jsr223_preprocessor(groovy_script)` 使用 `utils/xml_helpers`
- [ ] 3.2 创建 `<JSR223PreProcessor>` 元素，`testclass="JSR223PreProcessor"`、`guiclass="TestBeanGUI"`
- [ ] 3.3 设置 `<stringProp name="scriptLanguage">groovy</stringProp>`
- [ ] 3.4 注入 Groovy 脚本内容到 `<stringProp name="script">`
- [ ] 3.5 返回可嵌入 JMX 的 XML Element

## 4. 错误处理

- [ ] 4.1 CSV 文件不存在时：记录 error 日志，设置共享内存变量为空列表，不抛异常
- [ ] 4.2 CSV 解析失败时：记录 error 日志（含行号），设置共享内存变量为空列表，不抛异常
- [ ] 4.3 表名/库名含特殊字符（如 `-`）：替换为下划线后作为共享内存键
- [ ] 4.4 CSV 仅有 header 无数据行：存储空列表到共享内存

## 5. 多表处理

- [ ] 5.1 实现 `generate_for_table(table_name, csv_path)` 为单表生成完整 loader 组件
- [ ] 5.2 实现 `generate_for_tables(tables: List[TableConfig])` 批量生成
- [ ] 5.3 每表使用唯一共享内存键 `__SHARED_MEM_{db}.{table}`

## 6. 数据结构验证

- [ ] 6.1 行优先 `List[List[Any]]` 结构，验证直接写入可直接用 `rows.get(rowIdx)` 访问
- [ ] 6.2 配合列顺序列表，验证 PreparedStatement 可用 `row.get(columnIndex)` 按参数顺序绑定
- [ ] 6.3 验证 batch prepared 可用纯数组访问 `rows[i][j]`，无 Map 查找开销

## 7. 单元测试

- [ ] 7.1 测试 CSV 解析：标准 CSV（含逗号、引号、换行）
- [ ] 7.2 测试 CSV `null` 字符串转换为 Groovy `null`
- [ ] 7.3 测试 CSV 文件不存在时的错误处理（日志 + 空列表）
- [ ] 7.4 测试 CSV 解析失败时的错误处理
- [ ] 7.5 测试仅有 header 无数据行的处理
- [ ] 7.6 测试列名顺序保持一致
- [ ] 7.7 测试多表批量生成，每表有独立共享内存键
- [ ] 7.8 测试 Groovy 脚本语法正确性
- [ ] 7.9 运行全部单元测试并通过

## 8. 集成测试

- [ ] 8.1 端到端测试：生成 JSR223PreProcessor XML，嵌入 JMX 可被 `xml.etree.ElementTree` 解析
- [ ] 8.2 端到端测试：生成的 Groovy 脚本在 JMeter 中执行无语法错误
- [ ] 8.3 与 `jmx-skeleton-generator` 的 SharedMemorySetupThreadGroup 集成测试

## 9. Review 修复验证

- [ ] 9.1 确认设计文档（design.md）中已补充核心函数签名和代码示例（Finding #1）
- [ ] 9.2 确认设计文档中已补充 CSV 文件大小/加载时间的性能约束（Finding #2）
- [ ] 9.3 确认 spec.md 中已补充 CSV 完整性验证场景（Finding #3）
- [ ] 9.4 确认 spec.md 中已补充键命名规范和特殊字符处理（Finding #4）
- [ ] 9.5 确认 `utils/preprocessor_helpers.py` 不含共享内存读取函数（Finding #5）

## 10. 代码审查

- [ ] 10.1 提交代码审查
- [ ] 10.2 确认 review.md findings 全部解决后方可合并
