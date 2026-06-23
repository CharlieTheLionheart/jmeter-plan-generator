# Quality Review

## 1. Boundary Conditions
**Status**: ⚠️ Warning

**Findings**:
- `total column count = 0` 与 `proportions list is empty` 返回空分配列表：已覆盖。
- `total > 0` 但 `proportions` 元素为负数、和不为 1、长度不匹配：未覆盖。
- `floor + greedy` 在 `total < len(proportions)` 时会得到多个 0 和少量 1，语义正确但未说明。
- 数据类型规范化：正则只提到去除长度/精度，未覆盖无括号类型、`[]` 数组类型、类型含空格等边界。
- 列序号映射：spec 说"starting from 1, excluding timestamp column"，但未说明多列组场景下是否全局连续还是按组连续。示例跨 `ptag`/`col` 全局 1/2/3，符合全局连续。

**Recommendations**:
- 增加异常输入处理：负数比例、比例和不为 1、类型为空字符串。
- 明确类型规范化正则支持的范围（至少 `type(precision,scale)`、`type[]`）。
- 文档说明 `total < len(proportions)` 时允许部分类型分配为 0。

## 2. Rollback Plan
**Status**: ✅ Pass

**Findings**:
- 纯新增模块，无既有数据、无 schema 变更。
- 回滚 = 不调用 column-namer，依赖模块回退到原有列名生成方式（若存在）。

**Recommendations**:
- 无。

## 3. Test Coverage
**Status**: ⚠️ Warning

**Findings**:
- 主路径覆盖：floor+greedy、列名格式、前缀映射、类型规范化、序号连续、index mapping。
- 缺失场景：异常比例输入、类型包含特殊字符、大 total 性能、列名冲突检测。
- 未明确单元测试策略（是否需要为分配算法写独立单元测试）。

**Recommendations**:
- 补充异常输入单元测试。
- 增加大列数（如 10k）性能/稳定性测试。
- tasks 中明确为 column-namer 写独立 Python 单元测试。

## 4. Backward Compatibility
**Status**: ✅ Pass

**Findings**:
- 新 capability，未修改既有接口。
- 输出列名格式 `{prefix}_{type}_{seq}` 为新约定，不影响旧文件（旧文件若不存在则无冲突）。

**Recommendations**:
- 无。

## 5. Task Granularity
**Status**: ⚠️ Warning

**Findings**:
- tasks.md 未创建，无法核对。
- 功能可拆为独立小任务：
  1. 分配算法实现
  2. 前缀映射字典
  3. 类型规范化正则
  4. 列名生成器
  5. 列序号映射返回
  6. 单元测试

**Recommendations**:
- 按上述 6 项拆 task，每项可独立验证。
- 无 Open Questions，可进入 tasks.md。

## Overall Assessment
**结论**: 设计与 Spec 完整度较高，无阻塞项，可直接进入 tasks.md。

建议：
1. 补充异常输入与类型规范化边界到 spec（可在实现阶段补充）。
2. tasks 中预留单元测试与性能测试任务。
3. 拆分为 6 个可独立验证的任务。
