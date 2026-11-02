## ADDED Requirements

### Requirement: pub_sub_config segment in test_cfg.yaml
The system SHALL recognize a top-level `pub_sub_config` segment in `test_cfg.yaml`. When the segment is absent, the system SHALL generate a JMX file structurally identical to one generated without the segment. When the segment is present, the system SHALL treat its fields as authoritative for publication/subscription test setup.

#### Scenario: Absent segment preserves existing behavior
- **WHEN** the `test_cfg.yaml` does not declare a `pub_sub_config` segment
- **THEN** the generated JMX SHALL NOT contain any `CREATE PUBLICATION`, `CREATE SUBSCRIPTION`, `DROP SUBSCRIPTION`, `DROP PUBLICATION`, or subscriber-db verification sampler
- **THEN** existing fixtures (`test_model_shig.yaml`, `test_cfg_shig.yaml`, `test_model_schemaless.yaml`, etc.) SHALL produce identical JMX output

#### Scenario: Validation when present
- **WHEN** `pub_sub_config` segment is present
- **THEN** the config parser SHALL require `publisher_db`, `publication_name`, `subscription_name`, and `conninfo` to be non-empty
- **THEN** the config parser SHALL derive `subscriber_db = <publisher_db> + "_sub"` at generation time
- **THEN** the config parser SHALL reject `expected_min_rows < 0` if `expected_min_rows` is provided

### Requirement: pub_sub_config tables segment with optional column subset and WHERE clause
The system SHALL recognize an optional `pub_sub_config.tables` array of `{name, columns?, where?}` entries that control the publication granularity. When the array is null, absent, or empty, the system SHALL emit a database-level publication (`FOR DATABASE`). When the array has entries, the system SHALL emit a table-level publication (`FOR TABLE ...`) per the rules in this Requirement.

#### Scenario: Empty or omitted tables segment uses database-level publication
- **WHEN** `pub_sub_config.tables` is null, absent, or `[]`
- **THEN** the Setup TG SHALL emit `CREATE PUBLICATION <pub_name> FOR DATABASE <publisher_db>` (the database-level form documented in `pub-sql.md`)
- **THEN** the existing P0 behavior SHALL be preserved: subscriber_db (subscripted as `<publisher_db>_sub`) schema is the full clone of publisher_db

#### Scenario: Single-table entry without columns or WHERE
- **WHEN** `pub_sub_config.tables` has one entry `[{name: t_cnc}]`
- **THEN** the Setup TG SHALL emit `CREATE PUBLICATION <pub_name> FOR TABLE <publisher_db>.t_cnc`

#### Scenario: Single-table entry with column subset
- **WHEN** `pub_sub_config.tables` has one entry `[{name: t_cnc, columns: [col_float8_1, col_int8_1]}]`
- **THEN** the Setup TG SHALL emit `CREATE PUBLICATION <pub_name> FOR TABLE <publisher_db>.t_cnc (col_float8_1, col_int8_1)`

#### Scenario: Single-table entry with WHERE clause
- **WHEN** `pub_sub_config.tables` has one entry `[{name: t_cnc, where: "k_timestamp > '2026-01-01'"}]`
- **THEN** the Setup TG SHALL emit `CREATE PUBLICATION <pub_name> FOR TABLE <publisher_db>.t_cnc WHERE k_timestamp > '2026-01-01'`

#### Scenario: Single-table entry with both columns and WHERE
- **WHEN** `pub_sub_config.tables` has one entry `[{name: t_cnc, columns: [col_float8_1], where: "col_float8_1 > 0"}]`
- **THEN** the Setup TG SHALL emit `CREATE PUBLICATION <pub_name> FOR TABLE <publisher_db>.t_cnc (col_float8_1) WHERE col_float8_1 > 0`

#### Scenario: Multi-table entry without columns or WHERE
- **WHEN** `pub_sub_config.tables` has two entries `[{name: t_cnc}, {name: t_motor}]`
- **THEN** the Setup TG SHALL emit `CREATE PUBLICATION <pub_name> FOR TABLE <publisher_db>.t_cnc, <publisher_db>.t_motor`

