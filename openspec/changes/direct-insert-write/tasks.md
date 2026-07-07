# Tasks: direct-insert-write

## 0. 范围与依赖确认

- [x] 0.1 确认范围：single_insert、batch_insert 模式，从共享内存读取行数据，时间戳和设备号装配
- [x] 0.2 确认 OQ1 已决策：`batch_lines` 按表独立（每表可有独立 batch_lines 配置）
- [x] 0.3 确认 OQ2 已决策：时间戳列固定为第一个参数位置（设计文档已明确）
- [x] 0.4 确认依赖 `shared-memory-initializer`（共享内存读取）
- [x] 0.5 确认依赖 `utils/preprocessor_helpers`（时间戳/设备号计算公共函数）
- [x] 0.6 确认表名使用限定名 `db.table`，SQL 标识符和关键字统一小写

## 1. 模块骨架

- [x] 1.1 确认 `src/direct_insert_write/` 目录结构
- [x] 1.2 创建 `src/direct_insert_write/__init__.py` 导出公共 API
- [x] 1.3 添加模块 docstring

## 2. 单条 INSERT SQL 生成

- [x] 2.1 实现 `generate_single_insert_sql(table_name, columns)` 返回 `insert into db.table (col1, col2) values (?, ?)` 格式
- [x] 2.2 表名使用限定名格式 `database.table_name`
- [x] 2.3 所有标识符和关键字统一小写
- [x] 2.4 边界：columns 为空时抛 `DirectInsertGenerationError`（继承 `DdlGenerationError`，可被现有 `except DdlGenerationError` 兜住）

## 3. 批量 INSERT SQL 生成

- [x] 3.1 实现 `generate_batch_insert_sql(table_name, columns, batch_lines)` 返回带固定行数的 VALUES
- [x] 3.2 VALUES 行数固定为 `batch_lines`
- [x] 3.3 尾批处理：最后一批不足 `batch_lines` 时单独生成对应行数的 SQL
- [x] 3.4 边界：`batch_lines <= 0` 时抛 `DirectInsertGenerationError`（同上，向上兼容旧 `except DdlGenerationError`）

## 4. JSR223PreProcessor 数据装配脚本

- [x] 4.1 实现 `generate_preprocessor_script(table_config, device_per_thread)` 返回 Groovy 脚本
- [x] 4.2 从共享内存读取行数据：`props.get("__SHARED_MEM_{db}.{table}")`
- [x] 4.3 时间戳计算：调用 `utils/preprocessor_helpers.calculate_timestamps()`
- [x] 4.4 设备号计算：调用 `utils/preprocessor_helpers.calculate_device_number()` 使用 `${__threadNum}`
- [x] 4.5 第一个 ptag 占位符 `${device_code}` 替换为 `device_{device_number}`
- [x] 4.6 行数据克隆：`utils/preprocessor_helpers.clone_rows()`
- [x] 4.7 边界：`ms_step < batch_lines` 时时间戳计算说明（整数除法，`ms_step / batch_lines` 可能为 0）

## 5. JDBCSampler 配置生成

- [x] 5.1 实现 `generate_jdbc_sampler_config(mode, sql, batch_lines=None)` 返回配置字典
- [x] 5.2 `single_insert` 模式：`usePrepared=False`
- [x] 5.3 `batch_insert` 模式：`usePrepared=False`，batch_size 设置为 `batch_lines`

## 6. 关系表初始化

- [x] 6.1 确认关系表在 SetupThreadGroup 中一次性写入
- [x] 6.2 实现 `generate_relational_table_init_sampler(table_name, columns, total_rows)` 使用 batch_insert 策略
- [x] 6.3 使用 Loop Controller 处理大数据集

## 7. 单元测试

- [x] 7.1 测试 `generate_single_insert_sql` 输出格式正确
- [x] 7.2 测试限定名格式 `db.table`
- [x] 7.3 测试关键字/标识符小写
- [x] 7.4 测试 `generate_batch_insert_sql` VALUES 行数正确
- [x] 7.5 测试尾批处理
- [x] 7.6 测试 `batch_lines <= 0` 抛异常
- [x] 7.7 测试设备号计算使用 `${__threadNum}`
- [x] 7.8 测试 `${device_code}` 替换
- [x] 7.9 测试 `device_per_thread = 0` 抛异常
- [x] 7.10 测试时间戳除法精度说明
- [x] 7.11 运行全部单元测试并通过

## 8. 集成测试

- [x] 8.1 端到端：生成的 JMX 片段可被 JMeter 解析
- [x] 8.2 Groovy 脚本语法正确性验证

## 9. Review 修复验证

- [x] 9.1 确认 OQ1（batch_lines 作用域）已决策为按表独立
- [x] 9.2 确认 OQ2（时间戳列位置）已决策为首列
- [x] 9.3 确认 `${__threadNum}` 使用已统一
- [x] 9.4 确认 spec 中两处设备号公式已统一口径
- [x] 9.5 确认边界保护（除零、整数除法、环绕尾批）已在 spec/实现中处理

## 10. 代码审查

- [x] 10.1 提交代码审查（本项目仅 owner 自审，无 PR 提交）
- [x] 10.2 确认 review.md findings 全部解决后方可合并（详见 review.md 2026-07-09 决议：OQ1/OQ2 关闭、阻塞项 #1 切换 long、尾批伪命题关闭、函数名对齐 tasks.md）