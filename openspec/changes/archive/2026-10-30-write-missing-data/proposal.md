# write-missing-data — Proposal

## Why

当前 kwjdbc-svt 的写入侧永远是"完整笛卡尔积":每个 Write TG sampler tick(下称"一轮")把 `device_per_thread` 个设备 × `batch_lines` 个时间戳的**全部格子**都写进库里,没有任何手段制造"某些设备在某些时刻没有上报"的数据形态。真实采集链路上数据天然是稀疏的(设备掉线、采样抖动、上游丢包),而这类稀疏形态恰恰是 CDC 增量同步、时序补写、稀疏查询等下游能力的真实输入。当前生成器只能产出"完美数据",无法覆盖这类场景。

本 DCR 为写入侧引入**按批次的随机数据缺失**能力:每批次以给定概率触发一次尾部截断,截断掉的设备与时间戳取交集。

## What Changes

- `test_cfg.yaml::write_config[]` 新增可选段 `missing`,声明该表的写入侧数据缺失行为:
  ```yaml
  write_config:
    - tbl_name: iot_monitor.t_cnc
      mode: prepare
      batch_lines: 5
      device_per_thread: 2
      missing:                    # 段不存在 = 该表不做缺失
        probability: 0.5          # 必填:每写入批次下缺失数据的概率
        ts_count: 2               # 可选,缺省 0:每轮从尾部截断掉的时间戳数
        device_count: 1           # 可选,缺省 0:每轮从尾部截断掉的设备 ptag 数
  ```
  - `missing` 段是**表级**配置:挂在 `write_config[]` 的某个条目上,只作用于该条目锚定的那一张表(`tbl_name` 为 `{db}.{table}` 形式),与该表的 `mode` / `throughput` / `batch_lines` / `device_per_thread` 同属一个条目。不存在库级或全局层默认值。
  - `probability` 在段存在时**必填**,取值 `[0.0, 1.0]`:`1.0` = 必然缺失,`0.0` = 关闭缺失写入。段存在但漏写 `probability` 属于配置错误,解析阶段即失败。
  - `ts_count` / `device_count` 可选,缺省 `0`;取值上界按该表自身的 `batch_lines` / `device_per_thread` 判定(`ts_count <= batch_lines`、`device_count <= device_per_thread`),超过总数在解析阶段失败。计数取到全量即"缺整轮"(该批次一行不写),是合法形态。
- **缺失判定语义**:一行 `(device, ts)` 被跳过 ⟺ 该批次触发缺失 **且** `device` 位于本轮设备网格的尾部 `device_count` 个 **且** `ts` 位于本轮时间戳网格的尾部 `ts_count` 个(**交集**)。某一维度的 count 为 `0` 时该维度不构成约束(视为全集),因此:
  - 只配 `ts_count` → 该批次这若干个时间戳下**所有设备**的行都缺(整行缺);
  - 只配 `device_count` → 该批次这若干个设备在**所有时间戳**上的行都缺(整列缺);
  - 两个都配 → 只有"设备与时间戳同时命中尾部"的格子缺(交集);
  - 两个都为 `0` → 段存在但无缺失效果。
- **触发时机**:每一写入批次(sampler tick)独立判定一次是否触发缺失,判定发生在写入线程内,**各写入线程的判定相互独立**(暂不支持所有线程在同一批次同时缺失);`probability = 0.0` 时每批次都不触发。
- **覆盖全部 3 种写入 mode**:`direct`(inline SQL INSERT)、`prepare`(PreparedStatement batch)、`schemaless`(REST InfluxDB Line Protocol);每种 mode 的 `col_tag_bind_mode` 分支与非 bind 分支均覆盖,合计 6 处 Groovy 装配点。
- **零回归**:未声明 `missing` 段、或 `missing.probability = 0.0`(显式关闭缺失写入)的条目,生成器完全不注入缺失逻辑,生成的 JMX 与现状逐字节一致。
- **既有代码修正(独立 commit,先于功能改动落地)**:
  ① **随机源替换** —— 生成器 Groovy 脚本里的 7 处随机调用点(`write_groups.py` 4 处、`rest_write_groups.py` 2 处、`query_groups.py` 1 处)全部换成 `ThreadLocalRandom.current()`(0.7 ns,无锁无争用)。其中 `direct` 两条路径是**每行** `new Random()`(8 线程 73.4 ns/行),`Math.random()` 更是全局 CAS 争用(141 ns)。替换**行为等价**(取值域与分布不变)。
  ② **空种子池的失败模式修正** —— SetupTG 的 `SharedMemoryLoader` 在 CSV 加载失败时不再 `log.error` + 置空数组,而是**抛异常中断**;6 个写入侧消费点在共享内存池为空时**尽早抛业务异常**直接退出脚本(现状:1 处走到 `% totalRows` 除零 `ArithmeticException`,5 处 `log.warn` + 静默降级,测试会"跑完全绿"却一行数据都没写)。
  ③ **配置校验硬化** —— `write_config[]` 内同表不可配置多条(按 `tbl_name.lower()` 比较,不区分大小写),重复时配置期 `ValueError`;schemaless 路径建索引与查询统一 `to_lower`,与 JDBC 路径的大小写容忍度对齐。

  该组修正与缺失功能零耦合、可独立 review / 独立回滚。