#### Scenario: Validation - tables entries must reference existing tables
- **WHEN** any `tables[i].name` does not match any `test_model.ts_dbs[j].tables[k].name`
- **THEN** the config parser SHALL raise a `ValidationError` referencing the offending table name

#### Scenario: Validation - multi-table forbids columns and WHERE
- **WHEN** `pub_sub_config.tables` has more than one entry AND any entry has `columns` non-empty or `where` non-empty
- **THEN** the config parser SHALL raise a `ValidationError` (per `pub-sql.md`: "不支持指定表中的列,不支持设置过滤条件" for multi-table publications)

#### Scenario: Validation - columns must include all primary tags and NOT NULL data columns
- **WHEN** `pub_sub_config.tables[i].columns` is set
- **THEN** the config parser SHALL require the column list to include every `primary_tag` column name from the referenced table
- **THEN** the config parser SHALL require the column list to include every `data_col` column with `nullable=false` from the referenced table
- **THEN** the config parser SHALL reject any column name not present in the referenced table's `primary_tags` / `regular_tags` / `data_cols`
- **RATIONALE**: Per `pub-sql.md`, "指定列时必须包含所有的主键列和非空列"

#### Scenario: WHERE clause syntax is not validated at parse time
- **WHEN** `pub_sub_config.tables[i].where` is set
- **THEN** the config parser SHALL only check that the string is non-empty
- **THEN** SQL syntax validation (e.g., aggregate functions, type casts, collation references, system column references, non-immutable builtins per `db-administration/pub-sub.md` "使用限制") is the operator's responsibility and SHALL be reported by the KaiwuDB server at CREATE PUBLICATION execution time

### Requirement: Generate CREATE PUBLICATION at the granularity chosen by tables segment
The system SHALL emit a `CREATE PUBLICATION <pub_sub_config.publication_name>` DDL statement in the Setup ThreadGroup, after the existing `test_model.ts_dbs` DDL statements. The exact form of the statement SHALL depend on the `tables` segment per the previous Requirement.

#### Scenario: Database-level publication (default / no tables)
- **WHEN** `pub_sub_config.tables` is null, absent, or `[]`
- **THEN** the Setup TG SHALL emit `CREATE PUBLICATION pub_iot FOR DATABASE <publisher_db>`

#### Scenario: Explicit publisher_db override applies to all forms
- **WHEN** `pub_sub_config.publisher_db` is explicitly set to a value other than null
- **THEN** the Setup TG SHALL use the explicit value as `<publisher_db>` in the emitted CREATE PUBLICATION regardless of whether the form is `FOR DATABASE` or `FOR TABLE`

### Requirement: Generate CREATE SUBSCRIPTION on subscriber DB
The system SHALL emit a `CREATE SUBSCRIPTION <pub_sub_config.subscription_name> CONNECTION '<pub_sub_config.conninfo>' PUBLICATION <pub_sub_config.publication_name>` DDL statement in the Setup ThreadGroup, after the subscriber DB DDL statements (CREATE TS DATABASE <publisher_db>_sub + all subscriber table DDL).

#### Scenario: Default subscription options
- **WHEN** `pub_sub_config` segment is present and `pub_sub_config.options` is provided with only `enable` / `ignore_history` / `retry` keys (not `target`)
- **THEN** the config parser SHALL raise a `ValidationError` requiring `options.target` to be present
- **RATIONALE**: 同集群两库场景下,服务端无法仅靠"两端 db.table 名完全对应" 推断同步关系 — KaiwuDB 不支持同 db 同 table 自订阅(per `pub-sub.md` "使用限制"),必须用 `target` 显式指明发布库表 → 订阅库表映射

