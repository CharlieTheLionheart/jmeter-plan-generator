## ADDED Requirements

### Requirement: Generate single INSERT write sampler
The system SHALL generate a JDBCSampler for single INSERT write operations with qualified table names.

#### Scenario: Generate single INSERT SQL
- **WHEN** writing to table `t_cnc` in database `iot_monitor` with columns `ts, ptag_int8_1, col_int8_1`
- **THEN** the system SHALL generate SQL `INSERT INTO iot_monitor.t_cnc (ts, ptag_int8_1, col_int8_1) VALUES (?, ?, ?)`
- **THEN** the JDBCSampler queryType SHALL be `Update Statement`
- **THEN** the table name SHALL use the qualified format `database.table_name`

#### Scenario: Use qualified table names consistently
- **WHEN** generating INSERT statements for any table
- **THEN** the system SHALL always use the qualified table name format (database.table_name)
- **THEN** this SHALL match the format used in DDL generation statements
- **THEN** this SHALL enable multi-database test plans without context switching

### Requirement: Generate batch INSERT write sampler
The system SHALL generate a JDBCSampler for batch INSERT write operations with qualified table names.

#### Scenario: Generate batch INSERT SQL
- **WHEN** batch_lines is 10 and writing to table `t_cnc` in database `iot_monitor` with 3 columns
- **THEN** the system SHALL generate SQL with 10 row placeholders
- **THEN** the SQL SHALL be `INSERT INTO iot_monitor.t_cnc (col1, col2, col3) VALUES (?,?,?), (?,?,?), ...`
- **THEN** the table name SHALL use the qualified format `database.table_name`

#### Scenario: Handle batch_lines parameter
- **WHEN** generating batch INSERT sampler
- **THEN** the system SHALL use `${batch_lines}` variable in JMeter
- **THEN** the SQL SHALL be dynamically generated at runtime

### Requirement: Generate JSR223PreProcessor for data preparation
The system SHALL generate a JSR223PreProcessor to prepare batch data before writing.

#### Scenario: Copy rows from shared memory
- **WHEN** preparing data for writing
- **THEN** the PreProcessor SHALL read from shared memory `props.get("__SHARED_MEM_{db}.{table}")` for the row aggregate
- **THEN** the PreProcessor SHALL read the column-name list from `props.get("__SHARED_MEM_{db}.{table}_columns")` (DDL field order; overrides any Python-side fallback)
- **THEN** it SHALL randomly select a start row index
- **THEN** it SHALL copy `batch_lines` consecutive rows
- **THEN** if start + batch_lines exceeds total rows, it SHALL wrap around to the beginning

#### Scenario: Clone rows to avoid modifying shared memory
- **WHEN** copying rows from shared memory
- **THEN** each row SHALL be cloned using `row.clone()`
- **THEN** modifications SHALL not affect the shared memory data

### Requirement: Generate timestamp for each row
The system SHALL generate timestamps for each row in the batch based on base time, batch sequence, and ms_step.

#### Scenario: Get base time once per thread
- **WHEN** a thread executes the PreProcessor for the first time
- **THEN** it SHALL capture the base time as `System.currentTimeMillis()`
- **THEN** it SHALL store it in thread variable `base_time`
- **THEN** subsequent executions SHALL reuse this base time

#### Scenario: Calculate row timestamp
- **WHEN** calculating timestamp for row i in the current batch
- **THEN** the timestamp SHALL be `base_time + batch_seq * ms_step + i * (ms_step / batch_lines)`
- **THEN** the timestamp SHALL be converted to `java.sql.Timestamp`

### Requirement: Obtain thread index for multi-end coordination
The system SHALL obtain the thread index using JMeter built-in function to support multi-end coordination.

#### Scenario: Use JMeter built-in threadNum function
- **WHEN** the PreProcessor needs the thread index for device calculation
- **THEN** it SHALL use the JMeter built-in function `${__threadNum}`
- **THEN** the function SHALL return the thread's index starting from 0
- **THEN** this SHALL be used in device number calculation formulas

#### Scenario: Avoid parsing JMETER_THREAD_NAME variable
- **WHEN** considering alternative methods to get thread index
- **THEN** parsing `${__threadName}` is NOT acceptable (format "Thread Group Name 1-1" cannot be parsed reliably)
- **THEN** the system SHALL use `${__threadNum}` instead

### Requirement: Replace first primary tag placeholder
The system SHALL replace the first Primary Tag placeholder `${device_code}` with the device identifier.

#### Scenario: Calculate device number
- **WHEN** a thread needs to calculate its device number
- **THEN** it SHALL obtain thread index using JMeter built-in function `${__threadNum}`
- **THEN** it SHALL calculate as `device_start + ${__threadNum} * device_per_thread`
- **THEN** it SHALL generate device identifier as `device_{device_number}`

#### Scenario: Replace placeholder in each row
- **WHEN** preparing each row for writing
- **THEN** the first Primary Tag value SHALL be replaced with the device identifier
- **THEN** the replacement SHALL be `device_${device_start + ${__threadNum} * device_per_thread + (row_index % device_per_thread)}`

#### Scenario: Handle first primary tag in row aggregate
- **WHEN** the row seed aggregate CSV contains `${device_code}` in the first ptag column
- **THEN** the PreProcessor SHALL treat it as a placeholder to be replaced with the device identifier
- **THEN** it SHALL NOT include it in the INSERT VALUES as-is (replaced by device identifier)

### Requirement: Generate relational table initialization sampler
The system SHALL generate a JDBCSampler for one-time initialization of relational tables with qualified table names.

#### Scenario: Generate batch insert for relational table
- **WHEN** initializing relational table `t_workshop` in database `iot_metadata`
- **THEN** the system SHALL generate a JDBCSampler with batch INSERT SQL
- **THEN** the table name SHALL use the qualified format `database.table_name` (e.g., `iot_metadata.t_workshop`)
- **THEN** the sampler SHALL execute once in SetupThreadGroup
- **THEN** data SHALL be prepared by JSR223PreProcessor from seed files

#### Scenario: Loop for large datasets
- **WHEN** total rows exceed `batch_lines`
- **THEN** the system SHALL generate a Loop Controller
- **THEN** the loop SHALL iterate `ceil(total_rows / batch_lines)` times
- **THEN** each iteration SHALL prepare and insert one batch