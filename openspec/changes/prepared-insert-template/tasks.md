# Tasks: prepared-insert-template

## 1. Project skeleton and public API

- [ ] 1.1 Create `src/prepared_insert_template/__init__.py` exporting the public API (`PreparedInsertTemplateGenerator`, `requires_prepared_insert_templates`).
- [ ] 1.2 Add a minimal module docstring describing the module's responsibility and the expected template dictionary shape (`{db.table: insert into ... values (?, ?, ?)}`).
- [ ] 1.3 Verify the package can be imported without errors.

## 2. Condition check: `requires_prepared_insert_templates()`

- [ ] 2.1 Implement `requires_prepared_insert_templates(write_config)` returning `True` when any entry has `mode` in (`single_prepared`, `batch_prepared`).
- [ ] 2.2 Return `False` for `None`, empty `write_config`, and configs containing only `single_insert` / `batch_insert`.
- [ ] 2.3 Return `False` for malformed entries missing a `mode` key.
- [ ] 2.4 Write unit tests covering: empty config, only single_insert, only batch_insert, single_prepared, batch_prepared, mixed modes, missing mode key.

## 3. Single-table template generation

- [ ] 3.1 Implement `generate_template(table_name, columns)` producing a lower-case `insert into <table_name> (col1, col2) values (?, ?)` string.
- [ ] 3.2 Preserve column order exactly as provided.
- [ ] 3.3 Return `None` (or raise a clear domain exception) when `columns` is empty, preventing illegal `insert into ... () values ()` output.
- [ ] 3.4 Write unit tests covering: single column, multiple columns, column order preservation, empty column list, exact SQL string match.

## 4. Time-series table filtering

- [ ] 4.1 Implement `filter_timeseries_tables(ts_dbs)` excluding relational tables.
- [ ] 4.2 Confirm the filtering criterion matches the existing table metadata model (e.g., `table_type == 'time_series'` or equivalent).
- [ ] 4.3 Return an empty list when no time-series tables are present.
- [ ] 4.4 Write unit tests covering: only time-series tables, only relational tables, mixed table types, empty input.

## 5. Multi-table template dictionary assembly

- [ ] 5.1 Implement `build_template_dict(tables, columns_by_table)` returning a dict keyed by fully qualified lower-case name `db.table`.
- [ ] 5.2 Skip tables with empty column lists and log a warning instead of producing illegal SQL.
- [ ] 5.3 Return `{}` when no valid templates can be built.
- [ ] 5.4 Write unit tests covering: single database single table, multiple databases, mixed time-series and relational tables, empty column list handling, exact key format and SQL content.

## 6. `PreparedInsertTemplateGenerator` class

- [ ] 6.1 Implement `PreparedInsertTemplateGenerator` accepting table/column metadata and a `write_config`.
- [ ] 6.2 Expose a `generate()` method returning the template dictionary.
- [ ] 6.3 Internally compose filtering, single-table generation, and dictionary assembly.
- [ ] 6.4 Write integration tests covering: full happy path, no prepared modes (generator not required), all-relational tables, multi-database output.

## 7. Integration into the application entry points

- [ ] 7.1 In `main.py` (or `jmx_builder`), add an explicit `if requires_prepared_insert_templates(write_config): ...` branch to instantiate `PreparedInsertTemplateGenerator`.
- [ ] 7.2 Pass the generated template dictionary to downstream write-strategy modules.
- [ ] 7.3 Ensure the feature is completely skipped when no prepared modes are configured.
- [ ] 7.4 Add a smoke test or lightweight integration test that exercises the entry-point branch.

## 8. Boundary and review-driven tests

- [ ] 8.1 Add a boundary test for `write_config` containing entries with no `mode` key.
- [ ] 8.2 Add a boundary test for an empty database/table list.
- [ ] 8.3 Add a boundary test for reserved-word column names; document whether quoting is required based on KaiwuDB identifier rules.
- [ ] 8.4 Verify downstream consumers handle an empty template dictionary gracefully.
- [ ] 8.5 Run the full test suite for the new module and confirm all tests pass.

## 9. Documentation and final review

- [ ] 9.1 Update module-level docstrings to state the FQN key format (`db.table`, lower-case) and the empty-dict contract.
- [ ] 9.2 Verify `review.md` findings are addressed: task granularity, boundary conditions, test coverage, and backward compatibility notes.
- [ ] 9.3 Request code review for the completed change.
