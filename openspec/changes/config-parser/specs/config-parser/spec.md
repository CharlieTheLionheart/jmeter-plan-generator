## ADDED Requirements

### Requirement: Table inheritance structure
The system SHALL use inheritance to distinguish between relational tables and time-series tables.

#### Scenario: RelTableConfig contains relational table fields only
- **WHEN** a relational table is defined in `rel_dbs`
- **THEN** the system SHALL parse it using `RelTableConfig` which inherits from `TableConfig`
- **AND** the table SHALL contain `primary_key_count` and `primary_keys` fields
- **AND** the table SHALL NOT contain `ts_col`, `primary_tags`, `regular_tags`, or `with_hash` fields

#### Scenario: TsTableConfig contains time-series table fields only
- **WHEN** a time-series table is defined in `ts_dbs`
- **THEN** the system SHALL parse it using `TsTableConfig` which inherits from `TableConfig`
- **AND** the table SHALL contain `ts_col`, `primary_tag_count`, `regular_tag_count`, `primary_tags`, `regular_tags`, `with_hash`, and `retentions` fields
- **AND** the table SHALL NOT contain `primary_key_count` or `primary_keys` fields

#### Scenario: TableConfig base class contains shared fields only
- **WHEN** `TableConfig` is used as a base class
- **THEN** it SHALL contain `name`, `comment`, `if_not_exists`, `data_col_count`, and `data_cols` fields
- **AND** it SHALL NOT contain table-type-specific fields

### Requirement: Database inheritance structure
The system SHALL use inheritance to distinguish between relational databases and time-series databases.

#### Scenario: RelDbConfig contains relational database
- **WHEN** a relational database is defined in `rel_dbs`
- **THEN** the system SHALL parse it using `RelDbConfig`
- **AND** its `tables` field SHALL be of type `list[RelTableConfig]`

#### Scenario: TsDbConfig contains time-series database
- **WHEN** a time-series database is defined in `ts_dbs`
- **THEN** the system SHALL parse it using `TsDbConfig`
- **AND** its `tables` field SHALL be of type `list[TsTableConfig]`
- **AND** it SHALL contain `retentions` and `partition_interval` fields

### Requirement: TsColConfig for time-series timestamp column
The system SHALL use a dedicated `TsColConfig` object for time-series table timestamp column configuration.

#### Scenario: Parse ts_col as TsColConfig object
- **WHEN** a time-series table has a `ts_col` field
- **THEN** the system SHALL parse it as a `TsColConfig` object
- **AND** the `TsColConfig` SHALL contain `name` (string), `type` (Literal["timestamp", "timestamptz"]), and `ms_step` (int) fields

### Requirement: WriteConfig mode values
The system SHALL support the correct set of write mode values.

#### Scenario: Accept valid write modes
- **WHEN** `write_config.mode` is set to one of `single_insert`, `batch_insert`, `single_prepared`, `batch_prepared`, or `schemaless`
- **THEN** the system SHALL accept the configuration

#### Scenario: Reject invalid write modes
- **WHEN** `write_config.mode` is set to `direct_insert` or `write_through`
- **THEN** the system SHALL report a validation error indicating invalid write mode

### Requirement: QueryConfig mode values
The system SHALL support the correct set of query mode values.

#### Scenario: Accept valid query modes
- **WHEN** `query_config.mode` is set to one of `statement` or `prepared_statement`
- **THEN** the system SHALL accept the configuration

#### Scenario: Reject invalid query modes
- **WHEN** `query_config.mode` is set to `query` or `raw`
- **THEN** the system SHALL report a validation error indicating invalid query mode

### Requirement: Parse test_model.yaml
The system SHALL parse the test_model.yaml configuration file and validate its structure and content.

#### Scenario: Successfully parse valid test_model.yaml
- **WHEN** a valid test_model.yaml file is provided
- **THEN** the system SHALL load and parse the file without errors
- **THEN** the system SHALL return a structured data model representing the configuration

#### Scenario: Detect missing mandatory fields
- **WHEN** test_model.yaml is missing mandatory fields (e.g., `name` in a database definition)
- **THEN** the system SHALL report a clear error message indicating which field is missing

#### Scenario: Detect invalid YAML syntax
- **WHEN** test_model.yaml contains invalid YAML syntax
- **THEN** the system SHALL report a YAML parsing error with file location information

### Requirement: Parse test_cfg.yaml
The system SHALL parse the test_cfg.yaml configuration file and validate its structure and content.

#### Scenario: Successfully parse valid test_cfg.yaml
- **WHEN** a valid test_cfg.yaml file is provided
- **THEN** the system SHALL load and parse the file without errors
- **THEN** the system SHALL return a structured data model representing the configuration

#### Scenario: Detect missing mandatory fields
- **WHEN** test_cfg.yaml is missing mandatory fields (e.g., `param_name` in conn_config)
- **THEN** the system SHALL report a clear error message indicating which field is missing

### Requirement: Validate type_proportion
The system SHALL validate that the sum of `type_proportion` values within each column group equals 1.0.

