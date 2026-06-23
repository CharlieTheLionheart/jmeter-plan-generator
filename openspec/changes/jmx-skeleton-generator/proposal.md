## Why

KaiwuDB SVT 测试计划生成器的最终输出是 JMeter 测试计划（.jmx 文件）。JMX 生成器需要根据配置创建 JMeter 测试计划的骨架结构，包括 SetupThreadGroup（DDL 执行和共享内存初始化）、写入线程组、查询线程组等。

## What Changes

- 新增 JMX 骨架生成模块，支持：
  - JMeter 测试计划 XML 结构生成
  - SetupThreadGroup (DDL 执行)：执行建库建表语句
  - SetupThreadGroup（共享内存初始化）：加载行种子总集到共享内存
  - 写入线程组骨架（每个表一个线程组）
  - 查询线程组骨架（每个查询一个线程组）
  - JMeter 基础组件（TestPlan、ThreadGroup、JDBCSampler 等）
  - 变量定义（`${db_url}`、`${conn_pool_size}`、`${device_start}` 等）

## Capabilities

### New Capabilities
- `jmx-skeleton-generation`: JMX 测试计划骨架生成能力

### Modified Capabilities
（无）

## Impact

- 依赖 config-parser 模块提供测试配置
- 依赖 seed-data-generator 模块提供行种子总集路径
- 新增 JMX 生成模块，使用 Python 的 XML 库生成 JMX 文件
- 生成的 JMX 文件将被其他模块（写入方式、查询功能）进一步填充具体内容