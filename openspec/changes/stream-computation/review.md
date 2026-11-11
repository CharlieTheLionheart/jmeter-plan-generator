# stream-computation — Review

> 五维审查:边界条件 / 回滚方案 / 测试覆盖 / 向后兼容 / 任务粒度。

## 1. 边界条件

| # | 边界 | 覆盖情况 | 处置 |
|---|---|---|---|
| 1.1 | `stream_config` 段缺字段 | ✅ spec 场景「Validation when present」 | `StreamConfig` 全部必填字段非空校验 |
| 1.2 | `expected_min_rows = 0` | ✅ | 允许(0 = 恒真下界),与 pub-sub 的 `expected_min_rows` 语义一致 |
| 1.3 | `options` 为空 / 缺省 | ✅ spec 场景「Options clause omitted when empty」 | 不发 `WITH OPTIONS` 子句 |
| 1.4 | `group_by` 为空 | ✅ design Q3 | `GROUP BY <window>`(实测建流通过) |
| 1.5 | 源表 = 目标表 | ✅ spec 场景「Source and target must differ」 | 生成期拒绝(F14 服务端同样拒) |
| 1.6 | 源表无写入 | ✅ spec 场景「Source table must be written」 | 生成期拒绝 —— 静默失效比报错危险(write-missing-data 教训) |
| 1.7 | 目标表已存在(重跑) | ✅ spec 场景「Repeated runs are idempotent」 | `DROP STREAM IF EXISTS` + `DELETE FROM <target>` |
| 1.8 | 流已存在(重跑) | ✅ 同上 | `DROP STREAM IF EXISTS`(F3/F4) |
| 1.9 | 目标表列为 0 | ⚠️ **未覆盖** | `TsTableConfig` 要求 `primary_tag_count + regular_tag_count == len(...)` 且 `data_col_count >= 0`;`data_col_count=0` + 无 tag 的表 → 目标表只有 1 列(ts) → `select_list` 只能有 1 项 → 与"必须含窗口边界函数(2 项)"矛盾 → 生成期会被 D5 的列数校验拦下。**结论:天然被拦,无需额外校验** |
| 1.10 | 窗口为滑动形态(3 参 `TIME_WINDOW`) | ✅ design D5 | 校验规则按参数个数分派:`first/last` vs `first_row/last_row` |
| 1.11 | `select_list` 含带逗号的函数调用 | ⚠️ **实现细节** | 必须用括号感知切分器,不能用 `split(',')`(design D5 末段已标注) |
| 1.12 | 目标表有 `regular_tags`(非主标签) | ✅ spec「total column count」表述含 regular tags | 列数计算须含 regular_tags |
| 1.13 | schemaless + stream_config | ✅ spec Requirement「not supported on the schemaless write path」 | 生成期报错,不静默忽略(D7) |
| 1.14 | 流启动失败(引擎起不来) | ✅ spec 场景「Stream status is asserted」 | `status` + `error_message` 双断言(区别于"没产出数据") |
| 1.15 | 尾部窗口永不闭合 | ✅ design F20 / R3 | `expected_min_rows` 明确为下限语义 |
| 1.16 | 目标表 `ts_col.type` 写成 `timestamp` | ✅ design R5 / D3 | 交服务端类型校验(F11/F12),错误信息带列名与两侧类型;配置注释与 reference 显式提示用 `timestamptz` |
| 1.17 | 服务端 `SHOW STREAM` 返回列数变化 | ✅ design D8 / F22 | **不用** `variableNames`(列数不匹配会静默错绑 —— 实测 3 个名字对 10 列时 `status` 拿到第 2 列的值);改用 `resultVariable` + `Store as Object` + 按列标签取值(F23),免疫列序/列数变化 |
| 1.18 | 流不存在(`SHOW STREAM` 返回 0 行) | ✅ design D8 / F26 | 按列标签方案可显式判 `rows.isEmpty()` → 报"流不存在"而非含糊的 null |
| 1.19 | 目标表总列数算错 → 列数校验误报/漏报 | ✅ design D6 / R2 | 复用 `DDLGenerator._allocate_group`,与 `CREATE TABLE` 构造上同源;不另写一份分配逻辑 |

**结论**:边界已覆盖。1.9 / 1.11 是实现期必须注意的两点,已分别由现有校验天然拦截、需用括号感知切分器。1.17 是本轮实测新发现的**静默失败**陷阱,已通过改用按列标签取值规避。

## 2. 回滚方案