#### Scenario: Validate data_cols type_proportion
- **WHEN** a table's `data_cols` has multiple `col_type` entries with `type_proportion` values
- **THEN** the system SHALL verify that the sum of all `type_proportion` values equals 1.0
- **THEN** the system SHALL report an error if the sum deviates from 1.0

#### Scenario: Validate primary_keys type_proportion
- **WHEN** a table's `primary_keys` has multiple `col_type` entries with `type_proportion` values
- **THEN** the system SHALL verify that the sum of all `type_proportion` values equals 1.0
- **THEN** the system SHALL report an error if the sum deviates from 1.0

#### Scenario: Validate primary_tags type_proportion
- **WHEN** a table's `primary_tags` has multiple `col_type` entries with `type_proportion` values
- **THEN** the system SHALL verify that the sum of all `type_proportion` values equals 1.0
- **THEN** the system SHALL report an error if the sum deviates from 1.0

#### Scenario: Validate regular_tags type_proportion
- **WHEN** a table's `regular_tags` has multiple `col_type` entries with `type_proportion` values
- **THEN** the system SHALL verify that the sum of all `type_proportion` values equals 1.0
- **THEN** the system SHALL report an error if the sum deviates from 1.0

### Requirement: Validate nullable and null_rate
The system SHALL validate the relationship between `nullable` and `null_rate` fields.

#### Scenario: Reject nullable=true with null_rate > 0 when nullable is false
- **WHEN** a column has `nullable=false` but specifies `null_rate > 0.0`
- **THEN** the system SHALL report an error indicating that `nullable` must be `true` for `null_rate` to be non-zero

#### Scenario: Allow nullable=true with null_rate=0.0
- **WHEN** a column has `nullable=true` and `null_rate=0.0`
- **THEN** the system SHALL accept the configuration

#### Scenario: Calculate null count correctly
- **WHEN** a column has `seed_num=10`, `nullable=true`, and `null_rate=0.2`
- **THEN** the system SHALL calculate the number of null values as `round(10 × 0.2) = 2`

### Requirement: Validate primary_tags nullable constraint
The system SHALL reject any `nullable` field in `primary_tags` column configurations, as Primary Tags must always be NOT NULL in KaiwuDB.

#### Scenario: Reject nullable field in primary_tags
- **WHEN** a column in `primary_tags` contains a `nullable` field (regardless of value)
- **THEN** the system SHALL report a validation error indicating that `nullable` field is not permitted in Primary Tags
- **THEN** the error message SHALL clarify that Primary Tag columns are always NOT NULL

#### Scenario: Accept primary_tags without nullable field
- **WHEN** a column in `primary_tags` omits the `nullable` field
- **THEN** the system SHALL accept the configuration
- **THEN** the system SHALL parse the column configuration using the Primary Tag specific data model

#### Scenario: Data model structure enforces constraint
- **WHEN** the parser loads primary_tags configuration
- **THEN** the system SHALL use a dedicated `PrimaryTagColTypeConfig` model that does not include the `nullable` field
- **THEN** Pydantic SHALL automatically reject any configuration containing the `nullable` field with an "Extra fields are not permitted" error

### Requirement: Validate primary_tag_count constraint
The system SHALL enforce that the number of columns in `primary_tags` does not exceed 4.

#### Scenario: Reject primary_tag_count > 4
- **WHEN** a table's `primary_tag_count` exceeds 4
- **THEN** the system SHALL report an error indicating that Primary Tag count cannot exceed 4

#### Scenario: Accept primary_tag_count <= 4
- **WHEN** a table's `primary_tag_count` is 4 or less
- **THEN** the system SHALL accept the configuration

### Requirement: Validate Primary Tag data type constraints
The system SHALL validate that columns in `primary_tags` do not use unsupported data types.

#### Scenario: Reject float4 in primary_tags
- **WHEN** a column in `primary_tags` uses `col_type=float4`
- **THEN** the system SHALL report an error indicating that float4 is not allowed in Primary Tags

#### Scenario: Reject float8 in primary_tags
- **WHEN** a column in `primary_tags` uses `col_type=float8`
- **THEN** the system SHALL report an error indicating that float8 is not allowed in Primary Tags

#### Scenario: Reject nvarchar in primary_tags
- **WHEN** a column in `primary_tags` uses `col_type=nvarchar`
- **THEN** the system SHALL report an error indicating that nvarchar is not allowed in Primary Tags

#### Scenario: Reject varchar length > 128 in primary_tags
- **WHEN** a column in `primary_tags` uses `col_type=varchar(256)` (length > 128)
- **THEN** the system SHALL report an error indicating that varchar length cannot exceed 128 in Primary Tags

### Requirement: Validate Tag column data type constraints
The system SHALL validate that columns in `primary_tags` and `regular_tags` do not use unsupported data types.

#### Scenario: Reject timestamp in tags
- **WHEN** a column in `primary_tags` or `regular_tags` uses `col_type=timestamp`
- **THEN** the system SHALL report an error indicating that timestamp is not allowed in Tags