#### Scenario: Explicit options with target emit WITH OPTIONS clause
- **WHEN** `pub_sub_config.options={"target": '{"iot_pub.t_cnc":"iot_sub.t_cnc"}', "enable": "on"}` is provided
- **THEN** the emitted `CREATE SUBSCRIPTION` SQL SHALL include `WITH OPTIONS (target = '{"iot_pub.t_cnc":"iot_sub.t_cnc"}', enable = 'on')`
- **THEN** the key-value order in the emitted clause SHALL preserve the insertion order of the `options` dict

#### Scenario: options absent — ValidationError
- **WHEN** `pub_sub_config.options` is null or absent
- **THEN** the config parser SHALL raise a `ValidationError` referencing the missing `options` field
- **RATIONALE**: 同集群两库场景下 `target` 必填;无 `options` 即无 `target`,DDL 无法工作

#### Scenario: Failure on empty or malformed conninfo
- **WHEN** `pub_sub_config.conninfo` is empty or not a syntactically valid libpq connection string
- **THEN** the config parser SHALL raise a `ValidationError` at parse time referencing the offending field

### Requirement: Clone publisher ts_tables schema into <publisher_db>_sub
The system SHALL generate identical `CREATE TABLE` DDL statements for every table in `test_model.ts_dbs`, with the publisher db name replaced by `<publisher_db>_sub` (hardcoded convention). The replicated DDL SHALL be emitted after the CREATE PUBLICATION statement. The subscriber schema SHALL always be the full publisher schema (a superset of the publication), regardless of whether `tables.columns` specifies a subset.

#### Scenario: Schema fidelity
- **WHEN** the publisher schema includes `CREATE TABLE iot_monitor.t_cnc (...) TAGS (...) PRIMARY TAGS (...) WITH (hash=100)`
- **THEN** the subscriber side SHALL emit `CREATE TABLE iot_monitor_sub.t_cnc (...) TAGS (...) PRIMARY TAGS (...) WITH (hash=100)` with identical column definitions, primary tags, regular tags, hash settings, and WITH clauses

#### Scenario: Column-subset publication still uses full-column subscriber schema
- **WHEN** `pub_sub_config.tables` includes `columns` (column subset publication on the publisher side)
- **THEN** the subscriber-side `CREATE TABLE` DDL SHALL still include every column from the publisher table (the subscriber schema is a superset of the publication)
- **THEN** the un-published columns SHALL accept NULL values from the CDC stream; the subscriber table SHALL NOT have additional NOT NULL constraints that the publisher does not have
- **RATIONALE**: Per `sub-sql.md`, "目标表要包含发布表的字段,无论指定字段或全部字段,且字段名称需要保持一致" — superset schema is valid

#### Scenario: Reuse DDLGenerator output
- **WHEN** the system renders subscriber DDL
- **THEN** it SHALL reuse the `DDLGenerator.generate(test_model_config)` output for the publisher and apply a two-step string substitution: (1) replace `CREATE TS DATABASE <publisher_db>` with `CREATE TS DATABASE <publisher_db>_sub`, then (2) replace `<publisher_db>.` with `<publisher_db>_sub.` via regex with word boundary. The system SHALL NOT introduce a new SQL source of truth.

### Requirement: Subscriber-side samplers use FQN cross-database without a second Connection Configuration
The system SHALL, when `pub_sub_config` segment is present, route all subscriber-side SetupTG / VerifyTG samplers through the existing single `JDBC Connection Configuration` (whose `dbUrl=${db_url}` points to defaultdb — the only db guaranteed to exist before SetupTG creates ts_dbs). Subscriber-side samplers SHALL use fully-qualified table names (`<publisher_db>_sub.<table>`) to cross-reference the subscription-side tables. The system SHALL NOT add a second `JDBC Connection Configuration` element, SHALL NOT derive a `${db_url_sub}` UDV, and SHALL NOT issue any `USE <db>` statement to switch databases. `SHOW SUBSCRIPTION` and `CREATE SUBSCRIPTION` are per-cluster metadata (per 2026-10-12 KaiwuDB dev confirmation: publications and subscriptions are cluster-wide, not db-scoped) and run directly against the defaultdb connection.

