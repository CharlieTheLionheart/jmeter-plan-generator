## ADDED Requirements

### Requirement: Generate JDBCDataSource element
The system SHALL generate a JDBCDataSource element in the JMeter test plan.

#### Scenario: Generate JDBCDataSource with basic configuration
- **WHEN** generating the test plan
- **THEN** the system SHALL generate a `<JDBCDataSource>` element
- **THEN** the element SHALL have `testclass="JDBCDataSource"` and `guiclass="TestBeanGUI"`
- **THEN** the element SHALL be a child of the `<TestPlan>` element

#### Scenario: Set dataSource name
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `dataSource="jdbcConfig"`
- **THEN** all JDBCSampler SHALL reference this dataSource name

#### Scenario: Set auto-commit mode
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `autocommit="true"` for DDL execution

### Requirement: Configure database connection parameters
The system SHALL configure database connection parameters using JMeter variables.

#### Scenario: Set database URL
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `dbUrl="${db_url}"`
- **THEN** the `${db_url}` variable SHALL be defined in User Defined Variables

#### Scenario: Set username and password
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `username="${db_username}"`
- **THEN** the system SHALL set `password="${db_password}"`
- **THEN** the `${db_username}` and `${db_password}` variables SHALL be defined in User Defined Variables

#### Scenario: Set JDBC driver
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `driver="com.kaiwudb.Driver"`

### Requirement: Configure connection pool
The system SHALL configure connection pool parameters.

#### Scenario: Set maximum pool size
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `poolMax="${conn_pool_size}"`
- **THEN** the `${conn_pool_size}` variable SHALL be defined in User Defined Variables

#### Scenario: Set connection keep-alive
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `keepAlive="true"`

#### Scenario: Set connection age
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `connectionAge="5000"`

#### Scenario: Set connection timeout
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `timeout="10000"`

#### Scenario: Set trim interval
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `trimInterval="60000"`

#### Scenario: Set transaction isolation
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `transactionIsolation="DEFAULT"`

#### Scenario: Leave checkQuery empty
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL set `checkQuery` as an empty string

### Requirement: Position JDBCDataSource correctly
The system SHALL position the JDBCDataSource element in the correct location in the JMX.

#### Scenario: Place after User Defined Variables
- **WHEN** generating the test plan
- **THEN** the JDBCDataSource SHALL appear after the `<Arguments>` (User Defined Variables) element
- **THEN** the JDBCDataSource SHALL appear before all thread groups

#### Scenario: Generate hashTree for JDBCDataSource
- **WHEN** generating the JDBCDataSource
- **THEN** the system SHALL generate an empty `<hashTree/>` as a child element