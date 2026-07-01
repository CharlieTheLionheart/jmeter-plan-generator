## 1. CLI Argument Parsing

- [ ] 1.1 Create `src/kwjdbc_svt/main.py` with `parse_args(argv=None)` using `argparse`
- [ ] 1.2 Accept two positional arguments: `test_model.yaml` and `test_cfg.yaml`
- [ ] 1.3 Add `-o/--output-dir` optional flag defaulting to current working directory
- [ ] 1.4 Add `-v/--verbose` flag supporting `-v` (INFO) and `-vv` (DEBUG)
- [ ] 1.5 Return parsed arguments object from `parse_args()` for unit testing

## 2. Logging Setup

- [ ] 2.1 Implement `setup_logging(verbose_level)` to configure root logger
- [ ] 2.2 Default level `WARNING`; `-v` → `INFO`; `-vv` → `DEBUG`
- [ ] 2.3 Use a consistent log format with timestamp, level, and message
- [ ] 2.4 Ensure logging is configured once before pipeline execution

## 3. Configuration Parsing and Validation

- [ ] 3.1 Implement `load_configs(args)` to call `ModelParser.parse()` and `TestParser.parse()`
- [ ] 3.2 Validate input files exist before parsing; map missing file errors to exit code `1`
- [ ] 3.3 Catch `ValidationError` from either parser, log all collected errors, return exit code `1`
- [ ] 3.4 Handle empty or null YAML root as validation failure with exit code `1`

## 4. Pipeline Orchestration

- [ ] 4.1 Instantiate `ColumnNamer(model_config)` and produce column name lists
- [ ] 4.2 Call `SeedGenerator(model_config, column_names)` to write seeds under `seeds/{database_name}/{table_name}/`
- [ ] 4.3 Call `DDLGenerator(model_config, column_names)` to produce DDL statements
- [ ] 4.4 Check `test_config.write_config` tables for `single_prepared` or `batch_prepared` modes
- [ ] 4.5 If any table uses prepared mode, invoke `PreparedInsertTemplateGenerator(model_config, column_names)`
- [ ] 4.6 Invoke `JmxBuilder` with model config, test config, column names, seed paths, DDL, and prepared templates
- [ ] 4.7 Ensure module call order matches design.md §2.3 pipeline sequence

## 5. Error Handling and Exit Codes

- [ ] 5.1 Map `ValidationError` → exit code `1`
- [ ] 5.2 Map `SeedGenerationError` → exit code `2`; preserve already-written seed files
- [ ] 5.3 Map `DdlGenerationError` → exit code `3`
- [ ] 5.4 Map `JmxGenerationError` → exit code `4`
- [ ] 5.5 Map unexpected exceptions → exit code `5`; log traceback when log level is `DEBUG`
- [ ] 5.6 Ensure `main()` returns integer exit codes and does not call `sys.exit()` directly

## 6. Output Artifact Generation

- [ ] 6.1 Write final JMX file to `{output_dir}/{test_plan_name}.jmx` (default `test_plan.jmx`)
- [ ] 6.2 Create `seeds/{database_name}/{table_name}/` subdirectories in output directory
- [ ] 6.3 Overwrite existing files by default and log a `WARNING` before overwriting
- [ ] 6.4 Create output directory (including parents) if it does not exist
- [ ] 6.5 Handle write-permission errors by propagating as exit code `5`

## 7. Module Entry Point

- [ ] 7.1 Add `if __name__ == "__main__":` block calling `sys.exit(main())`
- [ ] 7.2 Support `python -m kwjdbc_svt.main test_model.yaml test_cfg.yaml`
- [ ] 7.3 Ensure programmatic `main()` invocation returns exit code without raising `SystemExit`

## 8. Unit Tests

- [ ] 8.1 Test `parse_args()` with valid positional arguments and flags
- [ ] 8.2 Test `parse_args()` fails when positional arguments are missing
- [ ] 8.3 Test `setup_logging()` maps `-v`/`-vv`/default to correct log levels
- [ ] 8.4 Test `main()` returns exit code `1` on `ValidationError`
- [ ] 8.5 Test `main()` returns exit code `2` on `SeedGenerationError`
- [ ] 8.6 Test `main()` returns exit code `3` on `DdlGenerationError`
- [ ] 8.7 Test `main()` returns exit code `4` on `JmxGenerationError`
- [ ] 8.8 Test `main()` returns exit code `5` on unexpected exceptions
- [ ] 8.9 Test prepared template generator is skipped when no prepared modes are configured

## 9. E2E Tests

- [ ] 9.1 Add an E2E test invoking the CLI with sample `test_model.yaml` and `test_cfg.yaml`
- [ ] 9.2 Assert output directory contains `test_plan.jmx` and `seeds/` directory
- [ ] 9.3 Assert generated `.jmx` is valid XML parseable by `xml.etree.ElementTree.parse()`
- [ ] 9.4 Assert seed files are written under `seeds/{database_name}/{table_name}/` with expected naming pattern
- [ ] 9.5 Assert overwrite scenario emits a `WARNING` log before replacing existing files
