# OpenSpec 剩余待解决问题清单

**最后更新**: 2026-06-29 (throughput-control 单位决策：统一使用 JMeter 原生次/分钟，用户自行换算)

---

## ✅ 已解决

### config-parser - primary_tags nullable 建模
- ✅ **已解决**: 采用专用模型 `PrimaryTagColTypeConfig`，不包含 `nullable` 字段
- 已更新 design.md 和 spec.md

### direct-insert-write - 线程索引获取方式
- ✅ **已解决**: 采用 JMeter 内置函数 `${__threadNum}`
- 已更新 design.md 和 spec.md，公式已统一

### ddl-generator - DDL 语句分隔符与表名限定名
- ✅ **已解决**: 支持分号分隔多语句执行，CREATE TABLE 必须使用限定名（`database.table`）
- 已确认 KaiwuDB 支持 `CREATE DATABASE; CREATE TABLE;` 一次执行
- 明确要求整个测试计划中表名都使用限定名形式，已更新 design.md 和 spec.md

### ddl-generator - SQL 标识符和关键字大小写策略
- ✅ **已解决**: 统一所有 SQL 标识符和关键字使用小写
- 虽然KaiwuDB对未加引号标识符的大小写不敏感，但为规范易读，测试计划内所有SQL语句标识符和关键字统一使用小写
- 已在 ddl-generator、direct-insert-write、prepared-insert-template、query-functionality 的 design.md 中添加决策说明

### jdbc-datasource - 动态参数范围与驱动类
- ✅ **已解决**: 本期仅暴露 `db_url` 和 `conn_pool_size` 两个动态参数（`db_username`/`db_password` 沿用既有变量），不动态生成任意 `conn_config` 参数
- 连接池参数（`connectionAge`/`timeout`/`trimInterval`）维持硬编码，列为 Non-Goal
- `driver` 固定为 `com.kaiwudb.Driver`，本期仅支持 KaiwuDB
- 其他参数的暴露后续按需添加
- 已更新 design.md、review.md（同时解决 jmx-skeleton-generator 的 conn_config 动态生成 Open Question）

---

## 🔴 必须解决（Hard Blocking）

### 1. ddl-generator - KaiwuDB 语法细节未确认
**模块**: `openspec/changes/ddl-generator/`
**影响**: 直接影响 DDL 生成的正确性，无法进入实现阶段

**阻塞项**：
1. ~~**DDL 语句分隔符**: KaiwuDB 对分号分隔的多语句支持情况~~
   - ~~问题：是否支持 `CREATE DATABASE; CREATE TABLE;` 一次执行~~
   - ✅ **已确认**: 支持分号分隔多语句一次执行
   - ✅ **新增约束**: CREATE TABLE 必须使用带数据库名的限定名（`database.table`）

2. ~~**大小写策略**: KaiwuDB 对未加引号标识符的大小写敏感性~~
   - ~~问题：未加引号的表名/列名是否区分大小写~~
   - ~~待确认：查阅 KaiwuDB 官方文档~~
   - ✅ **已解决**: 统一所有 SQL 标识符和关键字使用小写，已更新 design.md 和 review.md

3. ~~**错误处理策略**: 单表生成失败时是终止还是继续~~
   - ~~问题：Design Open Question #3 未解决~~
   - ~~待决策：默认继续生成其他表 + 收集错误列表，还是终止整个流程~~
   - ~~建议：默认继续生成，错误列表供调用方处理~~
   - ✅ **结论**：该问题不成立。DDL 生成器是文本生成任务，真正的失败（如格式化错误）会导致 Python 异常退出，无法继续；SQL 语法错误只在执行时才发现，超出生成器职责范围。正确的处理方式是在配置解析阶段验证输入，生成器内部任何异常应立即抛出终止。

