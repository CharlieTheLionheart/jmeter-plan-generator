# Quality Review

## 1. Boundary Conditions
**Status**: ⚠️ Warning

**Findings**:
- 共享内存环绕拷贝有覆盖：`start + batch_lines > total_rows` 时回绕到开头（spec 已覆盖）。
- `ms_step / batch_lines` 整数除法风险：若 `ms_step < batch_lines`，行内时间步长为 0，导致同批次时间戳重复。spec/design 未说明除法类型与精度处理。
- `batch_seq * ms_step` 长跑溢出风险：long 范围足够，但未声明 `batch_seq` 类型。
- 设备号回绕：`row_index % device_per_thread` 在 `device_per_thread = 0` 时除零。未见保护。
- 关系表 `ceil(total_rows / batch_lines)` 最后一批不足 batch_lines 时的尾批处理未明确（VALUES 行数固定还是动态）。

**Open Questions**:
- **OQ1 设备号格式**: 是否需要支持自定义前缀（默认为 `device_`）？影响占位符替换边界。
- **OQ2 时间戳列位置**: 是否需要支持时间戳列在非第一个位置？当前假设时间戳列为第一个参数——非首列时装配逻辑越界。

**Recommendations**:
- 明确时间戳除法使用浮点或保证 `ms_step >= batch_lines`，并定义最小步长。
- 增加 `device_per_thread > 0`、`batch_lines > 0` 前置校验。
- 关系表尾批：用动态 SQL 拼实际行数，或最后一批单独处理。
- 定型 OQ1：默认 `device_` 前缀，是否开放配置。
- 定型 OQ2：时间戳列位置约定（固定首列 or 可配置）。

## 2. Rollback Plan
**Status**: ✅ Pass

**Findings**:
- 纯新增功能模块，Migration Plan 声明"无需迁移"。
- 生成物为独立 JMX 线程组，回滚 = 不生成/移除该线程组，无数据迁移、无 schema 变更。

**Recommendations**:
- 无。新功能天然可回滚。

## 3. Test Coverage
**Status**: ⚠️ Warning

**Findings**:
- spec 场景覆盖 SQL 生成、批量、PreProcessor 拷贝、时间戳、占位符替换、关系表初始化——主路径全。
- 缺失负向/边界场景：除零、环绕、整数除法为 0、空种子集、`batch_lines=1`。
- 未声明验证手段：生成的 JMX 是否有结构校验 / Groovy 脚本是否有语法校验或运行冒烟。

**Recommendations**:
- 补边界场景到 spec。
- tasks 中加入：生成 JMX 后 XML schema 校验 + Groovy 脚本编译冒烟测试。

## 4. Backward Compatibility
**Status**: ✅ Pass

**Findings**:
- 无 Modified Capabilities，无破坏性变更。
- 依赖 config-parser / seed-data-generator / jmx-skeleton-generator 既有接口，未改其契约。
- `?ptag1?` 占位符为新约定，不影响既有种子文件格式（若旧文件无占位符则不触发替换）。
- **新增**: 表名限定名规范为新增约定，不破坏现有功能。

**Recommendations**:
- 文档说明：旧种子文件无 `?ptag1?` 时的行为（应原样写入）。
- ✅ **已解决**: 表名限定名规范已在 design.md 和 spec.md 中明确，与 DDL 生成器保持一致。

## 5. Task Granularity
**Status**: ❌ Fail

**Findings**:
- tasks.md 尚未创建，无法核对粒度。
- 占位符替换涉及两处不同公式：spec 行 64 `local_device_start + (row_index % device_per_thread)` 与行 58 `device_start + thread_index * device_per_thread`，需在任务中统一口径。

**Open Questions**:
- **OQ1 batch_lines 变量作用域**: 是否需要支持按表独立的 `batch_lines` 变量？影响 sampler 与 PreProcessor 任务拆分粒度。
- ~~**OQ2 线程索引获取方式**: `Integer.parseInt(vars.get("JMETER_THREAD_NAME"))` 不可行（线程名格式 `"Thread Group Name 1-1"` 无法直接解析）。需改用 `ctx.getThreadNum()` 或 `${__threadNum}`——**阻塞设备号计算任务**。~~ **✅ 已解决**: 采用 JMeter 内置函数 `${__threadNum}`。已在 design.md 中新增决策章节，在 spec.md 中统一设备号公式并新增 requirement。

**Recommendations**:
- ~~**先解决 OQ2**（线程索引获取方式），再拆任务。~~ **✅ OQ2 已解决**: 采用 `${__threadNum}`，已在设计文档中定型。
- **定型 OQ1**：`batch_lines` 全局共享 or 按表独立——决定变量传递方式与任务边界。
- ~~统一 spec 中两处设备号公式表述。~~ **✅ 已统一**: 全部使用 `${__threadNum}`，公式已更新为 `device_start + ${__threadNum} * device_per_thread + (row_index % device_per_thread)`。
- 任务建议拆分粒度：
  1. 设备号计算工具方法（含越界/除零保护，使用 `${__threadNum}`）
  2. JSR223PreProcessor Groovy 脚本（拷贝+克隆+环绕）
  3. 时间戳装配（明确除法精度）
  4. `?ptag1?` 占位符替换
  5. single_insert sampler 生成
  6. batch_insert sampler 生成（动态 `${batch_lines}`）
  7. 关系表 SetupThreadGroup + Loop Controller 初始化
  8. JMX/Groovy 校验冒烟

## Overall Assessment
**结论**: 设计与 Spec 主路径完整、回滚与兼容性良好。

已解决的关键问题包括：
- ✅ **线程索引获取方式**: 采用 `${__threadNum}`，已在 design.md 和 spec.md 中更新。
- ✅ **设备号公式统一**: 全部公式已更新为使用 `${__threadNum}` 的统一格式。
- ✅ **表名限定名规范**: 已在 design.md 中新增决策章节，spec.md 中明确所有 INSERT 语句必须使用限定名格式。
- ✅ **SQL标识符和关键字大小写策略**: 已在 design.md 中新增决策章节，统一所有 INSERT 语句中标识符和关键字使用小写，与 DDL 生成器保持一致。

阻塞项：
1. 边界保护（除零、整数除法、环绕尾批）需补 spec 与任务。

建议：解决边界保护问题后可生成 tasks.md。任务拆分目标 ≤ 1 文件/方法 粒度，每项可独立验证。
