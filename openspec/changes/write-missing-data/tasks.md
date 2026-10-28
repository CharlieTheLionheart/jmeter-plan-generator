# Tasks: write-missing-data

## 0. 范围决策确认(review 阶段已闭环)

- [x] 0.1 缺失判定用交集;设备维度与时间戳维度**分别判定**,两者同时命中才跳过该格;某一维度 count=0 时该维度视为全集(不构成约束)
- [x] 0.2 截断方式为**从后向前截断**(设备序列 `1、2、3、4、5` 截断 2 个 → 保留 `1、2、3`),不用随机抽样
- [x] 0.3 触发条件用概率,每写入批次判定一次;`probability = 1.0` 必然缺失 / `0.0` 关闭
- [x] 0.4 各写入线程的缺失判定**相互独立**,暂不支持"所有线程在同一批次同时缺失"
- [x] 0.5 计数上界取 `<=`(等于总数即"缺整轮",合法形态),超过总数在配置期拒绝
- [x] 0.6 配置形态用**表级嵌套 `missing` 段**(段名 `missing`),段内 `probability` 必填;两个 count 都是 0 → 接受;`probability: 0.0` → 显式关闭
- [x] 0.7 缺省概率 `0.0`(缺省不做缺失,缺陷模拟是 opt-in);`probability = 0.0` 时**不注入**缺失逻辑
- [x] 0.8 覆盖 `direct` + `prepare` + `schemaless` 三条路径,bind / 非 bind 分支均含(6 处装配点)
- [x] 0.9 缺失维度绑定表结构:设备维度 = 第一个 primary tag 列,时间戳维度 = `ts_col`;尾部按**本轮网格相对下标**定义
- [x] 0.10 缺失后**不做吞吐补偿**(只减行数,不改变 sampler 触发次数)
- [x] 0.11 随机源用 `ThreadLocalRandom`(8 线程 0.7 ns/call,无锁无争用),不用除法取余伪随机
- [x] 0.12 **既有代码修正**(随机源替换 7 处 + 空种子池失败模式修正 + 配置校验硬化)合并在 **commit 1**,**先于**缺失功能 commit 落地
- [x] 0.13 空种子池必须**尽早抛业务异常**:上游 loader 不再吞错误置空,下游 6 个消费点不再静默降级
- [x] 0.14 `write_config[]` **同表不可配置多条**(`tbl_name.lower()` 比较)+ **schemaless 路径大小写归一**(`to_lower`)
- [x] 0.15 D7 运行时设备数漂移防御采用"退化为只按 ts 维度截断"(而非 clamp 阈值 + 告警)

---

## TDD 范式约定

每个子 task 按"pytest 先行 → 编码后继 → 单元测试全绿 → 继续下一模块"节奏推进:

- **pytest 子 task**:先写含**失败断言**的测试文件,子 task 验收时该文件全绿
- **编码子 task**:实现让上述 pytest 全绿才能勾选
- **模块切换**:当前模块 pytest 全绿才推进下一模块
- **commit 闸门**:子 task 全部验收通过后**停下来等 user review**,收到明确信号再 commit / push(per 全局规则 `feedback-review-before-commit-not-after`)。commit 顺序固定:§1-§3 → commit 1,§4-§7 → commit 2

### 验收命令

```bash
source .venv/bin/activate
python -m pytest tests/config_parser/test_missing_config.py          # §2.1
python -m pytest tests/utils/test_preprocessor_helpers.py             # §2.2
python -m pytest tests/jmx_skeleton_generator/test_missing_injection.py  # §2.3
python -m pytest tests/jmx_skeleton_generator/test_random_source.py    # §1.1
python -m pytest tests/shared_memory_initializer/test_shared_memory_initializer.py  # §1.2
python -m pytest tests/config_parser/test_write_config.py              # §1.3
python -m pytest tests/                                                  # 全量
```

### 集成测试分两 phase

- **Phase A:.jmx 生成层集成测试** —— `python -m kwjdbc_svt.main` 生成 .jmx + `ElementTree.parse()` 校验结构,**不需要真实 KaiwuDB cluster**
- **Phase B:容器冒烟** —— 真实 KaiwuDB docker container + `jmeter -n` 端到端,**需要 cluster**,走 `kwjdbc-jmx-smoke` skill(**不在 pytest 里**)

---

## 1. commit 1 前置:随机源替换(7 处,design D4(b))