4. **partition_interval 语法位置**: 在 KaiwuDB DDL 中的正确位置
   - ✅ **已解决**: 已在 docs/specs/kwdb-svt-test-plan-generator-spec.md 8.2 章节补充完整语法
   - 修正：时序库建库语法为 `CREATE TS DATABASE name [RETENTIONS keep_duration] [PARTITION INTERVAL interval] [COMMENT [=] comment_text];`，不需要 WITH 关键字和单引号
   - 已更新 spec.md、review.md

**行动**：ddl-generator 所有硬阻塞问题已解决，可以进入实现阶段

---

### seed-data-generator - 核心实现细节未决
- ✅ **已解决**: 所有 3 个阻塞项已解决
- 已采用 CSV 格式作为行种子总集和列种子文件格式
- 采用预生成主键列种子文件策略处理外键引用
- 已更新 design.md 和 review.md

---

### config-parser - 职责重叠
- ✅ **已解决**: 列数计算归属 column-namer change，已从 config-parser spec 中移除相关 requirement
- config-parser 仅负责配置验证（如 `type_proportion` 总和等于 1.0）
- column-namer 使用 floor + 贪心算法计算实际列数并生成列名
- 已更新 spec.md 和 review.md

---

## ⚠️ 高优先级（影响任务边界）

### 4. write-strategies - ✅ 已完全解决
**模块**: `openspec/changes/write-strategies/`
**影响**: 已优化为 TDD 模式，风险可控，公共逻辑已提取

**解决项**：
1. **✅ Migration Plan 粒度问题**: 已重构为 TDD 模式
   - 解决方案：
     - 采用测试驱动开发：每个策略实现前先编写测试用例
     - 步骤 4 已拆分为独立子步骤：single_prepared、batch_prepared、schemaless（各含测试前置）
     - 每个步骤都包含明确的 Definition of Done（验证测试通过）
   - ✅ Open Question: PreProcessor 代码复用 - 已提取公共逻辑到 `utils/preprocessor_helpers.py`

2. **✅ 边界条件已补齐**：
   - `SchemalessWriteStrategy.get_sampler_script()` 现在抛出明确的 `NotImplementedError` 异常，而非返回 `null`

3. **✅ PreProcessor 公共逻辑提取**：
   - 已在 `utils/preprocessor_helpers.py` 中提供以下工具函数：
     - `read_shared_memory(table_name)`: 共享内存读取
     - `clone_rows(rows)`: 行数据复制
     - `calculate_timestamps(...)`: 时间戳计算
     - `calculate_device_number(...)`: 设备号计算
     - `replace_placeholder(...)`: 占位符替换
     - `generate_preprocessor_template(...)`: PreProcessor 脚本模板生成器
   - 各策略通过 `xml_helpers.py` 生成的 JSR223PreProcessor 组件，将 SQL、script 等参数注入
   - `BatchPreparedStatementStrategy` batch size 上限、连接超时、异常回滚边界
   - `STRATEGY_REGISTRY` 未知 mode 的防御行为
   - `get_sampler_config()` key 缺失时的默认值

**行动**：重构 Migration Plan，补齐边界条件到 spec

---

### 5. jmx-skeleton-generator - ✅ 共享内存数据结构已定型
**模块**: `openspec/changes/jmx-skeleton-generator/`

**解决项**：
1. ✅ **共享内存数据结构**: 采用 `List[List[Any]]`（行优先）+ 列顺序列表
   - **决策理由**：
     - 支持直接写入：SQL构造简洁，一行代码完成
     - 支持Prepare stmt：List下标天然对应参数位置，无需列名映射
     - 支持Batch prepared：批量绑定性能最优，纯数组访问
     - 支持行拷贝：`row.clone()` 直接实现，代码优雅
   - **列顺序保证**：由DDL生成器控制，seed-data-generator按列序号顺序生成CSV
   - **实现方案**：创建新模块 `shared-memory-initializer` 专门负责共享内存初始化

2. **conn_config 动态参数生成**:
   - ✅ **已决策**: 不动态生成。本期仅暴露 `db_url` 和 `conn_pool_size`（`db_username`/`db_password` 沿用既有变量），其余 `conn_config` 条目不在 JMX 中动态生成；其他参数的暴露后续按需添加
   - 详见 jdbc-datasource design.md / review.md

