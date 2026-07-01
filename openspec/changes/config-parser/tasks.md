# Tasks: config-parser

## 1. Project Setup & Dependencies

- [x] 1.1 Add `pyyaml` and `pydantic` to project dependency manifest (`requirements.txt` / `pyproject.toml`).
- [x] 1.2 Create `src/config_parser/__init__.py` and empty `src/config_parser/models.py`.
- [x] 1.3 Verify `utils/val_range_parser.py` exists and its parse API is stable for reuse.

## 2. Pydantic Data Models

- [x] 2.1 Implement `ColTypeConfig` model with fields: `col_type`, `type_proportion`, `val_range`, `seed_num`, `nullable`, `null_rate`.
- [x] 2.2 Implement `PrimaryTagColTypeConfig` model (no `nullable` field) with fields: `col_type`, `type_proportion`, `val_range`.
- [x] 2.3 Implement `TableConfig` model with fields: `name`, `comment`, `if_not_exists`, `with_hash`, `ts_col`, `primary_key_count`, `data_col_count`, `primary_tag_count`, `regular_tag_count`, `primary_keys`, `data_cols`, `primary_tags`, `regular_tags`, `retentions`.
- [x] 2.4 Implement `DatabaseConfig` model with fields: `name`, `if_not_exists`, `with_encoding`, `comment`, `retentions`, `partition_interval`, `tables`.
- [x] 2.5 Implement `TestModelConfig` model with fields: `rel_dbs`, `ts_dbs`.
- [x] 2.6 Implement `ConnConfig`, `WriteConfig`, `QueryConfig`, and `TestConfig` models for `test_cfg.yaml`.

## 3. YAML Loading & Structural Parsing

- [x] 3.1 Implement `load_yaml(path)` helper that wraps PyYAML and raises a clear error with file location on syntax failure.
- [x] 3.2 Implement `parse_test_model_yaml(path) -> TestModelConfig`.
- [x] 3.3 Implement `parse_test_cfg_yaml(path) -> TestConfig`.
- [x] 3.4 Add tests for valid/missing-mandatory-field/invalid-YAML scenarios for both files.

## 4. type_proportion Validation

- [x] 4.1 Add model/root validator ensuring `type_proportion` sums to `1.0` within a small epsilon for `primary_keys`, `data_cols`, `primary_tags`, `regular_tags`.
- [x] 4.2 Add positive tests for each column group summing to 1.0 (including `0.1 + 0.2`-style floating point cases).
- [x] 4.3 Add negative tests for sums deviating from 1.0.

## 5. nullable / null_rate Validation

- [x] 5.1 Add validator rejecting `nullable=false` with `null_rate > 0`.
- [x] 5.2 Add validator ensuring `null_rate` is in `[0.0, 1.0]`.
- [x] 5.3 Add validator confirming `min(seed_num, floor(seed_num * null_rate))` behavior is documented/tested for `seed_num=10, null_rate=0.2 -> 2`.
- [x] 5.4 Add negative tests for `null_rate < 0`, `null_rate > 1`, and `nullable=false` with non-zero `null_rate`.

## 6. Primary Tag Constraints

- [x] 6.1 Confirm `PrimaryTagColTypeConfig` rejects any `nullable` field via Pydantic `extra='forbid'`.
- [x] 6.2 Add validator enforcing `primary_tag_count >= 0` and `primary_tag_count <= 4`.
- [x] 6.3 Add validator rejecting `float4`, `float8`, and `nvarchar` in `primary_tags`.
- [x] 6.4 Add validator rejecting `varchar(N)` where `N > 128` in `primary_tags`.
- [x] 6.5 Add positive/negative tests for all primary tag constraints.

## 7. Tag Column Data Type Constraints

- [x] 7.1 Add validator rejecting `timestamp`, `timestamptz`, and `geometry` in `primary_tags` and `regular_tags`.
- [x] 7.2 Add positive/negative tests for tag type restrictions.

## 8. val_range Parsing & Validation

- [x] 8.1 Integrate `utils/val_range_parser.py` to parse `val_range` strings.
- [x] 8.2 Add validator for foreign-key references (`ref:db.table.column`) rejecting malformed formats.
- [x] 8.3 Add validator detecting empty integer open intervals such as `(1,2)`.
- [x] 8.4 Add validators for interval edge cases: reverse order `[10,1]`, single-value `[5,5]`, and invalid parse failures (bad regex, empty enum).
- [x] 8.5 Add positive/negative tests for numeric ranges, regex, enum, foreign key, and integer intervals.

## 9. Cross-Table Foreign Key Validation

- [x] 9.1 Implement cross-table check ensuring every `ref:` target (`db.table.column`) exists in the parsed model.
- [x] 9.2 Decide and document whether foreign-key cycle detection is in scope for this change; if yes, implement a cycle detector.
- [x] 9.3 Add tests for valid references, missing target column, and (if implemented) circular references.

## 10. test_cfg.yaml Business Rules

- [x] 10.1 Add validator ensuring all `write_config` entries share the same `num_threads` value.
- [x] 10.2 Add validator ensuring every `?` placeholder in `query_config.query` can be bound to a known generated column.
- [x] 10.3 Add tests for consistent/inconsistent `num_threads` and bindable/unbindable query placeholders.

## 11. Time-Series Specific Parsing

- [x] 11.1 Implement table-level `retentions` override for time-series tables.
- [x] 11.2 Add validator ensuring `with_hash` is in `[1, 50000]` for time-series tables.
- [x] 11.3 Add tests for retentions override and `with_hash` boundary values.

## 12. Error Reporting & Integration

- [x] 12.1 Define a single `ConfigParserError` exception class wrapping Pydantic and business-rule errors with clear messages.
- [x] 12.2 Ensure parser fails fast and does not return partial configuration on error.
- [x] 12.3 Add end-to-end tests using representative `test_model.yaml` and `test_cfg.yaml` samples.

## 13. Code Review & Documentation

- [x] 13.1 Run the full unit-test suite and fix any failures.
- [x] 13.2 Address any findings from self-review or peer review.
- [x] 13.3 Update `openspec/changes/config-parser/review.md` with resolution notes for boundary-condition and test-coverage recommendations.