- [x] 1.1 pytest 先写 `tests/jmx_skeleton_generator/test_random_source.py` 含失败断言:覆盖 7 处脚本生成路径,断言产物**不含** `new Random()` / `Math.random()`,**含** `ThreadLocalRandom.current()`:
  - `write_groups.py::_build_inline_sql_preprocessor_script` 非 bind 分支(内层循环 `new Random().nextInt(total)`)与 bind 分支(`new Random().nextInt(rowValues.size())`)
  - `write_groups.py::_build_batch_prepared_preprocessor_body` 非 bind 分支(`(int)(Math.random() * totalRows)`)与 `_build_batch_prepared_bind_preprocessor_body`(`def randomGen = new Random()`)
  - `rest_write_groups.py::_build_rest_write_preprocessor_script` 非 bind 与 bind 分支(各 `def randomGen = new Random()`)
  - `query_groups.py` 的 seed 取行脚本(`(int)(Math.random() * lines.size())`)
- [x] 1.2 实现 7 处替换:`new Random().nextInt(n)` → `java.util.concurrent.ThreadLocalRandom.current().nextInt(n)`;`def randomGen = new Random()` → `def randomGen = java.util.concurrent.ThreadLocalRandom.current()`(后续 `randomGen.nextInt(...)` 调用点不动);`(int)(Math.random() * n)` → `nextInt(n)`
- [x] 1.3 **验收**:跑 `pytest tests/jmx_skeleton_generator/test_random_source.py` 全绿 + 全量 pytest 无 regression

## 2. commit 1 前置:空种子池失败模式修正(design D11)

- [x] 2.1 pytest 先写 `tests/shared_memory_initializer/test_shared_memory_initializer.py` 新增用例含失败断言:loader Groovy 脚本在"CSV 文件不存在"分支与 `catch` 分支**均** `throw new RuntimeException`,**不含** `props.put(rowsKey, [])` 兜底
- [x] 2.2 pytest 先写 `tests/jmx_skeleton_generator/test_empty_pool_raises.py` 含失败断言:6 个消费点脚本在共享内存池为空时抛 `RuntimeException`,**不含** `log.warn(... empty ...)` + 早退:
  - `write_groups.py::_build_inline_sql_preprocessor_script` 非 bind(`allRows` 空)与 bind(`bindGroups` 空)
  - `write_groups.py::_build_batch_prepared_preprocessor_body` 非 bind(**新增**检查,现状无保护)与 `_build_batch_prepared_bind_preprocessor_body`(`bindGroups` 空)
  - `rest_write_groups.py::_build_rest_write_preprocessor_script` 非 bind(`rows` 空)与 bind(`bindGroups` 空)
- [x] 2.3 实现 loader 侧抛异常(`shared_memory_initializer.py::generate_groovy_loader_script` 的 2 处:文件不存在分支 + `catch` 分支)
- [x] 2.4 实现 6 个消费点抛业务异常,消息带表名 + 共享内存 key + "seed CSV load failed" 提示;判空 MUST 同时覆盖 `null` 与空数组(loader 抛异常后不再 `props.put(rowsKey, [])`,消费侧可能拿到 `null`)
- [x] 2.5 **验收**:跑 `pytest tests/shared_memory_initializer/test_shared_memory_initializer.py tests/jmx_skeleton_generator/test_empty_pool_raises.py` 全绿

## 3. commit 1 前置:配置校验硬化(design D12)

- [x] 3.1 pytest 先写 `tests/config_parser/test_write_config.py` 新增用例含失败断言:`write_config[]` 内同表两条(大小写不同也算重复,如 `iot_monitor.t_cnc` 与 `IOT_MONITOR.T_CNC`)→ `ValueError`,消息含 `tbl_name`
- [x] 3.2 pytest 先写 `tests/jmx_skeleton_generator/test_rest_write_bind.py` 新增用例含失败断言:schemaless 路径在 cfg 用**大写** `tbl_name` 时仍能匹配到 model 的小写表名(现状抛 `missing write_config for ts_table`)
- [x] 3.3 实现 `src/config_parser/models.py::TestConfig` 的 `@model_validator(mode="after")`:`write_config` 内 `tbl_name.lower()` 必须唯一
- [x] 3.4 实现 `rest_write_groups.py::generate_rest_write_thread_group` 的大小写归一:建索引 `write_cfg_by_table[wc.tbl_name.lower()] = wc`,查询键 `f"{ts_db.name}.{ts_table.name}".lower()`
- [x] 3.5 **验收**:跑 `pytest tests/config_parser/test_write_config.py tests/jmx_skeleton_generator/test_rest_write_bind.py` 全绿
- [x] 3.6 **commit 1**:§1-§3 全部验收通过 → 停下等 user review → 收到信号后 `git add` + `git commit`(message:`perf(write): 随机源换 ThreadLocalRandom + 空种子池抛业务异常 + write_config 同表唯一校验`)+ `git push origin feat/pub-sub`

