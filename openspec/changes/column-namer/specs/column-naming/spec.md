## ADDED Requirements

### Requirement: Allocate column counts by type_proportion
The system SHALL allocate actual column counts to each data type based on `type_proportion` and total column count using the `floor + greedy` algorithm.

#### Scenario: Allocate columns with exact proportions
- **WHEN** total column count is 100 and proportions are [0.25, 0.25, 0.5]
- **THEN** the system SHALL allocate [25, 25, 50] columns respectively
- **THEN** the sum of allocated columns SHALL equal 100

#### Scenario: Allocate columns with fractional proportions
- **WHEN** total column count is 10 and proportions are [0.33, 0.33, 0.34]
- **THEN** the system SHALL first allocate [3, 3, 3] using floor
- **THEN** the system SHALL greedily distribute the remaining 1 column to the type with the largest fractional part
- **THEN** the final allocation SHALL be [3, 4, 3] or [4, 3, 3] (order may vary)

#### Scenario: Handle empty or zero total
- **WHEN** total column count is 0
- **THEN** the system SHALL return an empty allocation list
- **WHEN** proportions list is empty
- **THEN** the system SHALL return an empty allocation list

### Requirement: Generate column names with prefix mapping
The system SHALL generate column names using the pattern `{prefix}_{type}_{sequence}` with prefix mapping based on column group type.

#### Scenario: Generate data column names
- **WHEN** generating column names for `data_cols` group with `col_type=int8`
- **THEN** the system SHALL use prefix `col`
- **THEN** the system SHALL generate names like `col_int8_1`, `col_int8_2`, ...

#### Scenario: Generate primary key column names
- **WHEN** generating column names for `primary_keys` group with `col_type=int8`
- **THEN** the system SHALL use prefix `pk`
- **THEN** the system SHALL generate names like `pk_int8_1`, `pk_int8_2`, ...

#### Scenario: Generate primary tag column names
- **WHEN** generating column names for `primary_tags` group with `col_type=int8`
- **THEN** the system SHALL use prefix `ptag`
- **THEN** the system SHALL generate names like `ptag_int8_1`, `ptag_int8_2`, ...

#### Scenario: Generate regular tag column names
- **WHEN** generating column names for `regular_tags` group with `col_type=varchar(10)`
- **THEN** the system SHALL use prefix `rtag`
- **THEN** the system SHALL generate names like `rtag_varchar_1`, `rtag_varchar_2`, ...

### Requirement: Normalize data type for column names
The system SHALL normalize data types by removing length/precision modifiers when generating column names.

#### Scenario: Normalize varchar with length
- **WHEN** the column type is `varchar(16)`
- **THEN** the system SHALL use `varchar` in the column name

#### Scenario: Normalize decimal with precision
- **WHEN** the column type is `decimal(10,2)`
- **THEN** the system SHALL use `decimal` in the column name

### Requirement: Maintain sequential numbering within each type
The system SHALL maintain sequential numbering for columns of the same data type across all columns in a group.

#### Scenario: Number columns sequentially
- **WHEN** a table has 3 int8 columns and 2 varchar columns in `data_cols`
- **THEN** the system SHALL generate `col_int8_1`, `col_int8_2`, `col_int8_3`, `col_varchar_1`, `col_varchar_2`
- **THEN** int8 columns SHALL be numbered 1-3 and varchar columns numbered 1-2

### Requirement: Return column index mapping
The system SHALL return a mapping from column names to their sequential indices (starting from 1, excluding timestamp column).

#### Scenario: Map column names to indices
- **WHEN** a table has columns with names `ptag_int8_1`, `ptag_varchar_1`, `col_int8_1`
- **THEN** the system SHALL map `ptag_int8_1` → 1, `ptag_varchar_1` → 2, `col_int8_1` → 3
- **THEN** the indices SHALL be used for seed file naming as `{index}_{col_name}.{type}`