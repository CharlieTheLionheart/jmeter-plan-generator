## ADDED Requirements

### Requirement: Generate relational database DDL
The system SHALL generate DDL statements for relational databases based on the configuration.

#### Scenario: Generate CREATE DATABASE statement
- **WHEN** a relational database configuration has `name="iot_metadata"` and `if_not_exists=true`
- **THEN** the system SHALL generate `create database if not exists iot_metadata;`

#### Scenario: Generate CREATE DATABASE with encoding
- **WHEN** a relational database configuration has `with_encoding="utf-8"`
- **THEN** the system SHALL generate `create database iot_metadata with encoding 'utf-8';`

#### Scenario: Generate CREATE DATABASE with comment
- **WHEN** a relational database configuration has `comment="工业互联网元数据库"`
- **THEN** the system SHALL generate `create database iot_metadata comment '工业互联网元数据库';`

#### Scenario: Generate CREATE TABLE for relational table
- **WHEN** a relational table in database `iot_metadata` has primary keys and data columns
- **THEN** the system SHALL generate `create table iot_metadata.table_name (col1 int not null, col2 varchar(16), primary key (col1));`

#### Scenario: Generate CREATE TABLE with IF NOT EXISTS
- **WHEN** a relational table in database `iot_metadata` has `if_not_exists=true`
- **THEN** the system SHALL generate `create table if not exists iot_metadata.table_name (...);`

#### Scenario: Generate CREATE TABLE with comment
- **WHEN** a relational table in database `iot_metadata` has `comment="车间表"`
- **THEN** the system SHALL generate `create table iot_metadata.table_name (...) comment '车间表';`

### Requirement: Generate time-series database DDL
The system SHALL generate DDL statements for time-series databases based on the configuration.

#### Scenario: Generate CREATE DATABASE for time-series
- **WHEN** a time-series database configuration has `name="iot_monitor"`
- **THEN** the system SHALL generate `create ts database iot_monitor;`

#### Scenario: Generate CREATE DATABASE with retentions
- **WHEN** a time-series database configuration has `retentions="3d"`
- **THEN** the system SHALL generate `create ts database iot_monitor retentions 3d;`

#### Scenario: Generate CREATE DATABASE with partition interval
- **WHEN** a time-series database configuration has `partition_interval="1d"`
- **THEN** the system SHALL generate `create ts database iot_monitor partition interval 1d;`

#### Scenario: Generate time-series CREATE DATABASE with comment
- **WHEN** a time-series database configuration has `comment="工业互联网时序监控数据数据库"`
- **THEN** the system SHALL generate `create ts database iot_monitor comment '工业互联网时序监控数据数据库';`

#### Scenario: Generate CREATE TABLE for time-series table
- **WHEN** a time-series table in database `iot_monitor` has timestamp column, primary tags, regular tags, and data columns
- **THEN** the system SHALL generate `create table iot_monitor.table_name (ts timestamp not null, ptag1 int not null, rtag1 varchar(10), col1 int) tags (ptag1 int not null, rtag1 varchar(10)) primary tags (ptag1);`

#### Scenario: Generate CREATE TABLE with table-level retentions
- **WHEN** a time-series table in database `iot_monitor` has `retentions="5d"` (overriding database-level)
- **THEN** the system SHALL generate `create table iot_monitor.table_name (...) with retentions '5d';`

#### Scenario: Generate CREATE TABLE with WITH HASH
- **WHEN** a time-series table in database `iot_monitor` has `with_hash=100`
- **THEN** the system SHALL generate `create table iot_monitor.table_name (...) with hash(100);`

#### Scenario: Generate time-series CREATE TABLE with comment
- **WHEN** a time-series table in database `iot_monitor` has `comment="数控机床表"`
- **THEN** the system SHALL generate `create table iot_monitor.table_name (...) comment '数控机床表';`

### Requirement: Use qualified table names
The system SHALL use qualified table names (database.table_name) in all generated DDL statements and throughout the test plan.

#### Scenario: Use qualified name in CREATE TABLE
- **WHEN** generating a CREATE TABLE statement for table `t_workshop` in database `iot_metadata`
- **THEN** the system SHALL use the qualified name `iot_metadata.t_workshop`
- **THEN** the system SHALL NOT generate a non-qualified name `t_workshop`