## 4. commit 2:配置模型(`MissingConfig` + `WriteConfig.missing`)

- [ ] 4.1 pytest 先写 `tests/config_parser/test_missing_config.py` 含失败断言:
  - `MissingConfig` 3 字段:`probability`(必填,`[0.0, 1.0]`)/ `ts_count`(缺省 `0`,`>= 0`)/ `device_count`(缺省 `0`,`>= 0`);`extra="forbid"`(段内出现其它字段 → `ValueError`)
  - `missing` 段存在但漏写 `probability` → `ValueError`,消息含 `probability`
  - `WriteConfig.missing` 缺省为 `None`
  - 跨字段校验:`ts_count <= batch_lines`、`device_count <= device_per_thread`(取等合法 = 缺整轮);**超过**总数 → `ValueError`
  - 段存在但两个 count 都是 `0` → 校验通过
- [ ] 4.2 实现 `src/config_parser/models.py::MissingConfig`(Pydantic,`probability: float = Field(..., ge=0.0, le=1.0)`)+ `WriteConfig.missing: Optional[MissingConfig] = None`
- [ ] 4.3 实现 `WriteConfig` 的 `@model_validator(mode="after")` 跨字段校验(与 `check_col_tag_bind_mode_positive` 同级)
- [ ] 4.4 **验收**:跑 `pytest tests/config_parser/test_missing_config.py` 全绿

## 5. commit 2:判定 helper(Python + Groovy 同构,design D10)

- [ ] 5.1 pytest 先写 `tests/utils/test_preprocessor_helpers.py` 新增用例含失败断言 `should_skip_row(device_idx, ts_idx, *, device_count, ts_count, device_per_thread, batch_lines) -> bool`:
  - 只配 `ts_count=2`(device_count=0)→ 尾部 2 个 ts 的**所有设备**行命中
  - 只配 `device_count=1`(ts_count=0)→ 尾部 1 个设备的**所有 ts** 行命中
  - 两个都配 → 交集(设备尾部 ∩ ts 尾部)
  - count=0 的维度恒"命中"(视为全集,不构成约束)
  - `ts_count == batch_lines` → 全部命中(缺整轮)
- [ ] 5.2 实现 `src/utils/preprocessor_helpers.py::should_skip_row`(纯函数,**无 rng 参数** —— 截断语义下判定式是纯比较)
- [ ] 5.3 实现 `src/utils/preprocessor_helpers.py::groovy_missing_data_decl(...)`:返回 D8 的 Groovy 块(概率常量分支 + `deviceHit` / `tsHit` 两行独立判定 + 交集)
- [ ] 5.4 **验收**:跑 `pytest tests/utils/test_preprocessor_helpers.py` 全绿

## 6. commit 2:Groovy 注入(6 处装配点,design D8)

- [ ] 6.1 pytest 先写 `tests/jmx_skeleton_generator/test_missing_injection.py` 含失败断言:6 处装配点生成的脚本**含**缺失逻辑块(`missingProbability` / `missingTsCount` / `missingDeviceCount` / `skipMissingRow` / `deviceHit` / `tsHit`),且内层循环含 `if (applyMissing && skipMissingRow(...)) { continue }`;设备下标为**本轮相对下标**(`d - deviceStart`,非绝对设备号)
- [ ] 6.2 pytest 先写同文件"零回归"用例含失败断言:**未声明 `missing` 段**或 **`probability = 0.0`** 时,生成的脚本与改动前基线**逐字节一致**(不含任何缺失标识符)
- [ ] 6.3 实现 `_build_inline_sql_preprocessor_script` 的非 bind + bind 分支注入(设备循环起点变量分别为 `localDeviceStart` / `deviceStart`)
- [ ] 6.4 实现 `_build_batch_prepared_preprocessor_body` 非 bind + `_build_batch_prepared_bind_preprocessor_body` bind 分支注入
- [ ] 6.5 实现 `rest_write_groups.py::_build_rest_write_preprocessor_script` 非 bind + bind 分支注入
- [ ] 6.6 实现注入开关(design D6):仅当 `wc.missing is not None` **且** `wc.missing.probability > 0.0` 时插入缺失块
- [ ] 6.7 **验收**:跑 `pytest tests/jmx_skeleton_generator/test_missing_injection.py` 全绿

