# Quality Review

## 1. Boundary Conditions
**Status**: ⚠️ Warning

**Findings**:
- `type_proportion` 总和校验为 1.0：浮点相等判断需容差（如 `0.1+0.2`）。spec 未声明 `abs(sum-1.0) < eps` 容差，直接相等会误报。
- `with_hash` 范围 [1, 50000] 已覆盖；但 `primary_tag_count` 仅校验 ≤4，未校验下限（0 或负）。
- `null_rate` 边界：`round(seed_num × null_rate)` 在 null_rate=1.0 时全 null、=0 时无 null，但 `null_rate > 1.0` 或负值未明确拒绝。
- 整数开区间空值检测（`(1,2)`）已覆盖；闭区间 `[5,5]` 单值、`[10,1]` 逆序未覆盖。
- 外键引用循环检测未定型——A.ref→B、B.ref→A 时下游采样死锁风险。
- val_range 复用 `utils/val_range_parser`，但该依赖（utils change）状态未确认，跨 change 依赖边界需核对。

**Open Questions**:
- **OQ1 外键循环引用检测**: 是否需要支持？影响跨表业务规则校验复杂度。

**Recommendations**:
- 明确 `type_proportion` 总和使用浮点容差。
- 补 `primary_tag_count >= 0`、`null_rate ∈ [0,1]`、区间逆序/单值边界校验。
- 定型 OQ1。

## 2. Rollback Plan
**Status**: ✅ Pass

**Findings**:
- 纯新增模块，不影响现有代码（design 已声明）。
- 失败立即抛异常、不返回部分配置——回滚语义干净。

**Recommendations**:
- 无。

## 3. Test Coverage
**Status**: ⚠️ Warning

**Findings**:
- spec 场景丰富：两文件解析、type_proportion、nullable/null_rate、primary_tag 类型/数量/长度限制、tag 类型限制、val_range 各形态、外键格式、整数区间、列数计算、num_threads 一致性、query 占位符绑定、retentions 覆盖、with_hash。覆盖面广。
- 缺失：浮点容差用例、val_range 解析失败用例（非法正则、enum 空值）、跨表外键引用不存在的目标列、query 占位符引用不存在列。
- 未声明测试组织（Pydantic 模型校验 vs 业务规则校验分层是否分别测试）。

**Open Questions**:
- **OQ1 错误消息国际化**: 是否需要支持多语言错误消息？影响错误报告测试范围。倾向延后（当前单语言足够）。

**Recommendations**:
- 补上述负向用例到 spec 或 tasks。
- 两阶段校验（结构 + 业务规则）各写独立单元测试。

## 4. Backward Compatibility
**Status**: ✅ Pass

**Findings**:
- 新 capability，无 Modified。新增 `pyyaml` + `pydantic` 依赖需登记到项目依赖清单。
- 配置文件路径硬编码 `test_model.yaml`/`test_cfg.yaml`，不影响兼容但限制灵活性。

**Open Questions**:
- **OQ1 配置文件路径**: 是否需要支持自定义配置文件路径？当前硬编码固定文件名。可延后，非阻塞。

**Recommendations**:
- 确认依赖已加入 requirements/pyproject。
- OQ1（自定义路径）可延后，非阻塞。

## 5. Task Granularity
**Status**: ⚠️ Warning

**Findings**:
- tasks.md 未创建。
- 模块可拆为清晰小任务：models.py 各模型、PyYAML 加载、结构校验、业务规则校验（按规则逐条）、val_range 复用对接、错误报告。

**Open Questions**:
- ~~**OQ1 primary_tags nullable 建模**: 沿用 `ColTypeConfig` 仅校验值为 `false`，还是为 `primary_tags` 单独定义不含 `nullable` 字段的模型直接拒绝该键？**决定 models.py 结构与校验任务拆分**，应先定型。~~ **✅ 已解决**: 采用方案B，为 `primary_tags` 定义专用的 `PrimaryTagColTypeConfig` 模型，该模型不包含 `nullable` 字段。已在 design.md 和 spec.md 中更新。

**Recommendations**:
- ~~**先定型 OQ1**（primary_tags nullable 建模方式），再拆 models.py 任务。~~ **✅ OQ1 已定型**: 采用专用模型 `PrimaryTagColTypeConfig`，不包含 `nullable` 字段。
- 建议任务拆分：
  1. `models.py` Pydantic 模型定义（5 层）
  2. PyYAML 加载 + 语法错误处理
  3. 结构校验（必填字段）
  4. 业务规则校验：type_proportion 总和
  5. 业务规则校验：nullable/null_rate
  6. 业务规则校验：primary_tags 约束（类型/数量/长度/nullable）
  7. 业务规则校验：tag 类型限制
  8. val_range 对接 utils + 外键格式 + 整数区间
  9. 跨表外键引用校验
  10. write_config num_threads 一致性 + query 占位符绑定
  11. 单元测试
- 每项独立可测。

## Overall Assessment
**结论**: Spec 校验规则完整、回滚与兼容性良好。存在若干边界/职责澄清。

阻塞 / 待澄清：
1. ~~**primary_tags nullable 建模**（Task Granularity OQ1）必须先定型——影响 models.py 结构。~~ **✅ 已解决**: 采用专用模型 `PrimaryTagColTypeConfig`，已在 design.md 和 spec.md 中更新。
2. ~~**职责重叠**：spec "Calculate actual column counts" 与 column-namer change 的列数分配重叠，且与本 design Non-Goals 矛盾，需明确归属。~~ **✅ 已解决**: 从 config-parser spec 中移除"Calculate actual column counts" requirement，因为实际的列数计算（使用 floor + 贪心算法）属于 column-namer change 的职责。config-parser 仅负责配置验证，如 `type_proportion` 总和等于 1.0。
3. 浮点容差、外键循环检测（Boundary OQ1）需定型。

建议：解决 1、2 后再生成 tasks.md。各章节 OQ（外键循环 / 配置路径 / 国际化）可标记延后，不阻塞。
