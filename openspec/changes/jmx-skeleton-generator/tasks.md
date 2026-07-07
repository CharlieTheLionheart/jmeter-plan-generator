# Tasks: jmx-skeleton-generator

## 1. Project scaffolding and shared utilities

- [ ] 1.1 Create module directory structure under `src/jmx_skeleton_generator/` (generators, templates, tests).
- [ ] 1.2 Verify or extend `utils/xml_helpers.py` to build standard JMeter XML elements (`TestPlan`, `hashTree`, `stringProp`, `boolProp`, `longProp`, `intProp`, `elementProp`, `Arguments`, `ThreadGroup`, `SetupThreadGroup`, `JDBCSampler`, `JSR223PreProcessor`).
- [ ] 1.3 Add JMeter XML namespace / version constants for JMeter 5.5+ compatibility.
- [ ] 1.4 Write unit tests for `utils/xml_helpers.py` covering element creation, attribute serialization, and XML round-trip.

## 2. TestPlan and global User Defined Variables

- [ ] 2.1 Implement `TestPlanGenerator` to create the root `<jmeterTestPlan>` and `<TestPlan>` with a `hashTree`.
- [ ] 2.2 Implement `UserDefinedVariablesGenerator` to map `TestConfig.conn_config` into `<Arguments>` / `<elementProp>` entries (e.g., `${db_url}`, `${conn_pool_size}`, `${device_start}`).
- [ ] 2.3 Add validation for `conn_config` keys/values (empty keys, illegal XML characters, unsupported value types) with explicit error messages.
- [ ] 2.4 Write unit tests for TestPlan + variables generation, including empty config and invalid character edge cases.

## 3. SetupThreadGroup for DDL execution

- [ ] 3.1 Implement `DDLSetupThreadGroupGenerator` to create a `SetupThreadGroup` with one thread.
- [ ] 3.2 Generate one `JDBCSampler` per DDL statement, referencing `${db_url}` and auto-commit enabled.
- [ ] 3.3 Define behavior when DDL list is empty: skip the SetupThreadGroup entirely.
- [ ] 3.4 Write unit tests for DDL SetupThreadGroup generation, including empty DDL list and CREATE DATABASE / CREATE TABLE scenarios.

## 4. Shared memory initialization integration

- [ ] 4.1 Define the interface contract with `shared-memory-initializer` module (input: table name + seed aggregate file path; output: `JSR223PreProcessor` element).
- [ ] 4.2 Implement `SharedMemorySetupThreadGroupGenerator` to create a `SetupThreadGroup` with one thread.
- [ ] 4.3 Integrate generated `JSR223PreProcessor` components into the shared memory SetupThreadGroup.
- [ ] 4.4 Define behavior when seed aggregate file is missing or malformed: fail fast with a clear error.
- [ ] 4.5 Write unit tests for shared memory SetupThreadGroup integration, including missing seed file handling.

## 5. Write thread groups skeleton

- [ ] 5.1 Implement `WriteThreadGroupsGenerator` to create one `ThreadGroup` per time-series table.
- [ ] 5.2 Set `num_threads`, loop count `-1`, and duration `${test_duration}` per table write configuration.
- [ ] 5.3 Place a `JDBCSampler` placeholder under each write thread group for later filling by the write module.
- [ ] **5.4 (CRITICAL) Sampler type by write mode**: 根据 `WriteConfig.mode` 决定 Sampler 类型：
  - `batch_prepared` 模式：**必须使用 `JSR223Sampler`**（而非 `JDBCSampler`），配合前置 `JSR223PreProcessor` 准备批次数据，详见 write-strategies/design.md §JSR223Sampler 用于 batch_prepared
  - `single_prepared` / `single_insert` / `batch_insert` 模式：使用 `JDBCSampler`
  - `schemaless` 模式：使用 `JSR223Sampler`（T2）
