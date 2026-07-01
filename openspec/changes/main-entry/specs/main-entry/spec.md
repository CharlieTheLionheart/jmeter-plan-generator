## ADDED Requirements

### Requirement: Parse CLI arguments
The system SHALL provide a command-line interface that accepts the required input files and optional flags.

#### Scenario: Parse two positional YAML arguments
- **WHEN** the user invokes `python -m kwjdbc_svt.main test_model.yaml test_cfg.yaml`
- **THEN** the system SHALL accept both file paths as positional arguments
- **THEN** the system SHALL fail with exit code `1` if either file is missing

#### Scenario: Specify output directory
- **WHEN** the user invokes `python -m kwjdbc_svt.main test_model.yaml test_cfg.yaml -o ./output`
- **THEN** the system SHALL use `./output` as the destination for generated artifacts
- **THEN** the system SHALL create the directory if it does not exist

#### Scenario: Default output directory is the current working directory
- **WHEN** the user invokes `python -m kwjdbc_svt.main test_model.yaml test_cfg.yaml` without `-o`
- **THEN** the system SHALL use the current working directory as the output directory

#### Scenario: Control log verbosity
- **WHEN** the user provides `-v`
- **THEN** the system SHALL set the log level to `INFO`
- **WHEN** the user provides `-vv`
- **THEN** the system SHALL set the log level to `DEBUG`
- **WHEN** the user provides neither flag
- **THEN** the system SHALL use the default log level `WARNING`

### Requirement: Orchestrate module pipeline
The system SHALL invoke the generator modules in the correct order and pass data between them.

#### Scenario: Parse both configuration files first
- **WHEN** the CLI is invoked with valid YAML files
- **THEN** the system SHALL call `ModelParser` on `test_model.yaml`
- **THEN** the system SHALL call `TestParser` on `test_cfg.yaml`
- **THEN** the system SHALL use the parsed configurations in downstream modules

#### Scenario: Generate column names before seed and DDL generation
- **WHEN** both configurations are parsed successfully
- **THEN** the system SHALL instantiate `ColumnNamer` with `ModelConfig`
- **THEN** the system SHALL pass the resulting column name lists to `SeedGenerator`, `DDLGenerator`, `PreparedInsertTemplateGenerator` (when applicable), and `WriteSamplerGenerator` via `JmxBuilder`

#### Scenario: Generate seed files and DDL statements
- **WHEN** column names are available
- **THEN** the system SHALL call `SeedGenerator` to write seed files under `seeds/{database_name}/{table_name}/`
- **THEN** the system SHALL call `DDLGenerator` to produce DDL statements

#### Scenario: Conditionally generate prepared insert templates
- **WHEN** `write_config` contains at least one table with `mode` equal to `single_prepared` or `batch_prepared`
- **THEN** the system SHALL invoke `PreparedInsertTemplateGenerator`
- **THEN** the system SHALL pass the generated templates to `JmxBuilder`
- **WHEN** no table uses a prepared statement mode
- **THEN** the system SHALL skip `PreparedInsertTemplateGenerator`

#### Scenario: Build final JMX file
- **WHEN** all upstream artifacts are generated
- **THEN** the system SHALL invoke `JmxBuilder` with `ModelConfig`, `TestConfig`, column names, seed paths, DDL statements, and prepared insert templates (if any)
- **THEN** the system SHALL write the resulting JMX document to the output directory

### Requirement: Handle errors with defined exit codes
The system SHALL map each failure category to a specific exit code and report a clear error message.

#### Scenario: Configuration validation fails
- **WHEN** `ModelParser` or `TestParser` raises `ValidationError`
- **THEN** the system SHALL log all collected validation errors
- **THEN** the system SHALL exit with code `1`

#### Scenario: Seed generation fails
- **WHEN** `SeedGenerator` raises `SeedGenerationError`
- **THEN** the system SHALL log the error
- **THEN** the system SHALL preserve any seed files already written
- **THEN** the system SHALL exit with code `2`

#### Scenario: DDL generation fails
- **WHEN** `DDLGenerator` raises `DdlGenerationError`
- **THEN** the system SHALL log the error
- **THEN** the system SHALL exit with code `3`

#### Scenario: JMX generation fails
- **WHEN** `JmxBuilder` raises `JmxGenerationError`
- **THEN** the system SHALL log the error
- **THEN** the system SHALL exit with code `4`

#### Scenario: Unexpected error occurs
- **WHEN** an unhandled exception is raised
- **THEN** the system SHALL log the traceback when log level is `DEBUG`
- **THEN** the system SHALL exit with code `5`

### Requirement: Generate output artifacts
The system SHALL write the final `.jmx` file and seed files to the configured output directory.

#### Scenario: Output JMX file lands in output directory
- **WHEN** the pipeline completes successfully
- **THEN** the system SHALL write `test_plan.jmx` (or the configured name) to the output directory
- **THEN** the file SHALL be valid XML readable by JMeter 5.5+

#### Scenario: Output seed directory structure
- **WHEN** the pipeline completes successfully
- **THEN** the system SHALL create `seeds/{database_name}/{table_name}/` subdirectories in the output directory
- **THEN** each subdirectory SHALL contain the column seed files generated for that table

#### Scenario: Overwrite existing output files
- **WHEN** the output directory already contains `test_plan.jmx` or `seeds/` entries
- **THEN** the system SHALL overwrite them by default
- **THEN** the system SHALL log a `WARNING` before overwriting

### Requirement: Support E2E invocation
The system SHALL expose a `main()` entry point that can be invoked programmatically and from the CLI.

#### Scenario: Programmatic invocation returns exit code
- **WHEN** `main()` is called from Python code
- **THEN** it SHALL return an integer exit code
- **THEN** it SHALL not call `sys.exit()` directly

#### Scenario: CLI module execution works
- **WHEN** `python -m kwjdbc_svt.main` is executed
- **THEN** it SHALL parse arguments and invoke `main()`
- **THEN** it SHALL propagate the returned exit code to the shell
