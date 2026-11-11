# stream-computation Specification

## Purpose

为 kwjdbc-svt 测试计划生成器增加**流计算**(`CREATE STREAM`)场景测试能力:一条测试计划内自动完成"建目标表 → 建流 → 写源表 → 等窗口闭合 → 断言目标表产出",并对流计算的配置与服务端契约做生成期校验,把可在生成期发现的错误拦在跑压之前。

## ADDED Requirements

### Requirement: stream_config segment in test_cfg.yaml

The system SHALL recognize a top-level `stream_config` segment in `test_cfg.yaml`. When the segment is absent, the system SHALL generate a JMX file structurally identical to one generated without the segment. When the segment is present, the system SHALL treat its fields as authoritative for the stream-computation scenario.

The segment SHALL have the following fields:

| 字段 | 必填 | 说明 |
|---|---|---|
| `stream_name` | 是 | 流计算名称,非空 |
| `source_table` | 是 | 源时序表,`{db}.{table}` 形态 |
| `target_table` | 是 | 目标时序表,`{db}.{table}` 形态 |
| `select_list` | 是 | 流查询输出列清单,逗号分隔 |
| `window` | 是 | 窗口函数调用,如 `TIME_WINDOW(ts, '1m')` |
| `group_by` | 否 | 分组列清单(逗号分隔);缺省为空 |
| `options` | 否 | 流计算参数字典,原样透传给 `WITH OPTIONS`;缺省为空 |
| `expected_min_rows` | 否 | 目标表行数断言阈值,`>= 0`;缺省 `1` |
| `verify_delay_seconds` | 否 | Verify TG 等待秒数,`>= 0`;缺省 `60` |

#### Scenario: Absent segment preserves existing behavior

- **WHEN** the `test_cfg.yaml` does not declare a `stream_config` segment
- **THEN** the generated JMX SHALL NOT contain any `CREATE STREAM`, `DROP STREAM`, `SHOW STREAM`, or stream-target verification sampler
- **THEN** existing fixtures SHALL produce byte-identical JMX output compared to the baseline before this feature

#### Scenario: Validation when present

- **WHEN** the `stream_config` segment is present
- **THEN** the config parser SHALL require `stream_name`, `source_table`, `target_table`, `select_list`, and `window` to be non-empty
- **THEN** the config parser SHALL reject `expected_min_rows < 0` and `verify_delay_seconds < 0`
- **THEN** the config parser SHALL reject a `stream_config` segment whose fields are not in the documented set

### Requirement: Stream target table is declared as a regular model time-series table

The system SHALL treat the stream's target table as an ordinary time-series table declared in `test_model.yaml`. The target table's DDL SHALL be produced by the existing `DDLGenerator`, so that the generator has exactly one source of truth for table DDL.

The target table SHALL NOT appear in `write_config`, and the system SHALL exclude the target table from seed generation so that no column-seed CSV files and no shared-memory loader sampler are produced for it.

#### Scenario: Target table DDL comes from the model

- **WHEN** `stream_config.target_table` names a time-series table declared in `test_model.yaml`
- **THEN** the Setup TG SHALL emit that table's `CREATE TABLE` statement via the existing DDL generator, before the `CREATE STREAM` statement
- **THEN** the generator SHALL NOT emit any additional DDL for the target table

#### Scenario: Target table is excluded from seed generation

- **WHEN** `stream_config.target_table` names a time-series table declared in `test_model.yaml`
- **THEN** the generator SHALL NOT create column-seed CSV files for that table
- **THEN** the Setup TG SHALL NOT contain a shared-memory loader sampler for that table

#### Scenario: Target table is not written by the workload

- **WHEN** the target table does not appear in `write_config`
- **THEN** the write thread groups SHALL NOT contain any sampler writing to the target table

### Requirement: Setup thread group appends the stream DDL chain

The system SHALL append a three-step stream DDL chain to the existing setup thread group, after the model's DDL statements and before any write thread group runs. The chain SHALL be, in order:

1. `DROP STREAM IF EXISTS <stream_name>` — the stream SHALL be dropped if it exists
2. `DELETE FROM <target_db>.<target_table>` — all rows left in the target table by a previous run SHALL be removed
3. `CREATE STREAM <stream_name> INTO <target_db>.<target_table> [WITH OPTIONS (<k> = '<v>', ...)] AS SELECT <select_list> FROM <source_db>.<source_table> [GROUP BY <group_by>, ]<window>`

The `WITH OPTIONS` clause SHALL be omitted entirely when `options` is empty. Option keys and values SHALL be emitted in the order they appear in the configuration.

#### Scenario: Stream creation statement shape

- **WHEN** `stream_config` declares `stream_name: s1`, `source_table: db1.src`, `target_table: db2.dst`, `select_list: "first_row(ts), last_row(ts), count(*)"`, `window: "TIME_WINDOW(ts, '1m')"`, and no `group_by`
- **THEN** the Setup TG SHALL emit `CREATE STREAM s1 INTO db2.dst AS SELECT first_row(ts), last_row(ts), count(*) FROM db1.src GROUP BY TIME_WINDOW(ts, '1m')`

#### Scenario: Options clause shape

