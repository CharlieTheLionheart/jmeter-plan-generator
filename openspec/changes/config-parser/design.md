## Context

KaiwuDB SVT 测试计划生成器需要支持通过 YAML 配置文件定义复杂的测试场景，包括关系库和时序库的混合模式、多种列类型、种子数据生成规则等。配置解析是生成器的核心基础模块，其输出将被 DDL 生成器、种子数据生成器和 JMX 生成器使用。

当前项目使用 Python 3.12+ 作为开发环境。

## Goals / Non-Goals

**Goals:**
- 实现健壮的 YAML 配置文件解析器
- 提供全面的配置校验能力，在生成阶段尽早发现配置错误
- 输出结构化的配置数据模型供下游模块使用
- 支持所有规格书中定义的配置字段和校验规则

**Non-Goals:**
- 不提供配置文件编辑或补全功能
- 不提供配置文件的版本迁移功能
- 不在解析阶段处理配置的业务逻辑（如列名生成、seed_num 采样等）

## Decisions

### 使用 PyYAML 作为 YAML 解析库

**Decision:** 使用 PyYAML（`yaml` 模块）作为 YAML 文件解析库。

**Rationale:**
- PyYAML 是 Python 生态中最成熟的 YAML 解析库
- 与 Python 3.12+ 兼容性好
- 支持自定义类型加载，便于实现类型转换

**Alternatives considered:**
- **ruamel.yaml**: 功能更强大但更复杂，当前需求不需要其高级特性
- **手动解析**: 过于复杂，容易出错，不利于维护

### 使用 Pydantic 进行数据校验

**Decision:** 使用 Pydantic（`pydantic` 模块）定义数据模型并进行校验。

**Rationale:**
- Pydantic 提供声明式的数据模型定义，与配置结构高度匹配
- 内置类型校验和自定义校验器支持
- 自动生成友好的错误消息
- 广泛用于 Python 项目，社区支持良好

**Alternatives considered:**
- **手动校验**: 代码量大，难以维护，错误消息不一致
- **jsonschema**: 适用于 JSON，对 YAML 支持较弱

### 数据模型设计

**Decision:** 使用分层的数据模型结构，所有 Pydantic 模型统一实现在 `src/config_parser/models.py` 中，作为本 change 的核心交付物之一：
- `TestModelConfig`: 顶层配置，包含 `rel_dbs` 和 `ts_dbs`
- `DatabaseConfig`: 库级别配置
- `TableConfig`: 表级别配置
- `ColTypeConfig`: 列类型配置（用于 `primary_keys`、`regular_tags`、`data_cols`）
- `PrimaryTagColTypeConfig`: Primary Tag 专用列类型配置（不含 `nullable` 字段）
- `TestConfig`: 测试配置，包含 `conn_config`、`write_config`、`query_config`

**Rationale:**
- 分层设计对应配置文件的嵌套结构，代码可读性强
- 每层负责自己的校验逻辑，职责清晰
- 便于后续扩展新的配置字段
- `PrimaryTagColTypeConfig` 专用于 `primary_tags`，通过模型结构强制约束 `nullable` 字段不可出现，确保业务规则在模型层面得到保证

**Alternatives considered:**
- **扁平化设计**: 无法表达配置的层级关系，不利于理解和维护
- **动态字典**: 类型不安全，容易在运行时出错
- **共用 ColTypeConfig**: 需要在校验阶段检查 `nullable=false`，但用户仍可能在配置中错误地设置 `nullable=true`，导致运行时才发现错误

### Primary Tag nullable 约束的建模方式

**Decision:** 为 `primary_tags` 定义专用的 `PrimaryTagColTypeConfig` 模型，该模型**不包含 `nullable` 字段**。如果用户在配置中为 primary_tags 的列添加 `nullable` 字段，Pydantic 会在解析阶段直接报错，实现编译时级别的约束。

**模型定义：**
```python
class PrimaryTagColTypeConfig(BaseModel):
    col_type: str
    type_proportion: float
    val_range: Optional[str] = None

    # 不包含 nullable 字段，强制约束 Primary Tag 不可为 NULL
```

**Rationale:**
- KaiwuDB 的业务规则明确要求 Primary Tag 列必须为 `NOT NULL`，这是强约束而非可选配置
- 通过模型结构直接禁止 `nullable` 字段出现，比校验阶段检查更彻底
- 错误消息会明确提示 "Extra fields are not permitted"，帮助用户快速定位问题
- 避免用户在配置中错误地设置 `nullable=true`，导致运行时才发现错误

**Alternatives considered:**
- **沿用 ColTypeConfig 并在校验阶段检查 nullable=false**: 允许配置中出现 `nullable` 字段，运行时校验报错。问题：错误发现较晚，且用户可能误以为 Primary Tag 支持 nullable。
- **允许 nullable 字段但强制为 false**: 模型包含 `nullable` 字段但固定为 `False`。问题：增加了不必要的字段，语义不清晰。

### 复用 `utils/val_range_parser` 解析 val_range

**Decision:** `val_range` 表达式的分类识别与字段提取复用 `utils/val_range_parser.py`，本模块在此基础上进行业务规则校验（如开区间是否包含合法整数、外键引用格式等）。

**Rationale:**
- 避免与 `seed-data-generator` 重复实现解析逻辑
- 统一解析结果的数据结构，降低下游模块使用成本

**Alternatives considered:**
- **在 `parser.py` 内直接解析**: 会导致多处重复代码，维护困难

### 校验策略

**Decision:** 采用"两阶段校验"策略：
1. **结构校验**：使用 Pydantic 的基础类型校验，检查必填字段、字段类型等
2. **业务规则校验**：在数据模型加载后进行自定义校验，检查 `type_proportion` 总和、外键引用格式、Primary Tag 约束等

**Rationale:**
- 结构校验快速失败，减少不必要的计算
- 业务规则校验可以访问完整的数据模型，支持跨字段校验
- 错误消息清晰，便于用户定位问题

**Alternatives considered:**
- **单阶段校验**: 将所有校验放在 Pydantic 模型中，导致模型过于复杂
- **延迟校验**: 在下游模块中校验，无法在解析阶段暴露问题

### 错误处理策略

**Decision:** 配置解析失败时立即抛出异常，不返回部分配置。

**Rationale:**
- 配置错误无法生成有效的测试计划，需要尽快中断
- 避免下游模块处理无效配置产生不可预测的结果

**Alternatives considered:**
- **返回部分配置**: 下游模块需要处理空值，增加复杂度
- **收集所有错误后报告**: 虽然更友好，但实现复杂，当前需求不强

## Risks / Trade-offs

### Risk: Pydantic 校验规则过于复杂，维护困难
**Mitigation:** 将复杂的校验规则拆分为独立的函数，并添加单元测试覆盖。

### Risk: 外键引用校验需要访问完整的配置模型
**Mitigation:** 在所有配置加载完成后进行外键校验，可能需要两轮校验（单表校验 + 跨表校验）。

### Trade-off: 不支持配置文件继承或模板
**Rationale:** 当前规格书中没有此需求，保持简单。未来可以通过 `extends` 字段扩展。

## Migration Plan

无需迁移。这是一个新功能模块，不影响现有代码。