**行动**：共享内存初始化逻辑已迁移至 `shared-memory-initializer` 模块

---

### 6. multi-end-coordination - device_start 注入机制
- ✅ **已解决（范围决策）**: 多端协同**发压**由调用测试计划的**流水线脚本**实现，**不在测试计划生成器职责范围内**。本模块的多端协同描述仅用于说明可能性和方法。
- 原阻塞项均归属外部编排/流水线，视为已关闭：
  1. ~~**device_start 输出位置**~~ → 由流水线脚本决定与捕获
  2. ~~**注入机制 / `${__P(device_start,1)}` 读取**~~ → 由流水线脚本注入；生成器仅保证模板可通过 JMeter 属性读取
  3. ~~**冲突验证责任**~~ → 由外部编排工具负责，生成器不做跨实例冲突校验
- **对生成器唯一要求**: JMX 模板支持通过 `${__P(device_start,1)}` 读取 `device_start`
- 已更新 multi-end-coordination/review.md（新增第 0 节范围决策）

---

### 7. throughput-control - ✅ Open Questions 全部解决
**模块**: `openspec/changes/throughput-control/`
**影响**: 任务边界与配置层设计已明确

**已决策项**：
1. ✅ **最小吞吐量**: 不设置除 `> 0` 外的最小限制。JMeter `ConstantThroughputTimer` 使用毫秒级延时，理论无硬性下限，可支持到 `0.001` 次/分钟级别的极小值；典型配置 120 次/分钟。
2. ✅ **吞吐量单位**: 统一使用 JMeter 原生 **次/分钟** 单位，不在生成器或配置层做单位换算；用户需在配置前自行换算为次/分钟。

**行动**: Open Questions 已全部解决，可生成 `tasks.md`

---

## 📋 次要优先级（可延后）

### 8. utils - 边界条件定义不足
**模块**: `openspec/changes/utils/`
**影响**: 测试覆盖不完整，但主路径可实现

**待补充**：
1. `val_range_parser.py`：
   - 空白处理规则（`strip()`）
   - 区间逆序（如 `[100,1]`）返回 `unknown` 还是解析不校验
   - 枚举值空字符串处理（如 `enum:A,,B`）
   - `ref:` 引用中库名/表名/列名特殊字符处理

2. `xml_helpers.py`：
   - `to_string()` 对空元素、嵌套空 `HashTree` 的序列化行为
   - `add_bool_prop()` 对非布尔值的转换策略
   - 特殊字符转义（`<`、`&`、中文）输出

**行动**：补边界条件到 spec，补充单元测试

---

### 9. query-functionality - 边界条件与任务粒度
**模块**: `openspec/changes/query-functionality/`
**影响**: 部分场景未覆盖，职责耦合

**待补充**：
1. 边界条件：
   - 双引号转义字符串中的 `?`
   - SQL 注释（`--`, `/* */`）中的占位符
   - 多字节字符与引号相邻
   - 单条种子数据的采样确定性
   - 种子文件为空或仅含 `"null"` 的处理

2. Open Questions：
   - 参数类型映射：是否需要更精确的 JDBC 类型映射
   - IN 子句支持：是否未来支持 `WHERE col IN (?,?,?)`
   - 查询结果处理：是否需要支持查询结果验证或断言
   - 线程组 `num_threads` 示例：是否需要在 JMX 示例中展示 `${q1_num_threads}`

3. 任务粒度：将 SQL 解析绑定与查询 artifacts 生成拆分为独立子模块

**行动**：优先补充边界测试用例，延后 Open Questions

---

### 10. main-entry - Open Questions
**模块**: `openspec/changes/main-entry/`
**影响**: 配置边界不清晰，目录结构未定义
**状态**: ⚠️ 已降级为次要优先级，不阻塞 `tasks.md` 生成

