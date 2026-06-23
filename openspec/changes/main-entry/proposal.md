## Why

`main.py` 是 KaiwuDB SVT 测试计划生成器的 CLI 入口与端到端编排层，负责把 Parser、ColumnNamer、SeedGenerator、DDLGenerator、PreparedInsertTemplateGenerator、JmxBuilder 等模块串联成完整生成流水线。当前 `openspec/changes/` 下没有任何 change 覆盖 `main.py` 及端到端编排逻辑，导致架构图中“🔧 main.py”这一层在 openspec 规划里缺失，模块调用顺序、错误处理、退出码、输出物落地均无显式规格约束。

## What Changes

- 新增 `main.py` CLI 入口模块，支持：
  - 位置参数：输入 `test_model.yaml` 路径
  - 位置参数：输入 `test_cfg.yaml` 路径
  - `-o/--output-dir`：输出目录，默认当前目录
  - `-v/--verbose`：支持 `-v`（INFO）和 `-vv`（DEBUG）两级日志
- 实现模块编排流水线，按顺序调用：
  - `ModelParser` 解析 `test_model.yaml`
  - `TestParser` 解析 `test_cfg.yaml`
  - `ColumnNamer` 生成列名列表
  - `SeedGenerator` 生成列种子文件
  - `DDLGenerator` 生成 DDL
  - `PreparedInsertTemplateGenerator` 生成 PreparedStatement INSERT 模板（仅当 `write_config` 中存在 `single_prepared` / `batch_prepared` 时执行）
  - `JmxBuilder` 汇总生成最终 `.jmx`
- 实现错误处理与退出码：
  - 配置校验失败（`ValidationError`）：收集所有错误后一次性报告，退出码 `1`
  - 种子生成失败（`SeedGenerationError`）：中止，保留已生成的部分种子文件，退出码 `2`
  - DDL 生成失败（`DdlGenerationError`）：中止，输出日志，退出码 `3`
  - JMX 生成失败（`JmxGenerationError`）：中止，输出日志，退出码 `4`
  - 成功：退出码 `0`
- 实现输出物落地：
  - 在输出目录下生成 `<name>.jmx`
  - 在输出目录下生成 `seeds/{table}/{index}_{col_name}.{type}` 种子文件

## Capabilities

### New Capabilities
- `main-entry`: CLI 入口与端到端模块编排能力，包括参数解析、模块调用顺序、错误处理、退出码和输出物落地

### Modified Capabilities
（无）

## Impact

- 新增 `src/kwjdbc_svt/main.py` 作为项目 CLI 入口
- 统一使用 `logging` 模块管理日志，日志级别通过 `-v/-vv` 控制
- 为所有已有 openspec change 提供最终集成落点，明确模块实例化顺序和数据流
- 输出物格式影响用户后续使用 JMeter 运行 `.jmx` 的方式
- 需要为 `main.py` 编写 E2E 测试，验证示例配置能生成合法的 `.jmx` 和种子文件