| 层面 | 回滚方式 | 可逆性 |
|---|---|---|
| 配置层 | 删掉 `test_cfg.yaml` 的 `stream_config` 段 | 完全可逆 —— 生成器零生效,输出回到基线(逐字节一致,smoke 用「与基线比对」核验) |
| 代码层 | revert 本 change 的 commit | 完全可逆 —— 无数据迁移、无 schema 变更、无外部依赖 |
| 数据层 | 目标表 / 流残留在库里 | 流水线侧负责(与 pub-sub 同口径:生成器不生成 tearDown 清理)。**残留影响**:下一次跑同配置时,`DROP STREAM IF EXISTS` + `DELETE FROM <target>` 会清干净 → 残留不构成回滚障碍 |
| 环境层 | 容器需 `--advertise-addr=127.0.0.1:26257`(F21) | 与本 change 正交;但缺它会让流起不来 —— smoke 文档必须写明 |

**风险**:无不可逆操作。`DELETE FROM <target>` 只清目标表,不动源表 —— 源表是压测负载对象,不能被建流链清空(已在 spec 中把 DELETE 严格限定在目标表)。

**结论**:回滚方案完整,无不可逆步骤。

## 3. 测试覆盖

### 单测(纯 Python,无需容器)

| 层 | 用例 | 断言要点 |
|---|---|---|
| `config_parser` | `StreamConfig` 字段白名单 / 必填非空 / `expected_min_rows >= 0` / `verify_delay_seconds >= 0` / `options` 值类型 | 缺字段 → `ValidationError`;`extra="forbid"` 拒未知字段 |
| `config_parser` | `validate_stream_refs` 各条校验 | 源/目标不存在、源=目标、源不在 write_config、窗口边界函数错、输出列数不匹配 —— 5 类各一例 + 1 例正常通过 |
| `config_parser` | `validate_stream_refs` 列数计算 | 目标表带 regular_tags / 多 data_col 时列数计算正确(与 `DDLGenerator` 同源) |
| `stream_comp/stream_sql` | `build_create_stream_sql` 各形态 | 无 options / 有 options / 有 group_by / 无 group_by / 多 option 顺序 |
| `stream_comp/stream_sql` | `split_select_items` | 括号感知:`count(*)` / `date_trunc('day', ts)` / 嵌套括号 |
| `stream_comp/stream_setup_tg` | 追加链结构 | 3 个 sampler + 各自 paired hashTree;SQL 文本正确;挂在 SetupTG hashTree 内 |
| `stream_comp/stream_verify_tg` | Verify TG 结构 | PostThreadGroup 属性(delay / loops / duration)、2 个 sampler、断言脚本内容 |
| `stream_comp/stream_verify_tg` | `SHOW STREAM` 取值机制 | `resultSetHandler="Store as Object"` + `resultVariable="stream_rows"`(**不是** `variableNames`);断言脚本按列标签 `row.get('status')` 取值 |
| `ddl_generator` | `ts_table_column_count` | 与 `CREATE TABLE` 展开的列数一致(含 primary_tags / regular_tags);多 data_col 组合下正确 |
| `jmx_skeleton_generator` | 段缺省时零回归 | 生成的 JMX **不含** `CREATE STREAM` / `SHOW STREAM`;与基线逐字节一致 |
| `jmx_skeleton_generator` | 段存在时接线 | SetupTG 内含建流链;Verify TG 在写入 TG 之后 |
| `kwjdbc_svt` 集成 | 端到端生成 | 用 fixture 跑 `main` → `ElementTree.parse()` 校验 XML 合法 + 断言关键 SQL 存在 |
| `seed_data_generator` | 目标表被排除 | 目标表无种子 CSV;非目标表不受影响 |

### smoke(真实 KaiwuDB 容器,`kwjdbc-jmx-smoke` skill)

| # | 场景 | 断言 |
|---|---|---|
| S1 | 建流 + 写入 + 落库 + 断言全绿 | `Err: 0`;目标表行数 > 0;`SHOW STREAM` 的 `status` = `Enable`、`error_message` 空;Verify TG 两个断言均通过 |
| S2 | 段缺省回归 | 生成的 JMX 不含建流语句;既有 fixture 输出与基线逐字节一致 |
| S3 | 目标表清空生效 | 连跑两次,第二次目标表行数与第一次同量级(不被上一轮残留抬 high) |
| S4 | **insecure 容器**(与仓库全部 fixture 一致) | 流 `status` = `Enable`(F25);确认 F21 是 TLS 特有,不阻塞本期 |

### 覆盖缺口(已知,记录在案)

| 缺口 | 原因 | 处置 |
|---|---|---|
| 类型不匹配的负向 smoke | 服务端报错清晰(F11),生成期不做类型推导(NG7) | 靠单测覆盖生成侧;类型负向由服务端保证 |
| 滑动窗口 `TIME_WINDOW(ts,'1m','30s')` 的端到端 | 本期场景配置用非滑动窗口 | 单测覆盖 SQL 形态;建流已在 F8 实测通过 |
| `LOW_LATENCY=ON` / `PROCESS_HISTORY=ON` 的行为差异 | 属参数调优(NG4) | 选项透传由单测覆盖 |
| 并发多线程下的窗口闭合 | 本期 smoke 用单线程(与 write-missing-data 阶段 2 的"direct 路径首批 ts 相撞"教训一致) | 后续如需并发,单独评估 |
| TLS 模式下的流计算 | 本期 smoke 走 insecure 容器(F25:明文模式下流正常);TLS 模式需 `--advertise-addr=127.0.0.1:26257`(F21) | 问题已定位;流水线切 TLS 时按 F21 补参数,并写进 smoke skill |

