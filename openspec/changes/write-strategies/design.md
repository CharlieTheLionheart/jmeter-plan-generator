## Context

写入策略层使用策略模式实现不同写入方式的插件化扩展。每个策略实现 `WriteStrategy` 接口，提供 SQL 生成、采样器配置、PreProcessor 代码等功能。

## Goals / Non-Goals

**Goals:**
- 定义 `WriteStrategy` 抽象基类
- 实现 5 种策略：single_insert、batch_insert、single_prepared、batch_prepared、schemaless
- 策略注册表机制
- 重构 direct-insert-write 使用策略模式

**Non-Goals:**
- 不在策略内实现具体业务逻辑（数据准备、时间戳装配等）
- 不实现 schemaless 的完整逻辑（T2）

## Decisions

### 抽象基类设计

**Decision:** `WriteStrategy` 定义以下抽象方法：
- `mode_name`: 返回策略名称
- `requires_prepared_insert_template()`: 是否需要 Prepared Insert 模板
- `generate_query()`: 生成 SQL 模板
- `get_sampler_type()`: 返回采样器类型（`JDBCSampler` / `JSR223Sampler`）
- `get_sampler_config()`: 返回额外配置
- `requires_param_setup()`: 是否需要参数组装预处理
- `get_preprocessor_code()`: 返回 PreProcessor 脚本
- `get_sampler_script()`: 返回 JSR223Sampler 脚本（仅 JSR223Sampler 策略）

**Rationale:**
- 清晰的接口定义
- 支持不同策略的不同需求
- 便于扩展新策略

**Alternatives considered:**
- **使用类属性而非方法**: 不够灵活
- **接口分离**: 增加复杂度

### 策略注册表

**Decision:** 使用字典 `STRATEGY_REGISTRY` 映射 `WriteMode` 到策略类。

**Rationale:**
- 简单直接
- 便于查找和实例化

**Alternatives considered:**
- **装饰器注册**: 增加复杂度
- **动态导入**: 不必要

### JSR223Sampler 用于 batch_prepared

**Decision:** `batch_prepared` 策略使用 `JSR223Sampler` 而非 `JDBCSampler`，因为后者无法一次绑定多组参数。

**Rationale:**
- JMeter `JDBCSampler` 的 `Prepared Update Statement` 每次只绑定一组参数
- `JSR223Sampler` 可以手写 JDBC batch 代码
- 通过 `get_sampler_type()` 返回 `"JSR223Sampler"` 通知 JMX 构建器

**Alternatives considered:**
- **使用多个 JDBCSampler**: 无法保证事务
- **使用自定义插件**: 过于复杂

## Risks / Trade-offs

### Risk: 策略状态管理
**Mitigation:** 策略为无状态类，每次调用返回结果。如有需要，将状态存储在调用方。

### Trade-off: PreProcessor 代码生成
**Rationale:** 将 PreProcessor 代码生成逻辑放在策略中，便于每个策略自定义。公共逻辑已提取到 `utils/preprocessor_helpers.py`，避免重复实现。策略只需要了解如何调用工具函数，而不需要了解完整的 Groovy 语法。

## Migration Plan

**步骤 (TDD - 测试先行):**
1. 在 `strategies/` 下创建 `base.py`（`WriteStrategy` ABC）
2. **编写** `SingleInsertStrategy` 和 `BatchInsertStrategy` 的单元测试用例
3. **实现** `SingleInsertStrategy` 和 `BatchInsertStrategy`，**验证测试通过**
4. **编写** `single_prepared` 策略的单元测试用例
5. **实现** `single_prepared` 策略，**验证测试通过**
6. **编写** `batch_prepared` 策略的单元测试用例（含 JSR223Sampler 脚本输出基准）
7. **实现** `batch_prepared` 策略，**验证测试通过**
8. **编写** `schemaless` 策略的单元测试用例（异常路径：验证抛出 `NotImplementedError`）
9. **实现** `schemaless` 策略（抛出 `NotImplementedError` 异常），**验证测试通过**
10. 重构 `direct-insert-write` 模块，使用策略而非直接生成，**验证重构前后输出等价性**

**PreProcessor 公共逻辑提取（步骤 2.5）：**

在实现各策略的 `get_preprocessor_code()` 之前，先提取公共逻辑到 `utils/` 模块：

- **共享内存读取工具函数**：`read_shared_memory(table_name)`
- **行数据复制工具函数**：`clone_rows(rows)`
- **时间戳计算工具函数**：`calculate_timestamps(base_time, batch_seq, ms_step, batch_lines)`
- **设备号计算工具函数**：`calculate_device_number(device_start, thread_num, device_per_thread, row_index)`
- **占位符替换工具函数**：`replace_placeholder(value, device_number)`
- **PreProcessor 脚本模板生成器**：`generate_preprocessor_template(strategy_specific_parts)`

这些工具函数将基于 `utils/xml_helpers.py` 生成的 JSR223PreProcessor 组件，将各策略生成的 SQL、script 等参数注入到统一的框架中。