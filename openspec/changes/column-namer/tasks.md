# Tasks: column-namer

## 1. Implement column count allocation algorithm

- [x] 1.1 Create the `column_namer/allocate.py` module with a `allocate_columns(total: int, proportions: List[float]) -> List[int]` function.
- [x] 1.2 Implement the `floor + greedy` algorithm: floor allocation first, then distribute the remainder to the largest fractional parts.
- [x] 1.3 Validate inputs: reject negative proportions, reject proportions that do not sum to `1.0` (within a tolerance), and handle empty/zero inputs by returning an empty list.
- [x] 1.4 Add unit tests covering exact proportions, fractional proportions, empty/zero total, negative proportions, and proportions that do not sum to 1.

## 2. Implement data type normalization

- [x] 2.1 Create the `column_namer/normalize.py` module with a `normalize_type(col_type: str) -> str` function.
- [x] 2.2 Strip length/precision modifiers such as `varchar(16)` and `decimal(10,2)` down to the base type name.
- [x] 2.3 Handle array suffixes (`type[]`) and types without parentheses.
- [x] 2.4 Add unit tests for `varchar(16)`, `decimal(10,2)`, `int8`, `float[]`, and types with extra whitespace.

## 3. Define prefix mapping dictionary

- [x] 3.1 Create the `column_namer/constants.py` module with a `GROUP_PREFIXES` dictionary mapping group names to prefixes.
- [x] 3.2 Include mappings: `data_cols -> col`, `primary_tags -> ptag`, `regular_tags -> rtag`, `primary_keys -> pk`.
- [x] 3.3 Add validation that rejects unknown group names when the mapping is used.
- [x] 3.4 Add unit tests for all four mappings and an unknown group error case.

## 4. Implement column name generator

- [x] 4.1 Create the `column_namer/generate.py` module with a `generate_column_names(group: str, col_type: str, count: int) -> List[str]` function.
- [x] 4.2 Use `GROUP_PREFIXES` and `normalize_type` to produce names in the format `{prefix}_{type}_{sequence}`.
- [x] 4.3 Ensure sequence numbers start at 1 and are continuous within the same group/type.
- [x] 4.4 Add unit tests for each group type and for `count = 0` returning an empty list.

## 5. Build table-level column namer and index mapping

- [x] 5.1 Create the `column_namer/namer.py` module with a `ColumnNamer` class or `name_columns(config: TableConfig) -> Tuple[List[str], Dict[str, int]]` function.
- [x] 5.2 Integrate `allocate_columns` with `type_proportion` from config to determine per-type counts.
- [x] 5.3 Generate names for all column groups (`primary_tags`, `regular_tags`, `primary_keys`, `data_cols`) in the order defined by the config.
- [x] 5.4 Build and return a global index mapping from column name to 1-based index, excluding the timestamp column.
- [x] 5.5 Add unit tests for multi-group tables, verifying global sequential indices and the `{index}_{col_name}.{type}` seed-file naming pattern.

## 6. Add integration and boundary tests

- [x] 6.1 Add a test for `total < len(proportions)` confirming some types receive zero columns.
- [x] 6.2 Add a large-column test (e.g., 10,000 columns) to verify performance and stability.
- [x] 6.3 Add an end-to-end test that exercises the full pipeline from config to column list and index mapping.
- [x] 6.4 Run the full test suite and fix any failures.
