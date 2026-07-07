## ADDED Requirements

### Requirement: Define WriteStrategy abstract base class
The system SHALL define an abstract base class for write strategies.

#### Scenario: Define abstract methods
- **WHEN** defining `WriteStrategy` base class
- **THEN** it SHALL have abstract method `mode_name` property
- **THEN** it SHALL have abstract method `requires_prepared_insert_template()`
- **THEN** it SHALL have abstract method `generate_query()`
- **THEN** it SHALL have abstract method `get_sampler_type()`
- **THEN** it SHALL have abstract method `get_sampler_config()`
- **THEN** it SHALL have abstract method `requires_param_setup()`
- **THEN** it SHALL have abstract method `get_preprocessor_code()`
- **THEN** it SHALL have abstract method `get_sampler_script()`

### Requirement: Register strategies in registry
The system SHALL maintain a registry mapping write modes to strategy classes.

#### Scenario: Register all built-in strategies
- **WHEN** the module is initialized
- **THEN** `STRATEGY_REGISTRY` SHALL map `"single_insert"` → `SingleInsertStrategy`
- **THEN** `STRATEGY_REGISTRY` SHALL map `"batch_insert"` → `BatchInsertStrategy`
- **THEN** `STRATEGY_REGISTRY` SHALL map `"single_prepared"` → `SinglePreparedStatementStrategy`
- **THEN** `STRATEGY_REGISTRY` SHALL map `"batch_prepared"` → `BatchPreparedStatementStrategy`
- **THEN** `STRATEGY_REGISTRY` SHALL map `"schemaless"` → `SchemalessWriteStrategy`

#### Scenario: Retrieve strategy by mode
- **WHEN** calling `get_strategy("single_insert")`
- **THEN** the system SHALL return an instance of `SingleInsertStrategy`

### Requirement: Implement SingleInsertStrategy
The system SHALL implement a strategy for single INSERT write operations.

#### Scenario: Configure for single INSERT
- **WHEN** creating `SingleInsertStrategy`
- **THEN** `mode_name` SHALL return `"single_insert"`
- **THEN** `requires_prepared_insert_template()` SHALL return `False`
- **THEN** `get_sampler_type()` SHALL return `"JDBCSampler"`
- **THEN** `get_sampler_config()` SHALL return `{"usePrepared": False}`
- **THEN** `requires_param_setup()` SHALL return `True`
- **THEN** `get_sampler_script()` SHALL return `None`

### Requirement: Implement BatchInsertStrategy
The system SHALL implement a strategy for batch INSERT write operations.

#### Scenario: Configure for batch INSERT
- **WHEN** creating `BatchInsertStrategy`
- **THEN** `mode_name` SHALL return `"batch_insert"`
- **THEN** `requires_prepared_insert_template()` SHALL return `False`
- **THEN** `get_sampler_type()` SHALL return `"JDBCSampler"`
- **THEN** `get_sampler_config()` SHALL return `{"usePrepared": False}`
- **THEN** `requires_param_setup()` SHALL return `True`
- **THEN** `get_sampler_script()` SHALL return `None`

### Requirement: Implement SinglePreparedStatementStrategy
The system SHALL implement a strategy for single PreparedStatement write operations.

#### Scenario: Configure for single PreparedStatement
- **WHEN** creating `SinglePreparedStatementStrategy`
- **THEN** `mode_name` SHALL return `"single_prepared"`
- **THEN** `requires_prepared_insert_template()` SHALL return `True`
- **THEN** `generate_query()` SHALL return the prepared insert template
- **THEN** `get_sampler_type()` SHALL return `"JDBCSampler"`
- **THEN** `get_sampler_config()` SHALL return `{"usePrepared": True}`
- **THEN** `requires_param_setup()` SHALL return `True`
- **THEN** `get_sampler_script()` SHALL return `None`

### Requirement: Implement BatchPreparedStatementStrategy
The system SHALL implement a strategy for batch PreparedStatement write operations using JSR223Sampler.

#### Scenario: Configure for batch PreparedStatement
- **WHEN** creating `BatchPreparedStatementStrategy`
- **THEN** `mode_name` SHALL return `"batch_prepared"`
- **THEN** `requires_prepared_insert_template()` SHALL return `True`
- **THEN** `generate_query()` SHALL return the prepared insert template
- **THEN** `get_sampler_type()` SHALL return `"JSR223Sampler"`
- **THEN** `get_sampler_config()` SHALL return `{"scriptLanguage": "groovy"}`
- **THEN** `requires_param_setup()` SHALL return `True`
- **THEN** `get_sampler_script()` SHALL return Groovy batch execution code

### Requirement: Implement SchemalessWriteStrategy (deferred)
> **Note**: Schemaless write mode (T2) is deferred. The `SchemalessWriteStrategy` class exists as a placeholder skeleton but is not functional. If `schemaless` mode is configured in `test_cfg.yaml`, the generator SHALL reject it during validation with an error message indicating the feature is not yet implemented. A future DCR will drive the full design and implementation of this feature.

### Requirement: Refactor direct-insert-write to use strategies
The system SHALL refactor existing direct INSERT logic to use the strategy pattern.

#### Scenario: Replace direct INSERT generation with strategy calls
- **WHEN** generating write samplers for `single_insert` mode
- **THEN** the system SHALL use `SingleInsertStrategy`
- **THEN** the system SHALL call `generate_query()`, `get_sampler_type()`, `get_sampler_config()`
- **WHEN** generating write samplers for `batch_insert` mode
- **THEN** the system SHALL use `BatchInsertStrategy`
- **THEN** the system SHALL call `generate_query()`, `get_sampler_type()`, `get_sampler_config()`

## MODIFIED Requirements

### Requirement: Direct INSERT write functionality
The implementation of `single_insert` and `batch_insert` modes SHALL be refactored to use the `SingleInsertStrategy` and `BatchInsertStrategy` classes respectively.

**Reason**: Migrate to strategy pattern for extensibility and consistency with prepared statement implementations.

**Migration**:
- Extract SQL generation logic from `direct_insert_write` module into `SingleInsertStrategy.generate_query()` and `BatchInsertStrategy.generate_query()`
- Extract JDBCSampler configuration into `get_sampler_config()`
- Extract JSR223PreProcessor code generation into `get_preprocessor_code()`