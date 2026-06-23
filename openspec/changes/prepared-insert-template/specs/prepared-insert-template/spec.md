## ADDED Requirements

### Requirement: Generate Prepared Insert templates
The system SHALL generate INSERT statement templates with `?` placeholders for PreparedStatement execution.

#### Scenario: Generate template for time-series table
- **WHEN** generating template for table `iot_monitor.t_cnc` with columns `ts, ptag_int8_1, ptag_varchar_1, col_int8_1`
- **THEN** the system SHALL generate `INSERT INTO iot_monitor.t_cnc (ts, ptag_int8_1, ptag_varchar_1, col_int8_1) VALUES (?, ?, ?, ?)`
- **THEN** the column order SHALL match the CREATE TABLE field order

#### Scenario: Generate template excluding relational tables
- **WHEN** generating templates for all tables including relational tables
- **THEN** the system SHALL only generate templates for time-series tables
- **THEN** relational tables SHALL be excluded

### Requirement: Conditionally generate templates
The system SHALL only generate Prepared Insert templates when required by write configuration.

#### Scenario: Generate templates when single_prepared exists
- **WHEN** `write_config` contains at least one entry with `mode="single_prepared"`
- **THEN** the system SHALL generate Prepared Insert templates
- **THEN** the system SHALL instantiate `PreparedInsertTemplateGenerator`

#### Scenario: Generate templates when batch_prepared exists
- **WHEN** `write_config` contains at least one entry with `mode="batch_prepared"`
- **THEN** the system SHALL generate Prepared Insert templates
- **THEN** the system SHALL instantiate `PreparedInsertTemplateGenerator`

#### Scenario: Skip generation when no prepared modes exist
- **WHEN** `write_config` contains only `single_insert` or `batch_insert` modes
- **THEN** the system SHALL skip template generation
- **THEN** `PreparedInsertTemplateGenerator` SHALL NOT be instantiated

### Requirement: Index templates by fully qualified name
The system SHALL return templates indexed by fully qualified table name (`db.table`).

#### Scenario: Return dictionary with FQN keys
- **WHEN** generating templates for tables in databases `iot_metadata` and `iot_monitor`
- **THEN** the system SHALL return a dictionary with keys like `iot_metadata.t_workshop` and `iot_monitor.t_cnc`
- **THEN** write strategies SHALL look up templates by FQN

### Requirement: Check for template requirements
The system SHALL provide a method to check if Prepared Insert templates are required.

#### Scenario: Return True when prepared modes exist
- **WHEN** any table in `write_config` uses `single_prepared` or `batch_prepared`
- **THEN** `requires_prepared_insert_templates()` SHALL return `True`

#### Scenario: Return False when no prepared modes exist
- **WHEN** no table in `write_config` uses `single_prepared` or `batch_prepared`
- **THEN** `requires_prepared_insert_templates()` SHALL return `False`