#### Scenario: Subscriber-side samplers use FQN
- **WHEN** `pub_sub_config` segment is present and a SetupTG sampler issues `CREATE SUBSCRIPTION sub_iot CONNECTION '...' PUBLICATION pub_iot`
- **THEN** the sampler SHALL run against the defaultdb connection (per `${db_url}`)
- **THEN** subscriber-side table DDL / queries SHALL use fully-qualified names of the form `<publisher_db>_sub.<table>` so they execute correctly against the defaultdb connection

#### Scenario: Publisher-side sampler runs on defaultdb
- **WHEN** `pub_sub_config` segment is present and a SetupTG sampler issues `CREATE PUBLICATION pub_iot FOR DATABASE iot_monitor`
- **THEN** the sampler SHALL run against the defaultdb connection (per `${db_url}`)

### Requirement: Generate Verify PostThreadGroup reading from <publisher_db>_sub
The system SHALL, when `pub_sub_config` segment is present, generate a Verify `PostThreadGroup` element with `testclass="PostThreadGroup"` / `guiclass="PostThreadGroupGui"` (JMeter 5.6.3 GUI display name: "tearDown Thread Group"; PostThreadGroup always runs **after** all normal ThreadGroups complete, regardless of `TestPlan.serialize_threadgroups` setting). The Verify PostThreadGroup SHALL contain, first, a `SHOW SUBSCRIPTION` status check, then one `JDBCSampler` per ts_table reading `select count(*) from <publisher_db>_sub.<table>` (FQN form; FQN makes the database override unnecessary) and asserting the row count meets or exceeds the threshold derived from `pub_sub_config.expected_min_rows` (see next Requirement). The PostThreadGroup SHALL have `ThreadGroup.delay=60` and SHALL NOT emit `<longProp name="ThreadGroup.duration">` (JMeter default behavior = run sampler list once and exit).

**Rationale for using PostThreadGroup type**: JMeter 5.6.3 offers only three TG positions — `SetupThreadGroup` (always before normal TGs), `ThreadGroup` (parallel by default, controlled by `TestPlan.serialize_threadgroups`), and `PostThreadGroup` (always after all normal TGs). To guarantee Verify runs after the Write ThreadGroup completes without changing the existing `TestPlan.serialize_threadgroups = false` setting (which keeps Write/Query parallel for SVT load simulation), the Verify TG MUST use the `PostThreadGroup` type.