## 7. commit 2:集成与 fixture

- [ ] 7.1 pytest 先写 `tests/kwjdbc_svt/test_main.py` 新增集成用例:`python -m kwjdbc_svt.main` 生成 .jmx → `ElementTree.parse()` 校验 —— 声明 `missing` 段的表其 Write TG 脚本含缺失块;未声明的表不含
- [ ] 7.2 新增 fixture(8 个,覆盖 6 条装配点 + 概率 + 缺整轮),统一 `missing: {probability: 1.0, ts_count: 2, device_count: 1}`(概率 / 缺整轮两个 fixture 除外):
  - `test_cfg_missing_direct.yaml`(mode: direct,非 bind)
  - `test_cfg_missing_direct_bind.yaml`(mode: direct + `col_tag_bind_mode: true`)
  - `test_cfg_missing_prepare.yaml`(mode: prepare,非 bind)
  - `test_cfg_missing_prepare_bind.yaml`(mode: prepare + `col_tag_bind_mode: true`)
  - `test_cfg_missing_schemaless.yaml`(mode: schemaless,非 bind)
  - `test_cfg_missing_schemaless_bind.yaml`(mode: schemaless + `col_tag_bind_mode: true`)
  - `test_cfg_missing_prob.yaml`(mode: prepare,`probability: 0.5` —— 概率生效验证)
  - `test_cfg_missing_full_round.yaml`(mode: prepare,`ts_count == batch_lines` —— 缺整轮验证)
  - model 复用 `test_model.yaml`;schemaless 两个用 `test_model_schemaless.yaml` + TLS 证书
- [ ] 7.3 **验收**:跑 `pytest tests/kwjdbc_svt/test_main.py` 全绿 + **全量 pytest 无 regression**
- [ ] 7.4 **commit 2**:§4-§7 全部验收通过 → 停下等 user review → 收到信号后 `git add` + `git commit`(message:`feat(write): 表级 missing 段 — 尾部截断 + 交集的按批次随机缺失`)+ `git push origin feat/pub-sub`

## 8. 文档同步

- [ ] 8.1 更新主 spec `docs/specs/kwdb-svt-test-plan-generator-spec.md` §2.0 写入配置字段表:新增 `missing` 段(`probability` 必填 / `ts_count` / `device_count` 缺省 `0`)、表级归属、尾部截断+交集语义、每批次概率触发、缺省不做缺失
- [ ] 8.2 更新 `docs/refs/` 下相关 reference(若涉及写入语义描述)

## 9. smoke(Phase B,需真实 KaiwuDB 容器;**不在 pytest 里**)

> 缺失功能覆盖 6 处 Groovy 装配点(`direct` / `prepare` / `schemaless` × bind / 非 bind),smoke MUST **逐路径全覆盖**,不能只跑一条就宣称通过。
>
> **核心技巧**:用 `probability = 1.0` 做**确定性 smoke** —— 尾部截断的位置是固定的,只有"是否触发"带概率;p=1.0 后缺失形态完全确定,断言从"统计区间"升级为**精确等值**。概率语义单独用 §9.3 的统计口径验证。

### 9.1 断言口径(6 条路径通用)

设 `dpt = device_per_thread`、`B = batch_lines`、`M = missing.device_count`、`N = missing.ts_count`。缺失设备 = 本轮设备网格尾部 M 个,缺失 ts = 本轮时间网格尾部 N 个。

**前提**:批次时间窗不重叠(吞吐 1/min + `batch_lines=5` + `ms_step=1000` → 窗口 5s、间隔 60s),否则各批次的 ts 会交叠,尾部语义被抹平。

