## ADDED Requirements

### Requirement: Parse SQL placeholders
The system SHALL extract all `?` placeholder positions from a SQL query, excluding those within string literals. The state machine that scans SQL characters SHALL be a single function shared by both placeholder extraction (`extract_placeholders`) and placeholder-to-variable rewriting (`replace_placeholders_with_vars`), so future rule changes (e.g. supporting a new escape sequence) only require updating one site.

#### Scenario: Single-source state machine applied to extraction
- **WHEN** `extract_placeholders(sql)` runs
- **THEN** it SHALL internally call a shared scanner (e.g. `_scan_sql_tokens(sql)`) that returns `[(position, kind)]` for every meaningful token
- **THEN** there SHALL be no duplicate inline state machines; the same `_scan_sql_tokens` SHALL be used by `replace_placeholders_with_vars` for the `?`-to-`${param_N}` rewrite

#### Scenario: Tokenised positions are reused by the rewriter
- **WHEN** the rewriter replaces each `?` placeholder
- **THEN** it SHALL iterate over the same token list from the shared scanner and emit `${param_N}` only for tokens whose `kind == PLACEHOLDER` (skipping `STRING`, `COMMENT_LEADER`, `SEPARATOR`)
- **THEN** this guarantees byte-for-byte parity between the placeholder count returned by extraction and the replacement count emitted by rewriting

#### Scenario: Extract placeholders from simple query
- **WHEN** SQL is `SELECT * FROM t WHERE col_int8_1 = ?`
- **THEN** the system SHALL extract one placeholder at position 38

#### Scenario: Extract placeholders from complex query
- **WHEN** SQL is `SELECT * FROM t WHERE col1 = ? AND col2 = ? OR col3 LIKE ?`
- **THEN** the system SHALL extract three placeholders at their respective positions

#### Scenario: Ignore placeholders in string literals
- **WHEN** SQL is `SELECT * FROM t WHERE name = 'What is this?' AND col = ?`
- **THEN** the system SHALL extract only the second placeholder (ignoring the one in the string literal)

#### Scenario: Ignore placeholders in double-quoted string literals
- **WHEN** SQL is `SELECT "col?" FROM t WHERE col = ?`
- **THEN** the system SHALL extract only the second placeholder (ignoring the one inside the double-quoted identifier)

#### Scenario: Handle SQL escape sequences inside string literals
- **WHEN** SQL is `SELECT * FROM t WHERE name = 'O''Brien' AND col = ?`
- **THEN** the system SHALL treat `''` as an embedded escaped single quote (KaiwuDB / ANSI SQL convention), keeping the string literal open across the escape, and SHALL extract only the second placeholder

### Requirement: Reject SQL comments in query templates
The system SHALL refuse any SQL query template that contains `--` line comments or `/* */` block comments in non-string-literal positions.

#### Scenario: Reject SQL with single-line comment
- **WHEN** SQL is `SELECT * FROM t WHERE col = ? -- some annotation`
- **THEN** the system SHALL raise `QueryGenerationError` with message containing `comment not allowed` and the position of `--`

#### Scenario: Reject SQL with block comment
- **WHEN** SQL is `SELECT * FROM t WHERE col = ? /* some annotation */`
- **THEN** the system SHALL raise `QueryGenerationError` with message containing `comment not allowed` and the position of `/*`

#### Scenario: Allow `'` inside double-quoted identifier (no nesting)
- **WHEN** SQL is `SELECT * FROM t WHERE col = ? AND "weird'name" = ?`
- **THEN** the system SHALL successfully parse both `?` placeholders without entering any string nesting depth

#### Scenario: Allow `''` escape inside single-quoted string (no nesting)
- **WHEN** SQL is `SELECT * FROM t WHERE col = ? AND name = 'it''s'`
- **THEN** the system SHALL treat `''` as an escaped single quote (no nested string state) and extract both placeholders correctly

### Requirement: Bind placeholder to column context
The system SHALL analyze the SQL context before each `?` to identify the column name.

#### Scenario: Bind with table-qualified column
- **WHEN** SQL is `SELECT * FROM db.t WHERE t.col_int8_1 = ?`
- **THEN** the system SHALL bind the placeholder to column `col_int8_1`

#### Scenario: Bind with bare column name
- **WHEN** SQL is `SELECT * FROM t WHERE col_int8_1 = ?`
- **THEN** the system SHALL bind the placeholder to column `col_int8_1`

