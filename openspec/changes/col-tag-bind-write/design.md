# col-tag-bind-write Design

## Context

4000 列稀疏表（sparse fixture，commit `c14969f` / `9333117`）当前通过 `null_rate=0.99` + 全列 inline INSERT 实现"软稀疏"。生产负载的真实模式是"设备 ↔ 列子集"：一个设备只关心与其相关的列子集（如设备 1 关心列 1-5，其他列对它无效），并非"全列都激活但 99% 是 NULL"。

本 change 引入"列-tag 绑定写入模式"：**每表独立配置** `col_tag_bind_mode`，启用时**复用现有列种子文件**（Orchestrator 已生成），SetupTG 加载列种子文件 + 按 ptag 组合映射函数找到对应列子集，inline INSERT 子集列。

## Goals / Non-Goals

**Goals:**
- 每表独立 `col_tag_bind_mode` 开关（`write_config[].tbl_name` 项下），默认 `false`
- 启用时：Orchestrator 跳过该表行种子文件生成；列种子文件**复用现有**（`read_column_seed` / `write_column_seed` 已存在）
- SetupTG 复用现有加载行种子文件 sampler + `if` 分支；如启用追加新 sampler 加载列种子 + hash 初始化行内存
- 混合表（部分全行 + 部分列绑定）支持并行（OR 关系，非互斥）
- 写入 TG：ptag 组合 → hash 映射函数 → 找到对应列子集 → inline INSERT 子集
- 适用所有 5 种 mode（含 `schemaless`）
- INSERT 列名列表显式列出 NOT NULL 列（`ts` + 所有 `primary_tag` + 显式 `NOT NULL` 的 `data_col`）
- 701+ pytest 不 regress

**Non-Goals:**
- 不改变 DDL 生成（DDL 仍是全列）
- 不改造 sparse fixture 默认 99% NULL 路径（保留做回归基线）
- 不新增列种子文件 IO（复用现有）

## Decisions

### Decision 1: col_tag_bind_mode 是每表配置（与 mode 正交）

**Decision:** `col_tag_bind_mode` 加在 `write_config[].tbl_name` 项下（每表独立），不是 `write_config` 全局。

**Rationale:**
- 不同表可走不同写入语义（部分全行 + 部分列绑定）
- 与现有 5 种 mode 列表**正交**：`mode` 决定"怎么写"（inline / batch / schemaless 等），`col_tag_bind_mode` 决定"写多少列"
- 混合表场景是真实需求（同一 test plan 里 sparse 表用列绑定，rel 表用全行）

**Alternatives considered:**
- 新增 `mode: ptag_subset` —— 改动面大，侵入现有 dispatch；与 mode 列表冲突
- write_config 全局 `col_tag_bind_mode` —— 强制所有表统一，不支持混合

### Decision 2: SetupTG 复用现有 sampler + `if` 分支（OR 关系）

**Decision:** 复用现有 SetupTG 加载行种子文件 sampler，加 `if` 短路：
- 当前表 `col_tag_bind_mode=false`：加载行种子文件到内存（现状）
- 当前表 `col_tag_bind_mode=true`：跳过行种子加载

如果任意表开启了 `col_tag_bind_mode`，SetupTG **追加一个新 JSR223 Sampler**：加载列种子文件 + 按 hash 算法初始化行内存（OR 关系，与现有 sampler 并行）。

**Rationale:**
- 现有 sampler 路径已稳定，复用避免重构
- `if` 分支最小化侵入
- 追加 sampler 支持混合表（sparse 用列绑定、rel 用全行时，新旧 sampler 并行）

**Alternatives considered:**
- 新建独立 SetupTG TG —— JMX 结构复杂化
- 改写现有 sampler 内部加 column seed 加载逻辑 —— sampler 职责不清

### Decision 3: 复用现有列种子文件（不新生成）

**Decision:** 启用 `col_tag_bind_mode` 时**复用 Orchestrator 已生成的列种子文件**（per data_col），不新生成；只跳过行种子文件生成。

**Rationale:**
- 列种子文件已存在（`src/seed_data_generator/io.py` `read_column_seed` / `write_column_seed` + `orchestrator.py:92,121` 已调用）
- 列种子文件已按 `val_range` 预生成 values，无需运行时再生成
- 仅需跳过行种子文件（互斥：单表只能有其中一种）

**文件命名：** `{col_name}.{type}.csv`（与现有 `write_column_seed` 一致）

**Alternatives considered:**
- 运行时生成 12800 行种子 —— 已废弃（性能与现架构不符）

### Decision 4: ptag 组合 → 种子组映射函数 = hash mod N（多对一）

**Decision:** 映射函数 = `hash(ptag_tuple) mod N`，其中：
- `N = num_threads`（按写入线程分组）
- 每组行数 = `seed_num`（已确认）
- **多对一映射**：多个 ptag 组合可映射到同一组

