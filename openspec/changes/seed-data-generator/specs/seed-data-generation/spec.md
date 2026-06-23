## ADDED Requirements

### Requirement: Generate column seed data
The system SHALL generate seed data for each column based on `val_range` and `seed_num`.

#### Scenario: Generate integer seed data with lower bound
- **WHEN** a column has `val_range=">=1"` and `seed_num=10`
- **THEN** the system SHALL generate 10 integer values >= 1

#### Scenario: Generate integer seed data with upper bound
- **WHEN** a column has `val_range="<=100"` and `seed_num=10`
- **THEN** the system SHALL generate 10 integer values <= 100

#### Scenario: Generate integer seed data with closed interval
- **WHEN** a column has `val_range="[1,100]"` and `seed_num=10`
- **THEN** the system SHALL generate 10 integer values in [1, 100] (inclusive)

#### Scenario: Generate integer seed data with open interval
- **WHEN** a column has `val_range="(1,100)"` and `seed_num=10`
- **THEN** the system SHALL generate 10 integer values in (1, 100) (exclusive)

#### Scenario: Generate float seed data
- **WHEN** a column has `val_range=">=0.0"` and `seed_num=10`
- **THEN** the system SHALL generate 10 float values >= 0.0

#### Scenario: Generate string seed data with regex
- **WHEN** a column has `val_range="^[一-鿿a-zA-Z0-9-_]{2,10}$"` and `seed_num=10`
- **THEN** the system SHALL generate 10 strings matching the regex pattern

#### Scenario: Generate enum seed data
- **WHEN** a column has `val_range="enum:M1,M2,M3"` and `seed_num=10`
- **THEN** the system SHALL generate 10 values by cycling through [M1, M2, M3] in order

#### Scenario: Generate enum seed data with less than seed_num
- **WHEN** a column has `val_range="enum:M1,M2,M3"` and `seed_num=2`
- **THEN** the system SHALL generate 2 values: [M1, M2]

### Requirement: Generate NULL values
The system SHALL generate NULL values based on `nullable` and `null_rate` configuration.

#### Scenario: Generate NULL values with null_rate > 0
- **WHEN** a column has `nullable=true`, `null_rate=0.2`, and `seed_num=10`
- **THEN** the system SHALL generate 2 NULL values and 8 non-NULL values
- **THEN** the NULL values SHALL be randomly distributed in the column seed file

#### Scenario: Generate no NULL values with null_rate=0
- **WHEN** a column has `nullable=true`, `null_rate=0.0`, and `seed_num=10`
- **THEN** the system SHALL generate 10 non-NULL values

#### Scenario: Generate no NULL values with nullable=false
- **WHEN** a column has `nullable=false` and `seed_num=10`
- **THEN** the system SHALL generate 10 non-NULL values

### Requirement: Generate foreign key reference seed data
The system SHALL generate seed data for columns with foreign key references by sampling from the referenced table's primary key seed data.

#### Scenario: Sample from foreign key reference
- **WHEN** a column has `val_range="ref:iot_metadata.t_workshop.pk_int8_1"` and `seed_num=10`
- **THEN** the system SHALL sample 10 values from the referenced primary key column's seed data
- **THEN** the sampling SHALL be uniform random with replacement

### Requirement: Generate column seed files
The system SHALL output column seed data to files with the naming convention `{column_index}_{column_name}.{type_name}`.

#### Scenario: Output column seed file
- **WHEN** column index is 1, column name is `ptag_int8_1`, and type name is `int8`
- **THEN** the system SHALL create file `seeds/{table_name}/1_ptag_int8_1.int8`
- **THEN** the file SHALL be in CSV format with a header line containing `value`
- **THEN** each seed value SHALL be written on a separate row in the CSV file
- **THEN** NULL values SHALL be written as `null` (case-insensitive)
- **THEN** CSV quoting rules SHALL be used to handle special characters (newlines, commas, quotes)

### Requirement: Generate row seed data aggregate
The system SHALL generate a row seed data aggregate by combining column seed files.

#### Scenario: Calculate row seed aggregate size
- **WHEN** a table has columns with seed_num values of [5, 10, 20]
- **THEN** the row seed aggregate SHALL have 20 rows (max seed_num)

#### Scenario: Fill shorter columns cyclically
- **WHEN** a column has seed_num=5 and the row aggregate has 20 rows
- **THEN** the column's values SHALL be repeated cyclically to fill 20 rows (pattern repeats 4 times)

### Requirement: Read column seed files in column index order
The system SHALL read column seed files in numerical order of column index.

#### Scenario: Read columns in index order
- **WHEN** column seed files are named `1_col_int8_1.int8`, `10_col_varchar_1.varchar`, `2_col_float4_1.float4`
- **THEN** the system SHALL read them in order: `1_col_int8_1.int8`, `2_col_float4_1.float4`, `10_col_varchar_1.varchar`

### Requirement: Generate row seed data aggregate as shared memory data
The system SHALL generate row seed data aggregate in CSV format with file naming convention `{database}.{table}.csv`.

#### Scenario: Output row seed data aggregate as CSV
- **WHEN** all column seed files are combined into the row aggregate for table `tsdb.t_table`
- **THEN** the system SHALL output to file `seeds/tsdb.t_table.csv`
- **THEN** the first line SHALL contain column names as header (comma-separated)
- **THEN** each subsequent line SHALL contain one row of seed values (comma-separated)
- **THEN** the output SHALL preserve column ordering for correct sampling

#### Scenario: CSV handles special characters correctly
- **WHEN** a column value contains commas (e.g., "value1, value2") or quotes
- **THEN** the system SHALL use CSV quoting rules to escape the field properly
- **THEN** Python's `csv.reader()` can correctly parse the field without manual splitting

#### Scenario: CSV supports prepared statement parameter binding
- **WHEN** the CSV file is loaded using Python's `csv.reader()`
- **THEN** each parsed row can be directly used as parameter list for prepared statement execution
- **THEN** row[i] corresponds to the i-th parameter in the `VALUES (?, ?, ...)` clause