#### Scenario: Reject unbindable placeholder
- **WHEN** SQL is `SELECT * FROM t LIMIT ?`
- **THEN** the system SHALL fail with an error indicating the placeholder cannot be bound to a column

### Requirement: Generate query parameter script
The system SHALL generate a Groovy script for JSR223PreProcessor that samples values from seed files.

#### Scenario: Generate parameter binding script
- **WHEN** a query has 2 parameters bound to columns `col_int8_1` and `ptag_varchar_1`
- **THEN** the system SHALL generate Groovy code that reads from corresponding seed files
- **THEN** each parameter SHALL be randomly sampled using `(int)(Math.random() * seedLines.size())`
- **THEN** values SHALL be set to JMeter variables `param_0` and `param_1`

#### Scenario: Handle NULL values in seeds
- **WHEN** a sampled value from seed file is the string `"null"`
- **THEN** the script SHALL set the JMeter variable to empty string `""`
- **WHEN** the sampled value is not `"null"`
- **THEN** the script SHALL set the JMeter variable to the actual value

### Requirement: Generate query sampler
The system SHALL generate a JDBCSampler for executing queries with prepared statements.

#### Scenario: Generate JDBCSampler configuration
- **WHEN** generating a query sampler
- **THEN** the queryType SHALL be `Prepared Select Statement`
- **THEN** the query SHALL contain the original `?` placeholders
- **THEN** queryArguments SHALL reference JMeter variables like `${param_0},${param_1},...`
- **THEN** queryArgumentsTypes SHALL be populated with JDBC type names (e.g., `VARCHAR,INTEGER`)

#### Scenario: Attach JSR223PreProcessor
- **WHEN** generating a query sampler
- **THEN** a JSR223PreProcessor SHALL be attached as a child element
- **THEN** the PreProcessor script SHALL be generated by the parameter binding algorithm
- **THEN** the PreProcessor SHALL execute before each JDBCSampler execution

### Requirement: Generate query thread group
The system SHALL generate one ThreadGroup for each query configuration.

#### Scenario: Generate thread group with default concurrency
- **WHEN** a query has no explicit `num_threads` in config
- **THEN** the thread group SHALL have 1 thread
- **THEN** the thread group SHALL use `Prepared Select Statement` mode

#### Scenario: Generate thread group with specified concurrency
- **WHEN** a query has `num_threads=5` in config
- **THEN** the thread group SHALL have 5 threads
- **THEN** each thread SHALL independently sample parameters from seed files

### Requirement: Query timer takes the per-query literal throughput value
The system SHALL hand the per-query `QueryConfig.throughput` as a literal string into the `ConstantThroughputTimer.throughput` property, with NO JMeter variable wrapping. The timer generation delegates to the `throughput-control` module.

#### Scenario: Query timer embeds literal throughput
- **WHEN** `generate_query_thread_groups(query_config)` runs with a `QueryConfig(throughput=4)`
- **THEN** the generated `ConstantThroughputTimer` SHALL have `throughput="4"` (literal, not `${...}`)

#### Scenario: Distinct throughput values produce distinct literals
- **WHEN** two queries have `throughput=4` and `throughput=12`
- **THEN** each generated timer SHALL embed its own literal (`"4"` vs `"12"`)
- **THEN** changing one query's throughput SHALL NOT affect the other timer

#### Scenario: No `${query_throughput}` UDV is referenced
- **WHEN** rendering query ThreadGroups end-to-end
- **THEN** the JMX SHALL NOT contain any reference to a `${query_throughput}` JMeter variable

### Requirement: Reject queries with unbindable parameters
The system SHALL reject query configurations that contain placeholders which cannot be bound to column seed caches.

#### Scenario: Reject LIMIT placeholder
- **WHEN** a query contains `LIMIT ?`
- **THEN** the system SHALL report an error and refuse to generate the test plan
- **THEN** the error message SHALL indicate that the placeholder cannot be bound to a column seed cache

#### Scenario: Reject IN clause with multiple placeholders
- **WHEN** a query contains `WHERE col IN (?, ?, ?)` (≥ 2 placeholders inside IN)
- **THEN** the system SHALL report an error and refuse to generate the test plan
- **THEN** the error message SHALL indicate that placeholders in IN clauses are not supported