**Rationale:**
- 组数 = `num_threads`（1-4 线程场景下，组数 ≤ 4）
- 总行数 = `num_threads × seed_num`（如 4 × 100 = 400），远少于原计划的 12800
- 多对一映射：避免 ptag 组合数远大于 num_threads 时的冗余

**Alternatives considered:**
- N = `ptag_combinations`（原计划 12800 行）—— 过大
- 顺序循环 mod N —— 依赖 ptag seed_num，ptag 数量变了映射变
- 显式配置 mapping —— 配置膨胀

### Decision 5: SharedMemory key 命名区分 = 混合表场景的强制需求

**Decision:** 列绑定表用 `__SHARED_MEM_{db}_{table}_bind`（独立 key），与现有 `__SHARED_MEM_{db}_{table}` 区分。

**Rationale:**
- 混合表场景的强制需求（同一 test plan 中 sparse 列绑定 + rel 全行）
- 现有 sampler 加载到 `__SHARED_MEM_{db}_{table}`（全行）
- 新 sampler 加载到 `__SHARED_MEM_{db}_{table}_bind`（列绑定）

**数据结构：**
- 全行：`__SHARED_MEM_{db}_{table}` → `List[List[str]]`（行为单位）
- 列绑定：`__SHARED_MEM_{db}_{table}_bind` → `{group_id: {col_names: [...], row_values: [...]}}`（按组索引）

### Decision 6: NOT NULL 列强制列入 INSERT

**Decision:** INSERT 列名列表必须包含 `ts` + 所有 `primary_tag` + 显式 `NOT NULL` 的 `data_col`。

**Rationale:**
- KaiwuDB 时序表 `ts` / `primary_tag` 通常 NOT NULL（spec 明确）
- **已查官网**：KaiwuDB 部分列 INSERT 不需要列顺序匹配，只要值类型与列类型对应即可
- 保守做法仍不省略 `ts`（不依赖 server 自动 NOW()）

### Decision 7: 适用所有 5 种 mode（含 schemaless）

**Decision:** `col_tag_bind_mode` 适用所有 5 种 mode（`single_insert` / `batch_insert` / `single_prepared` / `batch_prepared` / `schemaless`）。

**Rationale:**
- 列-tag 绑定是**与 mode 正交**的能力，逻辑上不依赖 mode
- 现有 4 种 SQL mode 都走 inline INSERT 路径（见 `_build_inline_sql_preprocessor_script`），底层拼装相同
- schemaless 走 HTTP/InfluxDB Line：InfluxDB Line 协议中部分列值对从 bind 模式内存种子组取（语义与 SQL INSERT 部分列一致）

**Alternatives considered:**
- 仅 batch_prepared——人为限制，不必要
- 仅 4 种 SQL mode——不必要，schemaless 也支持

### Decision 8: schemaless 路径集成 = InfluxDB Line 部分列从 bind 内存种子组取

**Decision:** schemaless 模式下，HTTP/InfluxDB Line 协议 body 中**部分列值对**从 bind 模式内存种子组（`__SHARED_MEM_{db}_{table}_bind`）取，按当前 ptag 所属组的 `col_names` 列表只填那几列。

**Rationale:**
- 与 SQL 模式部分列 INSERT 语义一致
- 不依赖 InfluxDB Line 协议新特性
- 复用 SetupTG 的 bind 内存种子组（已有 JSR223 Sampler 加载）

## Open Questions（设计阶段已收敛）

### 已收敛 ✅
1. 配置位置：每表独立（`write_config[].tbl_name` 项下）
2. SetupTG 位置：复用现有 sampler + if 分支 + 追加新 sampler
3. 种子文件：复用现有列种子文件（不新生成）
4. 映射函数：hash mod N（N = num_threads）+ 多对一
5. 每组行数：seed_num
6. SharedMemory 命名：`_bind` 后缀（混合表场景的强制需求）
7. NOT NULL 列：强制列入
8. mode 范围：所有 5 种 mode（含 schemaless）
9. schemaless 集成：InfluxDB Line 部分列值对从 bind 内存种子组取
10. 反退化测试（单元 + 冒烟）：验证 hash(ptag_tuple) mod num_threads 不退化为单组（实现：测试用例，不做功能）

## Migration Plan

无需迁移。

- 默认 `col_tag_bind_mode=false`（每表选项）：现有 fixture 行为不变
- 启用：用户主动在 `write_config[].tbl_name` 项下配置 `col_tag_bind_mode: true` + `col_num_per_tag: N`
- DDL 不变（仍是全列）
- 写入层加分支，不影响 `col_tag_bind_mode=false` 路径
- 列种子文件向后兼容（无条件生成）
- 行种子文件向后兼容（仅在 `col_tag_bind_mode=true` 时跳过）