#### Scenario: Reject timestamptz in tags
- **WHEN** a column in `primary_tags` or `regular_tags` uses `col_type=timestamptz`
- **THEN** the system SHALL report an error indicating that timestamptz is not allowed in Tags

#### Scenario: Reject geometry in tags
- **WHEN** a column in `primary_tags` or `regular_tags` uses `col_type=geometry`
- **THEN** the system SHALL report an error indicating that geometry is not allowed in Tags

### Requirement: Parse val_range expressions
The system SHALL parse and validate `val_range` expressions for different data types.

#### Scenario: Parse numeric range with >= operator
- **WHEN** `val_range=">=1"` is provided for a numeric column
- **THEN** the system SHALL parse it as a lower bound constraint

#### Scenario: Parse numeric range with <= operator
- **WHEN** `val_range="<=100"` is provided for a numeric column
- **THEN** the system SHALL parse it as an upper bound constraint

#### Scenario: Parse numeric range with interval notation
- **WHEN** `val_range="[1,100]"` is provided for a numeric column
- **THEN** the system SHALL parse it as a closed interval from 1 to 100
- **THEN** the system SHALL parse `"(1,100)"` as an open interval from 1 to 100
- **THEN** the system SHALL parse `"[1,100)"` as a half-open interval from 1 (inclusive) to 100 (exclusive)

#### Scenario: Parse regex for string types
- **WHEN** `val_range="^[一-鿿a-zA-Z0-9-_]{2,10}$"` is provided for a varchar column
- **THEN** the system SHALL parse and validate the regex pattern

#### Scenario: Parse enum values
- **WHEN** `val_range="enum:M1,M2,M3"` is provided
- **THEN** the system SHALL extract the enum values as `["M1", "M2", "M3"]`
- **THEN** the system SHALL validate that enum values contain only allowed characters (digits, letters, Chinese characters, hyphens, underscores)

#### Scenario: Parse foreign key reference
- **WHEN** `val_range="ref:iot_metadata.t_workshop.pk_int8_1"` is provided
- **THEN** the system SHALL parse the reference format as `database.table.column`

### Requirement: Validate foreign key reference format
The system SHALL validate that foreign key references use the correct format.

#### Scenario: Reject malformed foreign key reference
- **WHEN** `val_range` starts with `ref:` but does not match `ref:库名.表名.列名` format
- **THEN** the system SHALL report an error indicating the correct format

#### Scenario: Accept valid foreign key reference
- **WHEN** `val_range="ref:iot_metadata.t_workshop.pk_int8_1"` is provided
- **THEN** the system SHALL accept the configuration

### Requirement: Validate integer range for integer types
The system SHALL validate that open intervals for integer types contain valid integer values.

#### Scenario: Detect empty integer range
- **WHEN** an integer column has `val_range="(1,2)"` (open interval with no valid integers)
- **THEN** the system SHALL report an error indicating that the interval contains no valid integer values

#### Scenario: Accept valid integer range
- **WHEN** an integer column has `val_range="[1,10]"` (closed interval)
- **THEN** the system SHALL accept the configuration

### Requirement: Validate write_config num_threads consistency
The system SHALL validate that when `write_config` has multiple entries for different tables, all entries have the same `num_threads` value.

#### Scenario: Reject inconsistent num_threads across tables
- **WHEN** `write_config` has one entry with `tbl_name="t_cnc", num_threads=20` and another with `tbl_name="t_motor", num_threads=10`
- **THEN** the system SHALL report an error indicating that all tables must have the same `num_threads` value

#### Scenario: Accept consistent num_threads across tables
- **WHEN** `write_config` has multiple entries with `tbl_name="t_cnc", num_threads=20` and `tbl_name="t_motor", num_threads=20`
- **THEN** the system SHALL accept the configuration

### Requirement: Validate query_config placeholder binding
The system SHALL validate that all `?` placeholders in query SQL can be bound to column seed caches.

#### Scenario: Reject unbindable placeholder
- **WHEN** a query contains `LIMIT ?` where the placeholder does not reference a specific column
- **THEN** the system SHALL report an error indicating that the placeholder cannot be bound to a column seed cache

#### Scenario: Accept column bindable placeholder
- **WHEN** a query contains `WHERE col_int8_1=?` where the column name matches a generated column
- **THEN** the system SHALL accept the configuration

### Requirement: Support table-level retentions override
The system SHALL support overriding database-level retentions at the table level for time-series tables.

#### Scenario: Parse table-level retentions
- **WHEN** a time-series table specifies `retentions` that differs from the database-level retentions
- **THEN** the system SHALL use the table-level retentions value

### Requirement: Parse WITH HASH parameter
The system SHALL parse the `with_hash` parameter for time-series tables.

#### Scenario: Validate with_hash range
- **WHEN** a time-series table has `with_hash=100` (within [1, 50000])
- **THEN** the system SHALL accept the configuration

#### Scenario: Reject out-of-range with_hash
- **WHEN** a time-series table has `with_hash=60000` (outside [1, 50000])
- **THEN** the system SHALL report an error indicating that `with_hash` must be between 1 and 50000