#### Scenario: Accept single-element IN clause
- **WHEN** a query contains `WHERE col IN (?)` (exactly 1 placeholder inside IN)
- **THEN** the system SHALL treat it equivalently to `WHERE col = ?` and bind the placeholder to `col`

### Requirement: Reject unterminated string literals at EOF
The system SHALL reject SQL whose state machine did not return to NORMAL after full traversal. Only string-literal-related terminations apply; comment states are forbidden by the previous requirement and never produced.

#### Scenario: Reject unterminated single-quoted string
- **WHEN** SQL ends inside a single-quoted string literal (e.g. `WHERE name = 'O'Bri`)
- **THEN** the system SHALL raise `QueryGenerationError` with message containing `unterminated` and `SQ_STRING` and the last character index

#### Scenario: Reject unterminated double-quoted identifier
- **WHEN** SQL ends inside a double-quoted identifier (e.g. `SELECT "weird name`)
- **THEN** the system SHALL raise `QueryGenerationError` with message containing `unterminated` and `DQ_STRING` and the last character index

### Requirement: Handle seed file cache and concurrency
The system SHALL define a clear strategy for reading seed files during sampler execution, including behaviour for empty / single-row files and for parallel threads.

#### Scenario: Single-row seed file deterministic sample
- **WHEN** a column seed file contains exactly one row
- **THEN** the script SHALL pick that row regardless of `Math.random()` output (the only sample is deterministic)

#### Scenario: Empty seed file does not block execution
- **WHEN** a column seed file is missing or empty
- **THEN** the script SHALL fall back to the literal string `"null"` so the JDBC sampler still receives a parameter (matches design.md "种子文件为空时不阻塞")
- **THEN** the fallback `"null"` token SHALL be normalised to empty string `""` by the parameter binding script (same rule as NULL-as-string in CSV)

#### Scenario: Concurrent threads each read seed file independently
- **WHEN** multiple JMeter threads execute the same query concurrently
- **THEN** each thread SHALL read the seed file from disk on every iteration (no in-JVM cache) so independent sampling per thread is preserved
- **THEN** race conditions on the seed file are tolerated: filesystem read contention is acceptable for the SVT workload

### Requirement: Resolve seed file by unique column
The system SHALL locate the seed file for each parameter column by a strict naming convention enforced by the seed-data-generator (`seeds/{db}/{table}/{index}_{col_name}.csv`); conflicts SHALL raise `QueryGenerationError`.

#### Scenario: Unique seed file per column
- **WHEN** `tableDir` contains exactly one file matching `*_{col_name}.csv` for the bound column `col_name`
- **THEN** that file SHALL be used as the sample source

#### Scenario: Multiple matching seed files (naming conflict)
- **WHEN** `tableDir` contains two or more files matching `*_{col_name}.csv` for the same `col_name`
- **THEN** the system SHALL raise `QueryGenerationError` with message listing all matching files; sampling from the wrong file would silently corrupt test data

#### Scenario: No matching seed file
- **WHEN** `tableDir` contains no file matching `*_{col_name}.csv`
- **THEN** the parameter binding script SHALL fall back to the literal string `"null"` (matches the empty-file scenario; same NULL handling rule applies)

### Requirement: Reject unterminated string literals and comments
The system SHALL reject SQL whose state machine did not return to NORMAL after full traversal.

#### Scenario: Reject unterminated single-quoted string
- **WHEN** SQL ends inside a single-quoted string literal (e.g. `WHERE name = 'O'Bri`)
- **THEN** the system SHALL raise `QueryGenerationError` with kind `SQ_STRING` and the last character index

#### Scenario: Reject unterminated double-quoted identifier
- **WHEN** SQL ends inside a double-quoted identifier (e.g. `SELECT "weird name`)
- **THEN** the system SHALL raise `QueryGenerationError` with kind `DQ_STRING` and the last character index

#### Scenario: Block / line comment EOF states are unreachable
- **WHEN** the previous requirement forbidding SQL comments is enforced
- **THEN** the runtime state machine SHALL never enter `LINE_COMMENT` or `BLOCK_COMMENT` because the leading `--` / `/*` triggers an immediate error first
- **THEN** this scenario exists only for spec completeness; tests covering it SHALL assert it is unreachable by first hitting the comment-rejection error