- **WHEN** `stream_config.options` is `{"sync_time": "0", "low_latency": "on"}`
- **THEN** the Setup TG SHALL emit `WITH OPTIONS (sync_time = '0', low_latency = 'on')` between the target table and the `AS` keyword
- **THEN** the option keys SHALL appear in configuration order

#### Scenario: Options clause omitted when empty

- **WHEN** `stream_config.options` is absent or empty
- **THEN** the Setup TG SHALL NOT emit a `WITH OPTIONS` clause

#### Scenario: Group by clause shape

- **WHEN** `stream_config.group_by` is `ptag_varchar_1`
- **THEN** the Setup TG SHALL emit `GROUP BY ptag_varchar_1, TIME_WINDOW(ts, '1m')` — the window function SHALL be the last item of the `GROUP BY` clause

#### Scenario: Repeated runs are idempotent

- **WHEN** the generated test plan is executed twice against the same database
- **THEN** the second run SHALL NOT fail with a duplicate-stream error, because the chain drops the stream first
- **THEN** the second run's target-table row count SHALL reflect only the second run's data, because the chain deletes the target table's rows first

### Requirement: Verify thread group asserts stream health and target table output

The system SHALL append a verify tear-down thread group after the write thread groups. The group SHALL wait `verify_delay_seconds` before sampling, and SHALL contain, in order:

1. A `SHOW STREAM <stream_name>` sampler whose result is asserted to have `status` containing `Enable` and an empty `error_message`
2. A `select count(*) from <target_db>.<target_table>` sampler whose result is asserted to be at least `expected_min_rows`

Both samplers SHALL reference the existing JDBC data source and SHALL use fully-qualified table names, so that no `USE`-style database switch is required.

#### Scenario: Stream status is asserted

- **WHEN** the stream failed to start and reports `status` `Disable` with a non-empty `error_message`
- **THEN** the `SHOW STREAM` sampler SHALL fail its assertion
- **THEN** the failure message SHALL name the observed status and error message

#### Scenario: Target table row count is asserted

- **WHEN** the target table holds fewer rows than `expected_min_rows`
- **THEN** the count sampler SHALL fail its assertion
- **THEN** the failure message SHALL report the observed row count and the threshold

#### Scenario: Verify delay is configurable

- **WHEN** `stream_config.verify_delay_seconds` is `120`
- **THEN** the verify thread group's delay SHALL be `120` seconds

### Requirement: Generation-time validation of the stream configuration against the model

The system SHALL validate the `stream_config` segment against `test_model.yaml` before generating any JMX, and SHALL reject the following conditions with an error naming the offending field:

- `source_table` or `target_table` does not name a time-series table declared in `test_model.ts_dbs`
- `source_table` equals `target_table`
- `source_table` does not appear in `write_config` — in that case no data would flow into the stream and the target table would never receive rows
- `select_list`'s first two items are not the window-boundary functions required by `window`: a non-sliding `TIME_WINDOW` requires `first_row(ts)` then `last_row(ts)`; a sliding `TIME_WINDOW` with three arguments requires `first(ts)` then `last(ts)`
- the number of items in `select_list` does not equal the target table's total column count — the time-series column, the data columns, the primary tags, and the regular tags

#### Scenario: Source table must be written

- **WHEN** `stream_config.source_table` names a table that is not in `write_config`
- **THEN** generation SHALL fail with an error naming the source table and stating that it is not written by any write configuration

#### Scenario: Source and target must differ

- **WHEN** `stream_config.source_table` equals `stream_config.target_table`
- **THEN** generation SHALL fail with an error naming both tables

#### Scenario: Window boundary functions are checked

- **WHEN** `stream_config.window` is `TIME_WINDOW(ts, '1m')` and `select_list` starts with `first(ts), last(ts)`
- **THEN** generation SHALL fail with an error stating that a non-sliding `TIME_WINDOW` requires `first_row(ts)` and `last_row(ts)`

#### Scenario: Output column count is checked

- **WHEN** `select_list` has fewer items than the target table's total column count
- **THEN** generation SHALL fail with an error reporting both counts

### Requirement: Stream computation is not supported on the schemaless write path

The system SHALL reject a `stream_config` segment when any `write_config` entry uses the `schemaless` write mode, instead of silently ignoring the segment.

#### Scenario: Schemaless plus stream config is rejected

- **WHEN** `test_cfg.yaml` declares a `stream_config` segment and any `write_config` entry has `mode: schemaless`
- **THEN** generation SHALL fail with an error naming the offending write configuration entry

### Requirement: Stream statements are isolated from the rest of the test plan

The generator SHALL NOT emit `CREATE STREAM`, `DROP STREAM`, `SHOW STREAM`, or target-table DDL/cleanup statements outside the dedicated setup chain and the dedicated verify thread group.

#### Scenario: Statement placement

- **WHEN** the generated JMX is inspected
- **THEN** every `CREATE STREAM` / `DROP STREAM` statement SHALL appear inside the setup thread group's hash tree
- **THEN** every `SHOW STREAM` statement and every target-table `count(*)` statement SHALL appear inside the verify tear-down thread group's hash tree