#### Scenario: SHOW SUBSCRIPTION status assertion comes first
- **WHEN** the Verify TG is rendered
- **THEN** the first sampler SHALL be `SHOW SUBSCRIPTION <pub_sub_config.subscription_name>` followed by a `RegexExtractor` on the `status` column and a `JSR223Assertion` that requires the `status` text to contain `running`
- **THEN** this assertion SHALL be the first sampler in the Verify TG so that a non-running subscription fails the test before row-count assertions can give a false positive
- **THEN** the SHOW SUBSCRIPTION sampler SHALL run against the defaultdb connection (`SHOW SUBSCRIPTION` is per-cluster per 2026-10-12 KaiwuDB dev confirmation, so it returns the cluster-wide subscription regardless of the connection's current db)

#### Scenario: Single-table verification with row count assertion
- **WHEN** `test_model.ts_dbs` has one table `t_cnc` and the threshold is N (from `expected_min_rows` or the formula)
- **THEN** the Verify TG SHALL contain a sampler `select count(*) from iot_monitor_sub.t_cnc` (FQN cross-database query)
- **THEN** the sampler SHALL have a `JSR223Assertion` asserting `vars.get('count_1') >= N`

#### Scenario: Multi-table verification emits N samplers
- **WHEN** `test_model.ts_dbs` has three tables `t_cnc`, `t_motor`, `t_electmeter`
- **THEN** the Verify TG SHALL contain three samplers, one per table, each targeting `select count(*) from <publisher_db>_sub.<table>` and each with its own row-count assertion

#### Scenario: Column-subset publication does not affect row count
- **WHEN** `pub_sub_config.tables` includes `columns` (column-subset publication)
- **THEN** the subscriber-side `count(*)` SHALL still equal the publisher-side INSERT row count because CDC replicates rows, not just cells (un-published columns are NULL but rows are still replicated)
- **THEN** the inline `expected_min_rows` threshold (default `1`, or `expected_min_rows` if set) remains a valid pass criterion

### Requirement: expected_min_rows overrides the row-count threshold for filtered publications
The system SHALL recognize an optional `pub_sub_config.expected_min_rows: Optional[int]` field that overrides the Verify TG row-count threshold for every ts_table sampler.

#### Scenario: Default expected_min_rows uses inline default of 1
- **WHEN** `pub_sub_config.expected_min_rows` is null or absent
- **THEN** the Verify TG SHALL assert `count(*) >= 1` per table, where the constant `1` is inlined into `generate_pub_sub_verify_tg` (no separate `expected_rows` module)

#### Scenario: Explicit expected_min_rows overrides default
- **WHEN** `pub_sub_config.expected_min_rows=10` and the publication has a WHERE clause that filters out most rows
- **THEN** the Verify TG SHALL assert `count(*) >= 10` per table rather than the default of `1`

#### Scenario: Explicit expected_min_rows=0 accepts zero-row tables
- **WHEN** `pub_sub_config.expected_min_rows=0`
- **THEN** the Verify TG SHALL assert `count(*) >= 0` per table (tautology), accepting WHERE-filtered tables that produce zero rows as PASS

#### Scenario: expected_min_rows=0 is valid for fully filtered publications
- **WHEN** `pub_sub_config.expected_min_rows=0` (e.g., WHERE clause that excludes all rows in the test window)
- **THEN** the Verify TG SHALL assert `count(*) >= 0` (always true)
- **THEN** the SHOW SUBSCRIPTION `status=running` assertion remains the meaningful pass criterion in this scenario

### Requirement: Verify PostThreadGroup performs verification only, not cleanup
When the system SHALL generate a `PostThreadGroup` element, but the system SHALL NOT include any `DROP SUBSCRIPTION`, `DROP PUBLICATION`, or `DROP DATABASE` sampler in it (or anywhere else in the JMX). The PostThreadGroup's only role is to run the Verify samplers (`SHOW SUBSCRIPTION` status check + `select count(*) from <publisher_db>_sub.<table>` per ts_table). Database cleanup is the responsibility of the pipeline that invokes the generated JMX; the test plan generator SHALL NOT perform destructive cleanup that would interfere with ongoing replication observation.

#### Scenario: PostThreadGroup contains no DROP statement
- **WHEN** `pub_sub_config` segment is present and the JMX is rendered
- **THEN** the `PostThreadGroup` element SHALL exist and contain exactly the Verify samplers
- **THEN** no sampler whose SQL body matches `DROP SUBSCRIPTION`, `DROP PUBLICATION`, or `DROP DATABASE` SHALL appear anywhere in the JMX
- **RATIONALE**: DROP operations are low-frequency administrative actions, not stability-test workloads; dropping subscription/publication mid-test would prevent further observation of replication health; the running pipeline is responsible for pre-test cleanup and post-test teardown.

#### Scenario: Generated JMX contains no DROP statement
- **WHEN** `pub_sub_config` segment is present and the JMX is rendered
- **THEN** the JMX SHALL NOT contain a `PostThreadGroup` element
- **THEN** the JMX SHALL NOT contain any sampler whose SQL body matches `DROP SUBSCRIPTION`, `DROP PUBLICATION`, or `DROP DATABASE`
- **RATIONALE**: DROP operations are low-frequency administrative actions, not stability-test workloads; dropping subscription/publication mid-test would prevent further observation of replication health; the running pipeline is responsible for pre-test cleanup and post-test teardown.

### Requirement: Backward compatibility with existing fixtures
The system SHALL guarantee that any `test_cfg.yaml` lacking a `pub_sub_config` segment is absent produces a JMX structurally identical (up to irrelevant whitespace and serialization order) to one generated before this capability was introduced.

#### Scenario: All existing fixtures unaffected
- **WHEN** the existing fixtures (`test_model_shig.yaml`, `test_model_schemaless.yaml`, `test_model_col_bind.yaml`, `test_model_sparse_*.yaml`, and their corresponding `test_cfg_*.yaml`) are processed
- **THEN** the generated JMX SHALL be unchanged from the pre-capability baseline

### Requirement: Reference documentation
The system SHALL ship a `docs/refs/kaiwudb-pubsub-references.md` document covering the publish/subscribe protocol surface area relevant to the `pub_sub_config` flow.

#### Scenario: Reference document exists with required sections
- **WHEN** the change is reviewed
- **THEN** `docs/refs/kaiwudb-pubsub-references.md` SHALL exist
- **THEN** it SHALL include the CREATE PUBLICATION / CREATE SUBSCRIPTION syntax summary with permission requirements (SELECT for publication, INSERT for subscription)
- **THEN** it SHALL document the sync cycle (2s), end-to-end latency (~10s), and the 2-5s subscription connection establishment window
- **THEN** it SHALL include at least one insecure `conninfo` example (with `?sslmode=disable`) and one TLS `conninfo` example (with `?sslmode=require&sslrootcert=...`)
- **THEN** it SHALL include a note clarifying that database cleanup (`DROP SUBSCRIPTION` → `DROP PUBLICATION` → `DROP DATABASE`) is the pipeline's responsibility, not the test plan generator's, since DROP operations are out of scope for stability testing
- **THEN** it SHALL include a mapping table from `test_cfg.yaml::pub_sub_config` fields to the generated DDL and JMX elements, covering: `publisher_db`, `publication_name`, `subscription_name`, `conninfo`, `tables` (with `name` / `columns` / `where` per-entry semantics), `expected_min_rows`. The mapping SHALL also document the hardcoded `subscriber_db = <publisher_db>_sub` derivation rule.
- **THEN** it SHALL include the `tables` validation rules: multi-table forbids `columns`/`where`; `columns` must contain all primary tags + NOT NULL data cols; `where` string is not syntax-validated at parse time

### Requirement: Skill integration
The system SHALL update `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` with a `§7 pub_sub smoke` section covering end-to-end smoke execution for the publish/subscribe flow.

#### Scenario: Smoke skill contains pub_sub section
- **WHEN** the skill is reviewed
- **THEN** `.claude/skills/kwjdbc-jmx-smoke/SKILL.md` SHALL contain a §7 section
- **THEN** §7 SHALL describe the insecure container preparation required for pub_sub smoke (no TLS required since publication/subscription supports `?sslmode=disable`)
- **THEN** §7 SHALL provide complete `jmeter -n -t test_plan.jmx -J...` invocation templates for at least two fixtures: (a) `test_cfg_pub_sub.yaml` (database-level publication, default threshold); (b) `test_cfg_pub_sub_tables.yaml` (table-level publication with column subset + WHERE, `expected_min_rows` lowered)
- **THEN** §7 SHALL include an assertions checklist matching the SetupTG / Write TG / Verify TG lifecycle (no tearDown phase since the generator emits no DROP statements), plus a note that `expected_min_rows` must be set when the publication filters rows
- **THEN** §7 SHALL include a troubleshooting subsection covering common failures (`<publisher_db>_sub` already exists from a prior run, conninfo sslmode mismatch, `count(*)=0` likely causes, WHERE clause rejected by server at CREATE PUBLICATION execution time)
- **THEN** §7 SHALL explicitly state that database cleanup between runs is the pipeline's responsibility, with `DROP SUBSCRIPTION` / `DROP PUBLICATION` / `DROP DATABASE` as a recommended operator-side cleanup sequence
