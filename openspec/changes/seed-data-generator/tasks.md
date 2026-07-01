# Tasks: seed-data-generator

## 1. Module skeleton and interface contract

- [x] 1.1 Create the seed data generator package directory and `__init__.py`.
- [x] 1.2 Define the public API entry point (function/class signature) accepting parsed column/table configs from config-parser and column names from ddl-generator.
- [x] 1.3 Define the output contract: list of generated file paths and row aggregate CSV path.
- [x] 1.4 Add a module-level docstring documenting supported `val_range` syntax, NULL handling rules, and file naming conventions.

## 2. val_range parser adapter

- [x] 2.1 Wrap `utils/val_range_parser.py` to classify `val_range` into: numeric range, enum, regex, or foreign-key reference.
- [x] 2.2 Normalize numeric parse results into a common value-domain object (min/max, inclusive/exclusive, integer/float).
- [x] 2.3 Add unit tests for adapter classification covering `>=`, `<=`, `[a,b]`, `(a,b)`, `enum:...`, regex, and `ref:db.table.col`.
- [x] 2.4 Add unit tests for invalid `val_range` strings and ensure clear error messages.

## 3. Numeric value generators

- [x] 3.1 Implement integer generator for lower-bound expressions (`>=n`).
- [x] 3.2 Implement integer generator for upper-bound expressions (`<=n`).
- [x] 3.3 Implement integer generator for closed intervals (`[a,b]` inclusive).
- [x] 3.4 Implement integer generator for open intervals (`(a,b)` exclusive).
- [x] 3.5 Implement float generator with configurable precision for `>=`, `<=`, `[a,b]`, and `(a,b)`.
- [x] 3.6 Add boundary-value unit tests for `[1,1]`, `>=0` intersect `<=0`, and open-interval edge cases.
- [x] 3.7 Add property-based tests (Hypothesis) verifying all generated values satisfy the parsed domain.

## 4. String, enum, and NULL value generators

- [x] 4.1 Integrate a regex string generator library (e.g., `rstr` or `xeger`) for `val_range` regex patterns.
- [x] 4.2 Document the supported regex subset and explicitly list unsupported features (e.g., backreferences, nested quantifiers).
- [x] 4.3 Implement enum generator that cycles through values in declared order.
- [x] 4.4 Implement NULL value inserter: compute `floor(null_rate * seed_num)` NULLs, scatter them randomly through the column seed list.
- [x] 4.5 Respect `nullable=false` (no NULLs) and `null_rate=0.0` (no NULLs).
- [x] 4.6 Add unit tests for enum cycling, regex output matching, NULL counts, and NULL random distribution.
- [x] 4.7 Add unit tests for invalid `null_rate` values (< 0 or > 1) and `seed_num <= 0`.

## 5. Foreign-key reference sampling

- [x] 5.1 Implement reference discovery: scan all table configs to find columns with `val_range="ref:<db>.<table>.<col>"`.
- [x] 5.2 Pre-generate referenced primary-key column seed files before dependent tables are generated.
- [x] 5.3 Implement sampler that reads a seed file and returns `seed_num` values using uniform random sampling with replacement, cycling when `seed_num` exceeds reference size.
- [x] 5.4 Add unit tests for sampling with replacement, cycling behavior, and missing seed file error handling.
- [x] 5.5 Add an integration test for cross-database reference (`ref:iot_metadata.t_workshop.pk_int8_1`).

## 6. Column seed file output

- [x] 6.1 Implement column seed CSV writer using Python `csv` module with `QUOTE_MINIMAL`.
- [x] 6.2 Write header row `value` and one value per row; write Python `None` as the literal string `null`.
- [x] 6.3 Apply naming convention `{column_index}_{column_name}.csv` for all column seed files (no `.ref` suffix).
- [x] 6.4 Ensure output directory `seeds/{database}/{table}/` is created idempotently.
- [x] 6.5 Add integration tests writing to a temporary directory and reading back with `csv.reader`.
- [x] 6.6 Add tests for special-character escaping: commas, quotes, newlines.

## 7. Row seed aggregate generation

- [x] 7.1 Implement column seed file reader that discovers files in `seeds/{database}/{table}/` and sorts them numerically by column index.
- [x] 7.2 Implement row aggregate builder: size = max `seed_num` across columns; shorter columns repeat cyclically.
- [x] 7.3 Preserve column order in the aggregate matching numerical column-index order.
- [x] 7.4 Write the aggregate to `seeds/{database}/{table}.csv` with a header row of column names and one row per record.
- [x] 7.5 Add unit tests for cyclic fill, max-row sizing, and column-order preservation (including files `1_...`, `2_...`, `10_...`).
- [x] 7.6 Add integration tests round-tripping the aggregate CSV through `csv.reader` and verifying each row is a valid prepared-statement parameter list.

## 8. End-to-end generation orchestrator

- [x] 8.1 Wire together parser adapter, value generators, NULL handling, reference sampling, column file output, and row aggregate output into a single `generate_seeds(config)` function.
- [x] 8.2 Add input validation: reject `seed_num <= 0`, invalid `null_rate`, and unsupported type/`val_range` combinations.
- [x] 8.3 Add logging of input config hash and generated file list for traceability and rollback.
- [x] 8.4 Add a cleanup helper that removes `seeds/{database}/{table}/` and `seeds/{database}/{table}.csv` for a given table.
- [x] 8.5 Add an end-to-end test generating seeds for one time-series table and one relational table with a cross-table reference.

## 9. Review findings remediation

- [x] 9.1 Document precise `val_range` boundary semantics (integer inclusive bounds, float precision) in module docs.
- [x] 9.2 Define and implement `null_rate * seed_num` rounding rule: floor, ensuring NULL count never exceeds the configured proportion.
- [x] 9.3 Define and implement `seed_num=0`/negative behavior: raise a validation error with a clear message.
- [x] 9.4 Add a performance benchmark test for large `seed_num` (e.g., 1 million) to verify memory and runtime.
- [x] 9.5 Add concurrent-generation tests for multiple tables writing to separate directories.
- [x] 9.6 Update design.md to reflect resolved open questions and task-level implementation details.

## 10. Verification and handoff

- [x] 10.1 Run the full unit and integration test suite and ensure all tests pass.
- [x] 10.2 Run lint/type checks on the new package.
- [x] 10.3 Review generated sample seed files manually for one table to confirm CSV correctness.
- [x] 10.4 Update the change `review.md` to mark resolved findings and capture any remaining deviations.
- [x] 10.5 Run `openspec-verify-change` (or equivalent) and archive/transition the change on success.
