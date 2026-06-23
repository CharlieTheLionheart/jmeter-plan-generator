# Shared Memory Initializer - Proposal

## Why

JMeter 测试计划需要在运行时从 CSV 文件加载种子数据到共享内存，供写入线程拷贝和装配数据。当前设计将共享内存初始化逻辑分散在多个模块中，缺乏统一的职责划分。

## What Changes

- 新增 `shared-memory-initializer` 模块
- 负责从 CSV 文件加载种子数据并生成 JSR223PreProcessor Groovy 脚本
- 采用 `List[List[Any]]`（行优先）数据结构 + 列顺序列表
- 与 `seed-data-generator` 配合：CSV 文件由其生成，加载器由本模块生成

## Capabilities

### New Capabilities
- `shared-memory-initializer`: CSV 文件读取、Groovy 脚本生成、JSR223PreProcessor XML 生成

### Modified Capabilities
- `jmx-skeleton-generator`: 移除共享内存初始化相关逻辑，调用 `shared-memory-initializer` 获取 JSR223PreProcessor 组件
- `utils`: 移除 `preprocessor_helpers.py` 中的共享内存相关函数

## Impact

- 新增独立模块，职责单一清晰
- 减少模块间耦合，便于测试和维护
- 统一的共享内存数据结构设计（行优先存储）
- 支持直接写入和 PreparedStatement 两种写入策略