| # | 观测 | 期望 |
|---|---|---|
| ① | 每设备的 ts 覆盖数 `count(distinct ts) group by <设备列>` | 取值集合恰为 `{B, B−N}` 两个值(尾部 M 个设备为 `B−N`,其余为 `B`) |
| ② | 每 ts 的设备覆盖数 `count(distinct <设备列>) group by ts` | 取值集合恰为 `{dpt, dpt−M}` 两个值 |
| ③ | 非缺失设备的 ts 覆盖数 | **等于** `B`(满值,证明不是"全都缺了") |
| ④ | 非缺失 ts 的设备覆盖数 | **等于** `dpt` |
| ⑤ | 单批次窗口内落库行数 | **等于** `(dpt − M) × (B − N)` |

查询形态(以 `iot_monitor.t_cnc` 为例,`ts` = 时间戳列,`ptag_varchar_1` = 设备列):

```sql
-- ① 每设备的 ts 覆盖数分布(期望恰好 2 行:B 与 B−N)
select ts_cov, count(*) from (
  select ptag_varchar_1, count(distinct ts) as ts_cov
  from iot_monitor.t_cnc group by ptag_varchar_1
) t group by ts_cov;

-- ② 每 ts 的设备覆盖数分布(期望恰好 2 行:dpt 与 dpt−M)
select dev_cov, count(*) from (
  select ts, count(distinct ptag_varchar_1) as dev_cov
  from iot_monitor.t_cnc group by ts
) t group by dev_cov;

-- ⑤ 单批次窗口行数
select count(*) from iot_monitor.t_cnc
where ts >= '<窗口起>' and ts < '<窗口止>';
```

### 9.2 六路径全覆盖(逐 fixture 跑,断言 9.1 全部 5 项)

- [ ] 9.2.1 `test_cfg_missing_direct.yaml`(direct 非 bind):SetupTG 无 error + Write TG JTL 无 sampler error + 9.1 的 ①~⑤ 全成立
- [ ] 9.2.2 `test_cfg_missing_direct_bind.yaml`(direct bind):同上
- [ ] 9.2.3 `test_cfg_missing_prepare.yaml`(prepare 非 bind):同上
- [ ] 9.2.4 `test_cfg_missing_prepare_bind.yaml`(prepare bind):同上
- [ ] 9.2.5 `test_cfg_missing_schemaless.yaml`(schemaless 非 bind):同上(REST 写入路径,查询口径不变)
- [ ] 9.2.6 `test_cfg_missing_schemaless_bind.yaml`(schemaless bind):同上

每条路径额外确认:**缺失维度确实落在该路径的装配点上**(生成的 JMX 里该路径的 PreProcessor 脚本含缺失逻辑块,而不是碰巧由别的路径产生)。

### 9.3 概率触发(`probability = 0.5`,统计口径)

- [ ] 9.3.1 `test_cfg_missing_prob.yaml`:总落库行数落在 `[满量 × 0.5, 满量]` 区间(概率统计口径,**不用精确等值**)
- [ ] 9.3.2 存在 ts 覆盖数 < `B` 的设备(证明概率真的触发了缺失,而不是全触发或全不触发)
- [ ] 9.3.3 存在 ts 覆盖数 = `B` 的设备(证明不是每批都缺)

### 9.4 缺整轮(`ts_count == batch_lines`)

- [ ] 9.4.1 `test_cfg_missing_full_round.yaml`:无 sampler error、无空写入报错(验证 D7 的三条路径兜底)
- [ ] 9.4.2 对应批次窗口内 `count(*) = 0`(而不是查询报错)
- [ ] 9.4.3 总落库行数**显著低于**同参数未配缺失时的行数

### 9.5 空种子池失败路径(验证 commit 1 的健壮性修正)

- [ ] 9.5.1 故意让 seed CSV 缺失 / 损坏 → 断言 **SetupTG 报 error**(loader 抛异常中断,不是静默置空)
- [ ] 9.5.2 断言 Write TG 也报 error(消费点二次抛业务异常),而非静默跳过
- [ ] 9.5.3 断言测试**不是**"全绿"—— 这正是 commit 1 修正前会漏掉的失败模式

### 9.6 收尾

- [ ] 9.6.1 smoke 全部通过后在 `docs/implementation-log.md` 追加本阶段条目(6 条路径全覆盖 / 概率 / 缺整轮 / 空池失败路径的 smoke 证据),并同步"已落地阶段一览"与"待办(跨会话)"两节
- [ ] 9.6.2 勾选本文件 §9 全部子 task + §1~§8 全部子 task
- [ ] 9.6.3 `openspec archive write-missing-data`(spec 增量合并进主 spec)