#### Scenario: Use qualified name in time-series table
- **WHEN** generating a CREATE TABLE statement for table `t_cnc` in database `iot_monitor`
- **THEN** the system SHALL use the qualified name `iot_monitor.t_cnc`

#### Scenario: Support multi-database DDL execution
- **WHEN** executing multiple CREATE TABLE statements from different databases in one batch
- **THEN** the system SHALL use qualified names to avoid database context ambiguity
- **THEN** the generated DDL shall be executable without intermediate `use database` statements

### Requirement: Support multi-statement execution
The system SHALL support executing multiple DDL statements in a single batch separated by semicolons.

#### Scenario: Execute CREATE DATABASE and CREATE TABLE together
- **WHEN** creating a database and its tables in one execution
- **THEN** the system SHALL generate statements separated by semicolons
- **THEN** KaiwuDB shall support executing `create database db_name; create table db_name.table_name (...)` in one call

#### Scenario: Output semicolon-separated SQL script
- **WHEN** all DDL statements are generated
- **THEN** the system SHALL output them as an executable SQL script with semicolons separating statements

### Requirement: Generate column names
The system SHALL generate column names using the pattern `{type_prefix}_{data_type}_{sequence}`.

#### Scenario: Generate primary key column names
- **WHEN** generating column names for `primary_keys` with `col_type=int8`
- **THEN** the system SHALL generate `pk_int8_1`

#### Scenario: Generate data column names
- **WHEN** generating column names for `data_cols` with `col_type=varchar(16)`
- **THEN** the system SHALL generate `col_varchar_1`

#### Scenario: Generate primary tag column names
- **WHEN** generating column names for `primary_tags` with `col_type=int8`
- **THEN** the system SHALL generate `ptag_int8_1`

#### Scenario: Generate regular tag column names
- **WHEN** generating column names for `regular_tags` with `col_type=varchar(10)`
- **THEN** the system SHALL generate `rtag_varchar_1`

#### Scenario: Generate sequential column names
- **WHEN** generating multiple columns of the same type
- **THEN** the system SHALL generate names with incrementing sequence numbers (e.g., `col_int8_1`, `col_int8_2`, `col_int8_3`)

### Requirement: Generate NOT NULL constraints
The system SHALL generate `not null` constraints based on the `nullable` configuration.

#### Scenario: Generate NOT NULL for nullable=false
- **WHEN** a column has `nullable=false`
- **THEN** the system SHALL generate the column definition with `not null`

#### Scenario: Omit NOT NULL for nullable=true
- **WHEN** a column has `nullable=true`
- **THEN** the system SHALL generate the column definition without `not null`

#### Scenario: Omit NOT NULL for nullable omitted
- **WHEN** a column does not specify `nullable` (default is false)
- **THEN** the system SHALL generate the column definition with `not null`

### Requirement: Handle KaiwuDB data type syntax
The system SHALL output KaiwuDB-compatible data type syntax in DDL statements.

#### Scenario: Output int8 data type
- **WHEN** a column has `col_type=int8`
- **THEN** the system SHALL generate the column definition with data type `int8`

#### Scenario: Output varchar with length
- **WHEN** a column has `col_type=varchar(16)`
- **THEN** the system SHALL generate the column definition with data type `varchar(16)`

#### Scenario: Output timestamptz data type
- **WHEN** a timestamp column has `type=timestamptz`
- **THEN** the system SHALL generate the column definition with data type `timestamptz`

### Requirement: Organize DDL by database and table
The system SHALL organize generated DDL statements by database and table for structured output.

#### Scenario: Group DDL by database
- **WHEN** generating DDL for multiple databases
- **THEN** the system SHALL group statements by database name

#### Scenario: Group DDL by table within database
- **WHEN** generating DDL for multiple tables within a database
- **THEN** the system SHALL group statements by table name within each database

#### Scenario: Output DDL as executable SQL script
- **WHEN** all DDL statements are generated
- **THEN** the system SHALL output them as an executable SQL script with semicolons separating statements