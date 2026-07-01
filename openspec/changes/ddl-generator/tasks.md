# Tasks: ddl-generator

## 1. Project scaffolding and public API

- [x] 1.1 Create `src/ddl_generator/__init__.py` exporting the public API (`DDLGenerator`, `ColumnNameGenerator`, `DataTypeMapper`).
- [x] 1.2 Define the module-level interfaces and type hints expected by downstream consumers (config-parser output shape, SQL script output shape).
- [x] 1.3 Add a README/note in the module docstring describing KaiwuDB version assumptions and identifier lower-case convention.

## 2. Data type mapping

- [x] 2.1 Implement `DataTypeMapper` to convert configuration `col_type` values (e.g., `int8`, `varchar(16)`, `timestamptz`) to KaiwuDB-compatible lower-case syntax (`int8`, `varchar(16)`, `timestamptz`).
- [x] 2.2 Reject unknown or unsupported data types with a clear `ValueError`.
- [x] 2.3 Add unit tests covering `int8`, `varchar(N)`, `timestamptz`, and an unknown type.

## 3. Column name generator

- [x] 3.1 Implement `ColumnNameGenerator` producing names in the form `{type_prefix}_{data_type}_{sequence}`.
- [x] 3.2 Support prefixes `pk`, `col`, `ptag`, `rtag` for primary keys, data columns, primary tags, and regular tags.
- [x] 3.3 Normalize the data-type portion to lower case and strip length parentheses when forming the name (e.g., `varchar(16)` -> `col_varchar_1`).
- [x] 3.4 Increment sequence numbers per prefix + data-type combination independently.
- [x] 3.5 Add unit tests for all prefixes, sequence increments, and multi-column same-type ordering.

## 4. Relational database DDL generation

- [x] 4.1 Implement relational `CREATE DATABASE` generation supporting `IF NOT EXISTS`, `WITH ENCODING`, and `COMMENT` clauses.
- [x] 4.2 Implement relational `CREATE TABLE` generation with qualified table names (`database.table_name`).
- [x] 4.3 Generate column definitions including `NOT NULL` when `nullable` is `false` or omitted, and omit it when `nullable` is `true`.
- [x] 4.4 Generate `PRIMARY KEY` constraints from configured primary keys.
- [x] 4.5 Support optional table `COMMENT` and `IF NOT EXISTS` clauses.
- [x] 4.6 Add unit tests for each scenario in `specs/ddl-generation/spec.md` and for multi-database qualified-name output.

## 5. Time-series database DDL generation

- [x] 5.1 Implement time-series `CREATE TS DATABASE` generation supporting `RETENTIONS` and `PARTITION INTERVAL` without `WITH` or quotes.
- [x] 5.2 Implement time-series `CREATE TABLE` generation with qualified table names.
- [x] 5.3 Generate timestamp column, primary tags, regular tags, and data columns with correct `NOT NULL` handling.
- [x] 5.4 Generate `TAGS (...)` and `PRIMARY TAGS (...)` clauses.
- [x] 5.5 Support optional table-level `WITH RETENTIONS` and `WITH HASH` clauses.
- [x] 5.6 Add unit tests for each scenario in `specs/ddl-generation/spec.md`, including combined optional clauses.

## 6. SQL script organization and output

- [x] 6.1 Implement DDL aggregation that groups statements by database and then by table.
- [x] 6.2 Render the aggregated DDL as a semicolon-separated SQL script.
- [x] 6.3 Ensure database-level DDL precedes table-level DDL within each database group.
- [x] 6.4 Add tests verifying grouping order, semicolon separation, and absence of `USE database` statements.

## 7. Error handling and boundary conditions

- [x] 7.1 Validate required fields (database name, table name, column definitions) and raise clear errors for missing input.
- [x] 7.2 Decide and document the strategy for SQL keyword / special-character identifiers (reject or quote) and implement validation accordingly.
- [x] 7.3 Ensure any generation-time failure raises immediately rather than silently continuing.
- [x] 7.4 Add error-input tests for empty config, missing names, unknown types, and malformed column definitions.

## 8. Integration and verification

- [x] 8.1 Run the full `tests/ddl_generator/` test suite and fix any failures.
- [x] 8.2 Verify that all generated SQL identifiers and keywords are lower case.
- [x] 8.3 Verify that every `CREATE TABLE` uses a qualified table name.
- [x] 8.4 Confirm `config-parser` output shape stability before finalizing the module's input contract.
- [x] 8.5 Review and update `__init__.py` exports to keep internal modules hidden.