**结论**:单测 + smoke 覆盖了主链路与全部 5 条生成期校验。已记录的 4 个覆盖缺口均有明确原因与处置,不阻塞本期。

## 4. 向后兼容

| 变更点 | 影响面 | 兼容性 |
|---|---|---|
| `TestConfig` 新增 `stream_config` 字段 | `TestConfig` 是 `extra="forbid"` —— **既有 YAML 里出现 `stream_config` 之前会报错,之后被接受** | ✅ 向后兼容(既有 YAML 不含该键) |
| `TestConfig` 新增字段导致 model_dump 变化 | 仅内部使用 | ✅ |
| `main.py` 排除目标表种子 | **仅当声明了 `stream_config` 时生效** | ✅ 既有路径逐字节不变 |
| `skeleton.py` 新增 SetupTG / Verify TG 分支 | **仅当声明了 `stream_config` 时生效** | ✅ |
| `config_parser/models.py` 新增 `StreamConfig` / `validate_stream_refs` | 纯新增 | ✅ |
| 新增 `src/stream_comp/` 子包 | 纯新增 | ✅ |
| `TestConfig` 的 Pydantic 字段顺序 | `model_dump()` 的键序会变 —— 但仓库内 `model_dump` 只用于 `rest_api_config`(与本字段无关) | ✅ |
| `openspec/specs/` 主 spec | 本 change 归档时新增 `stream-computation` 能力 spec;既有 spec 不动 | ✅ |

**零回归核验方式**(与 write-missing-data 阶段 2 同法):
1. 不声明 `stream_config` 时,生成的 `.jmx` 与基线 commit **逐字节比对**;
2. 既有 fixture(`test_cfg.yaml` / `test_cfg_shig.yaml` / `test_cfg_schemaless_tls.yaml` 等)全部产出不变;
3. `pytest tests/` 全绿,基线用例数不减。

**结论**:完全向后兼容,零回归可用逐字节比对核验。

## 5. 任务粒度

| # | 任务组 | 预估粒度 | 是否可独立验证 |
|---|---|---|---|
| 1 | 配置模型 + 校验(`StreamConfig` / `validate_stream_refs`) | 1 组,约 1 个会话 | ✅ 纯 Python + 单测 |
| 2 | SQL 生成(`stream_sql.py`) | 1 组,约半会话 | ✅ 纯函数 + 单测 |
| 3 | TG 装配(`stream_setup_tg.py` / `stream_verify_tg.py`) | 2 组,各约半会话 | ✅ XML 结构断言 |
| 4 | 接线(`main.py` / `skeleton.py` / `config_parser/__init__.py`) | 1 组,约半会话 | ✅ 集成用例 |
| 5 | fixture + 集成测试 + 零回归比对 | 1 组,约半会话 | ✅ `pytest` |
| 6 | smoke(容器重建 + 建流 + 落库 + 断言) | 1 组,需容器 | ✅ 真实集群 |

**粒度检查**:
- 每个任务都 ≤ 1 个会话,无"实现整个特性"这种巨型任务;
- 任务按依赖排序(1 → 2 → 3 → 4 → 5 → 6),前一组不绿后一组无法验证;
- 每个任务都写明"验证方式"(单测名 / pytest 命令 / smoke 断言),符合 AGENTS.md §4「Goal-Driven Execution」;
- 任务 6 明确标注"需容器",与纯 Python 任务分离 —— 避免把环境依赖混进单测阶段。

**结论**:粒度合适,依赖序清晰,每项可独立验证。

---

## 审查结论

五个维度均通过,无阻塞项。落地前需在实现期特别注意三点(已在上面标注):

1. `select_list` 切分必须**括号感知**(1.11);
2. 目标表列数计算必须与 `DDLGenerator` **同源**(D6 / R2)—— 不另写一份 `allocate_columns` 组合;
3. `SHOW STREAM` 的结果取值**不得**用 `variableNames` —— 列数不匹配会静默错绑到别的列(F22),必须用 `resultVariable` + `Store as Object` + 按列标签取值(F23 / D8)。

smoke 走 **insecure 容器**(F25,与仓库全部 fixture 一致);TLS 容器的 `--advertise-addr` 问题(F21)已定位,流水线切 TLS 时按 R8 处置。
