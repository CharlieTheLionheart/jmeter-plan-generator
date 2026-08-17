# col-tag-bind-write：列-tag 绑定写入模式

## Why

4000 列稀疏表（sparse fixture，commit `c14969f` / `9333117`）当前通过 `null_rate=0.99` + 全列 inline INSERT 实现"软稀疏"——但与生产负载不符：

- **payload 浪费**：4000 列 INSERT + 99% NULL，wire/解析开销巨大
- **缺语义**：实际场景里"设备 ↔ 列子集"是有意义的（如设备 1 关心列 1-5，其他列对它无效），并非"全列都激活但 99% 是 NULL"
- **路径不一致**：server 端 INSERT 路径与生产"按设备写相关列"的真实负载模式不匹配

需要一个**显式列子集写入**模式：ptag 组合 → 映射函数 → 找到对应列子集 → inline INSERT 子集。

## What Changes

- 新增每表独立配置（**在 `write_config[].tbl_name` 项下**，非 write_config 全局）：
  - `col_tag_bind_mode: bool` — 启用列-tag 绑定写入模式（默认 `false`）
  - `col_num_per_tag: int` — 每个 ptag 绑定几个数据列
- 启用时：Orchestrator 跳过该表**行种子文件**生成（**列种子文件已存在**，复用现有 `read_column_seed` / `write_column_seed` API）
- SetupTG 复用现有"加载行种子文件到内存" sampler + `if` 分支：
  - `col_tag_bind_mode=false`：加载行种子文件到内存（现状）
  - `col_tag_bind_mode=true`：不加载行种子文件；如果任意表开启了模式，**追加**新 JSR223 Sampler 加载列种子文件 + 按 hash 函数初始化行内存
- 写入 TG：按 ptag 组合 → hash 映射函数 → 找到对应列子集 → inline INSERT 子集
- INSERT 列名列表必须包含所有 NOT NULL 列（`ts` + 所有 `primary_tag` + 显式 `NOT NULL` 的 `data_col`）
- 适用**所有 5 种 mode**（`single_insert` / `batch_insert` / `single_prepared` / `batch_prepared` / `schemaless`）

## Capabilities

### New Capabilities
- `col-tag-bind-write`: 列-tag 绑定写入模式（per-table 配置 + 复用列种子文件 + hash 映射函数 + inline INSERT 子集）

### Modified Capabilities
- 无（与现有 5 种 mode 列表并行；`col_tag_bind_mode` 是与 mode 正交的能力）

## Impact

**受影响模块：**
- `src/config_parser/` — 解析每表 `col_tag_bind_mode` / `col_num_per_tag` 字段 + Pydantic 校验
- `src/seed_data_generator/orchestrator.py` — 识别 `col_tag_bind_mode=true` 时跳过该表**行种子文件**生成
- `src/jmx_skeleton_generator/generators/write_groups.py` — 现有 SetupTG sampler 加 `if` 分支；追加新 sampler 加载列种子文件 + hash 初始化行内存
- `src/jmx_skeleton_generator/generators/write_groups.py` — 写入 TG 列子集选择分支

**不影响：**
- 现有 `batch_prepared` 全行路径（`col_tag_bind_mode=false` 默认行为不变）
- 现有 SetupTG 加载行种子文件 sampler（仅加 `if` 短路）
- DDL 生成（DDL 仍是全列）
- sparse fixture 现有 99% NULL 路径（保留做回归基线）
- 现有 701+ pytest（`col_tag_bind_mode` 默认 `false` 不触发新代码路径）
- 列种子文件 IO 接口（`read_column_seed` / `write_column_seed` 已存在，不需新增）