**待澄清**：
1. **文件名边界**: 是否需要在 `test_cfg.yaml` 中显式指定输出 `.jmx` 文件名
2. **mode 校验边界**: 在 `main.py` 中校验还是交给 JmxBuilder 处理
3. **种子目录层级**: 当不同数据库存在同名表时，是否增加数据库层级 `seeds/{db_name}/{table_name}/...`

**行动**：在细化 task 时收敛，非阻塞主路径

---

### 11. prepared-insert-template - 边界条件
**模块**: `openspec/changes/prepared-insert-template/`
**影响**: 部分场景未覆盖
**状态**: ⚠️ 已降级为次要优先级，不阻塞 `tasks.md` 生成

**待补充**：
1. 空列列表：返回空字典还是抛出异常
2. 表名/列名含特殊字符时是否需要加引号
3. KaiwuDB 标识符引号规则需确认
4. `write_config` 为空/缺失时的行为
5. 调用方空模板字典处理

**行动**：补边界条件到 spec，测试任务补充

---

### 12. jdbc-datasource - Open Questions
- ✅ **已解决**: 两个 Open Question 已决策
- **范围决策**: 本期仅暴露 `db_url` 和 `conn_pool_size` 两个动态参数（`db_username`/`db_password` 沿用既有变量），不动态生成任意 `conn_config` 参数；其他参数的暴露后续按需添加
- **连接池参数可配置性**: 维持 `connectionAge`/`timeout`/`trimInterval` 硬编码，列为 Non-Goal
- **驱动类支持**: 本期仅支持 KaiwuDB，`driver` 固定为 `com.kaiwudb.Driver`，列为 Non-Goal
- 已更新 design.md 和 review.md

---

### 13. multi-end-coordination - 测试覆盖
**模块**: `openspec/changes/multi-end-coordination/`
**影响**: 测试场景缺失

**待补充**：
1. 多实例设备号冲突验证测试
2. `device_per_thread` / `num_threads` 边界值测试
3. 设备号循环覆盖场景验证
4. 命令行参数 `-Jdevice_start=N` 端到端集成测试

**行动**：补充测试任务到 tasks.md

---

### 14. seed-data-generator - 测试覆盖
**模块**: `openspec/changes/seed-data-generator/`
**影响**: 测试场景缺失

**待补充**：
1. 边界值测试：`val_range` 区间边界
2. 异常输入测试：非法格式、非法 `null_rate`、`seed_num` 为 0 或负数
3. 并发测试：多表同时生成时的文件系统冲突
4. 大容量测试：`seed_num` 极大时的性能表现
5. 外键引用测试：被引用表 `seed_num` 小于引用表时的行为

**行动**：补充测试场景到 spec，定义测试策略

---

### 15. throughput-control - 边界条件
**模块**: `openspec/changes/throughput-control/`
**影响**: 负向场景未覆盖

**待补充**：
1. 吞吐量为 `0` 或负数时的行为
2. 缺失变量定义时的行为
3. 多端协同下 timer 生成一致性验证
4. JMX 输出结构校验测试

**行动**：补负向场景到 spec

---

### 16. write-strategies - 测试覆盖
**模块**: `openspec/changes/write-strategies/`
**影响**: 异常路径未覆盖

**待补充**：
1. 所有策略的异常输入测试（非法 mode、空配置、边界 batch size）
2. `BatchPreparedStatementStrategy.get_sampler_script()` 输出示例
3. 重构前后输出等价性验证标准
4. 策略注册表查找性能基准测试

**行动**：补异常测试，定义等价性验证标准

---

### 17. jdbc-datasource - 测试覆盖
**模块**: `openspec/changes/jdbc-datasource/`
**影响**: 负向用例缺失

**待补充**：
1. 元素定位的断言（"在 Arguments 之后、所有 thread group 之前"）
2. 生成 XML 的良构性与属性完整性断言
3. 依赖变量缺失的负向用例

**行动**：增加端到端断言和负向用例

---

## 📊 统计总结