## Capabilities

### New Capabilities

- `write-missing-data`:写入侧按批次的随机数据缺失能力,含表级 `missing` 配置段 / 尾部截断 + 交集判定语义 / 概率触发时机 / 三 mode 全覆盖 / 配置期取值校验。

### Modified Capabilities

(无。`openspec/specs/` 下现有 `conditional-relational-setup` 与本 change 无关;主 spec `docs/specs/kwdb-svt-test-plan-generator-spec.md` 的字段表在编码阶段随本 change 同步更新,属文档同步而非既有 spec 增量。)

## Impact

- **配置模型**:`src/config_parser/models.py` 新增 `MissingConfig` Pydantic 模型(`probability` 必填 / `ts_count` / `device_count` 缺省 `0`),`WriteConfig` 新增 `missing: Optional[MissingConfig] = None` 字段 + 一个 `@model_validator(mode="after")` 跨字段校验器(与既有 `check_col_tag_bind_mode_positive` 同级,校验 `ts_count <= batch_lines` / `device_count <= device_per_thread`)。
- **Groovy 装配点**(缺失逻辑注入位置,每处均为"外层设备循环 × 内层时间戳循环"的二维网格):
  - `src/jmx_skeleton_generator/generators/write_groups.py::_build_inline_sql_preprocessor_script` — `direct` 非 bind 分支 + `direct` bind 分支;
  - `src/jmx_skeleton_generator/generators/write_groups.py::_build_batch_prepared_preprocessor_body` — `prepare` 非 bind 分支;
  - `src/jmx_skeleton_generator/generators/write_groups.py::_build_batch_prepared_bind_preprocessor_body` — `prepare` bind 分支;
  - `src/jmx_skeleton_generator/generators/rest_write_groups.py::_build_rest_write_preprocessor_script` — `schemaless` 非 bind 分支 + `schemaless` bind 分支。
- **Groovy helper**:`src/utils/preprocessor_helpers.py` 新增缺失判定 helper(Groovy 源形式 + 等价 Python 实现,供单测复用同一套判定式)。
- **测试**:`tests/config_parser/` 新增 `MissingConfig` 与校验用例;`tests/jmx_skeleton_generator/` 新增 3 mode × 2 分支的生成脚本用例;`tests/utils/` 新增 helper 算法用例;`tests/kwjdbc_svt/fixtures/` 新增演示用 cfg fixture。
- **文档**:`docs/specs/kwdb-svt-test-plan-generator-spec.md` §2.0 写入配置字段表同步新增 `missing` 段及其语义。
- **既有代码改动(独立 commit)**:生成器 Groovy 脚本中的全部 7 处随机调用点换成 `ThreadLocalRandom`(`write_groups.py` 的 `:186` / `:252` / `:635` / `:744`、`rest_write_groups.py` 的 `:236` / `:329`、`query_groups.py` 的 `:489`),行为等价;`SharedMemoryLoader` 与 6 个写入侧消费点的空池处理改为抛业务异常中断;`TestConfig` 增加 `write_config[]` 同表唯一校验(按 `tbl_name.lower()` 比较);schemaless 路径建索引与查询统一 `to_lower`。
- **提交切分**:commit 1 = 既有代码修正(随机源替换 + 空种子池失败模式修正 + 配置校验硬化,与缺失功能零耦合、可独立回滚,**先于**功能 commit 落地);commit 2 = 缺失功能(新增能力)。
- **依赖**:无新增 Python 依赖,无新增 JMeter 插件。
- **回归风险**:低。未声明 `missing` 段的既有条目走原路径,JMX 输出不变;声明 `missing` 段的配置走新增分支,与现有写入/查询路径不重叠。随机热点修复会改变 `direct` 路径种子行的序列相关性(分布不变),已在 design 的 Risks 中登记。