- [ ] **5.5 (CRITICAL) JSR223PreProcessor for batch_prepared**：`batch_prepared` 模式需要在 `JSR223Sampler` 前挂载 `JSR223PreProcessor`，负责从共享内存行种子总集随机拷贝连续 `batch_lines` 行、装配时间戳和设备标识，写入线程变量 `__BATCH_ROWS_${tableName}` 供 Sampler 读取
- [ ] 5.6 Define behavior when no tables are configured: skip write thread groups.
- [ ] 5.7 Write unit tests for write thread group generation, including zero-table configuration and sampler type selection per mode.

## 6. Query thread groups skeleton

- [ ] 6.1 Implement `QueryThreadGroupsGenerator` to create one `ThreadGroup` per query configuration.
- [ ] 6.2 Set `num_threads` (default 1) and duration `${test_duration}` per query configuration.
- [ ] 6.3 Generate a `JDBCSampler` with `Prepared Select Statement` query type; replace each ``?`` placeholder in the SQL with ``${param_N}`` (N = 0, 1, 2, ...); set `queryArguments` to ``${param_0},${param_1},...``.
- [ ] **6.4 (CRITICAL) JSR223PreProcessor for query parameter binding**: For each query thread group, generate a `JSR223PreProcessor` (Groovy) **before** the JDBCSampler that:
  - Parses the SQL to extract column names preceding each ``?`` placeholder
  - For each resolved column, constructs the seed file path as ``{seed_dir}/{column_name}.csv`` and randomly samples one line into ``param_N``
  - Falls back to ``{seed_dir}/param.csv`` when column name cannot be resolved
  - Maps the string ``"null"`` to empty string ``""`` for JDBC NULL handling
- [ ] 6.5 Define behavior when no queries are configured: skip query thread groups.
- [ ] 6.6 Write unit tests for query thread group generation, including zero-query configuration, SQL with/without placeholders, and column name resolution.

## 7. Thread group ordering and assembly

- [ ] 7.1 Implement `JMXAssembler` to compose elements in required order: DDL SetupThreadGroup → Shared Memory SetupThreadGroup → Write ThreadGroups → Query ThreadGroups.
- [ ] 7.2 Ensure `SetupThreadGroup` elements appear before regular thread groups, and shared memory SetupThreadGroup appears after DDL SetupThreadGroup.
- [ ] 7.3 Write integration tests for full assembly ordering.

## 8. JMX serialization and output

- [ ] 8.1 Implement `JMXWriter` to serialize the assembled XML tree to a `.jmx` file with UTF-8 encoding.
- [ ] 8.2 Add output directory handling with version/timestamp suffix to avoid overwriting existing files.
- [ ] 8.3 Validate generated XML is well-formed and includes the JMeter 5.5+ namespace / version attributes.
- [ ] 8.4 Write unit tests for serialization, encoding, and output path generation.

## 9. End-to-end generation and compatibility

- [ ] 9.1 Implement the top-level `JMXSkeletonGenerator` facade that orchestrates config parsing, seed data lookup, and all sub-generators.
- [ ] 9.2 Add an end-to-end test generating a complete `.jmx` file from a sample test configuration.
- [ ] 9.3 Verify the generated `.jmx` file opens successfully in JMeter 5.5+ (manual or automated smoke check).
- [ ] 9.4 Document JMeter minimum version requirement in module README or generated file comment.

## 10. Review findings remediation

- [ ] 10.1 Update specs or design doc to explicitly define boundary behaviors for empty config, zero tables/queries, missing seed files, and invalid `conn_config` values.
- [ ] 10.2 Add negative test cases: illegal XML character escaping, oversized `conn_config` keys/values, cyclic variable names, missing seed file paths.
- [ ] 10.3 Add compatibility / smoke test matrix for JMeter 5.5 and 5.6.
- [ ] 10.4 Clarify the `conn_config` dynamic traversal boundary: confirm `config-parser` outputs a standardized key-value list and this module only performs format conversion.
- [ ] 10.5 Resolve open question on shared memory data structure (List vs Map) and document the decision with memory-usage guidance.