### 按模块分类
| 模块 | 必须解决 | 高优先级 | 次要优先级 | 状态 |
|------|---------|---------|-----------|------|
| config-parser | ~~3项~~ | - | - | ✅ 已解决 |
| direct-insert-write | ~~2项~~ | - | - | ✅ 已解决 |
| ddl-generator | - | - | - | ✅ 已解决 |
| seed-data-generator | ~~3项~~ | - | 1项 | ✅ 已解决 |
| write-strategies | - | 1项 | 1项 | ⚠️ Warning |
| jmx-skeleton-generator | - | ~~2项~~ | - | ✅ 已解决 |
| shared-memory-initializer | - | - | - | ✅ 已完成 |
| multi-end-coordination | - | ~~3项~~ | 1项 | ✅ 已解决（范围决策） |
| throughput-control | - | ~~2项~~ | 1项 | ✅ 已解决 |
| utils | - | - | 1项 | ⚠️ Warning |
| query-functionality | - | - | 3项 | ⚠️ Warning |
| main-entry | - | - | 3项 | ⚠️ Warning |
| prepared-insert-template | - | - | 5项 | ⚠️ Warning |
| jdbc-datasource | - | ~~OQ~~ | 3项 | ⚠️ 仅余测试覆盖 |

### 总计
- 🔴 **必须解决**: **0 项**（已解决 10 项）
- ⚠️ **高优先级**: **3 项**（已解决 7 项）
- 📋 **次要优先级**: **18 项**
- ✅ **新模块**: 1 项（shared-memory-initializer）
- **总计**: **26 项待解决问题**

---

## 💡 建议行动顺序

### 第一阶段（解决硬阻塞）
1. ✅ config-parser OQ1（primary_tags nullable 建模）- **已完成**
2. ✅ direct-insert-write OQ2（线程索引获取方式）- **已完成**
3. ✅ ddl-generator OQ2（SQL标识符和关键字大小写策略）- **已完成**
4. ✅ ddl-generator OQ3（错误处理策略）- **已完成（该问题不成立）**
5. ✅ ddl-generator OQ4（partition_interval 语法位置）- **已完成**
6. ✅ seed-data-generator（核心实现细节）- **已完成**
7. ✅ config-parser（职责重叠）- **已完成**

### 第二阶段（明确任务边界）
8. 🔄 write-strategies（Migration Plan 重构）
9. ✅ jmx-skeleton-generator（共享内存数据结构）- **已解决（创建 shared-memory-initializer 模块）**
10. 🔄 shared-memory-initializer（补充实现细节和性能约束）
11. ✅ multi-end-coordination（device_start 注入机制）- **已解决（范围决策：发压归流水线脚本）**
12. 🔄 throughput-control（Open Questions）

### 第三阶段（生成 tasks.md）
12. 为所有模块生成 tasks.md（当前状态：多数模块 tasks.md 未创建或已删除）

### 第四阶段（补充边界条件和测试）
13. 补充所有模块的边界条件定义
14. 补充所有模块的测试用例

---

## 🔗 相关文档链接

- [config-parser review](./config-parser/review.md)
- [ddl-generator review](./ddl-generator/review.md)
- [direct-insert-write review](./direct-insert-write/review.md)
- [seed-data-generator review](./seed-data-generator/review.md)
- [write-strategies review](./write-strategies/review.md)
- [jmx-skeleton-generator review](./jmx-skeleton-generator/review.md)
- [shared-memory-initializer review](./shared-memory-initializer/review.md) ⭐ **新模块**
- [multi-end-coordination review](./multi-end-coordination/review.md)
- [throughput-control review](./throughput-control/review.md)
- [utils review](./utils/review.md)
- [query-functionality review](./query-functionality/review.md)
- [main-entry review](./main-entry/review.md)
- [prepared-insert-template review](./prepared-insert-template/review.md)
- [jdbc-datasource review](./jdbc-datasource/review.md)
- [column-namer review](./column-namer/review.md)

---

**最后更新人**: Claude
**更新时间**: 2026-06-26