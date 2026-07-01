## ADDED Requirements

### Requirement: Load row seed data aggregate from CSV
The system SHALL load row seed data aggregate from CSV file and store in JMeter shared memory.

#### Scenario: Generate JSR223PreProcessor for CSV loading
- **WHEN** generating shared memory loader for table `tsdb.t_table`
- **THEN** the system SHALL generate a JSR223PreProcessor with Groovy script
- **THEN** the script SHALL read from `seeds/tsdb/t_table.csv`
- **THEN** the system SHALL use Python `csv.reader()` to parse the CSV file

#### Scenario: Parse CSV header for column names
- **WHEN** the CSV file contains header line `ts,ptag_int8_1,col_int8_1`
- **THEN** the system SHALL store column list in `__SHARED_MEM_tsdb.t_table_columns`
- **THEN** the column list SHALL be `["ts", "ptag_int8_1", "col_int8_1"]`
- **THEN** the column list SHALL be used for SQL construction

#### Scenario: Parse CSV rows into row-first structure
- **WHEN** the CSV file contains rows of data
- **THEN** the system SHALL parse each row into a List[Any]
- **THEN** the system SHALL store all rows in `__SHARED_MEM_tsdb.t_table` as List[List[Any]]
- **THEN** the row index SHALL correspond to `props.get("__SHARED_MEM_tsdb.t_table")[rowIdx]`

#### Scenario: Preserve column ordering
- **WHEN** parsing CSV rows
- **THEN** the system SHALL preserve the column order from CSV header
- **THEN** `rows[i][j]` SHALL correspond to the j-th column defined in CSV header

### Requirement: Handle CSV special characters
The system SHALL handle CSV special characters (commas, quotes, newlines) correctly using Python csv module.

#### Scenario: Handle quoted fields with commas
- **WHEN** a CSV field contains `"value1, value2"` (quoted)
- **THEN** the system SHALL parse it as a single field `"value1, value2"`

#### Scenario: Handle multiline fields
- **WHEN** a CSV field contains a newline character
- **THEN** the system SHALL correctly parse the field using CSV quoting rules

### Requirement: Store NULL values correctly
The system SHALL convert CSV `null` strings to Groovy `null` objects.

#### Scenario: Convert CSV null to Groovy null
- **WHEN** a CSV field contains the string `null`
- **THEN** the system SHALL store it as Groovy `null` object
- **THEN** the null object SHALL be distinguishable from string `"null"`

### Requirement: Generate JSR223PreProcessor XML
The system SHALL use `utils/xml_helpers` to generate JSR223PreProcessor XML component.

#### Scenario: Create JSR223PreProcessor element
- **WHEN** generating shared memory loader
- **THEN** the system SHALL use `xml_helpers.create_element()` to create JSR223PreProcessor
- **THEN** the system SHALL set script language to `groovy`
- **THEN** the system SHALL inject the generated Groovy script content

### Requirement: Support both direct write and prepared statement
The generated shared memory structure SHALL support both direct INSERT and PreparedStatement writing strategies.

#### Scenario: Support direct INSERT SQL construction
- **WHEN** using direct INSERT strategy
- **THEN** the script SHALL enable SQL construction using `columns.join(',')` and `row.collect{"'$it'"}.join(',')`

#### Scenario: Support PreparedStatement parameter binding
- **WHEN** using PreparedStatement strategy
- **THEN** the script SHALL enable parameter binding using `row[i]` for i-th parameter
- **THEN** the column order SHALL match PreparedStatement parameter order

#### Scenario: Support batch prepared statement binding
- **WHEN** using batch prepared statement strategy
- **THEN** the script SHALL enable batch binding using pure array access
- **THEN** the performance SHALL be optimal (no Map lookup overhead)

### Requirement: Generate shared memory loader for all time-series tables
The system SHALL generate shared memory loaders for all time-series tables.

#### Scenario: Generate loader for each table
- **WHEN** there are multiple time-series tables
- **THEN** the system SHALL generate one JSR223PreProcessor per table
- **THEN** each loader SHALL use unique shared memory key `__SHARED_MEM_{db}.{table}`

### Requirement: Handle CSV file not found
The system SHALL handle CSV file not found errors gracefully.

#### Scenario: Log error when CSV file not found
- **WHEN** the CSV file does not exist at the specified path
- **THEN** the script SHALL log an error message
- **THEN** the script SHALL set the shared memory variable to empty list

#### Scenario: Log error when CSV parsing fails
- **WHEN** the CSV file is malformed or cannot be parsed
- **THEN** the script SHALL log an error message with details
- **THEN** the script SHALL set the shared memory variable to empty list