# Design — query ThreadGroup naming

## Background

`generate_query_thread_groups` in `src/jmx_skeleton_generator/generators/query_groups.py` builds one ThreadGroup per `QueryConfig` entry. The ThreadGroup's `name` and `testname` attributes used to be derived from a 30/50-char slice of the SQL text:

```python
name=f"Query-{qc.query[:30]}",
testname=f"[Query] {qc.query[:50]}",
```

This makes the JTL `label` field useless for cross-referencing a specific query: `[Query] SELECT rtag_varchar_1, count(*...` doesn't tell you which of the 12 template entries failed.

## Decision

Add `QueryConfig.name: Optional[str]`. When the field is set, the ThreadGroup uses it. Otherwise the generator falls back to a positional `query{N}` label where N is the 1-indexed position in the `query_config` list.

### Why `name` is optional

- All existing fixtures (test_cfg.yaml, test_cfg_shig.yaml, ...) keep working unchanged — they don't set `name` and get `query1`, `query2`, ... automatically.
- Power users who want a stable identifier (e.g. for log scraping) can opt in.

### Why positional fallback not SQL hash

- SQL hash collides for similar queries (same prefix → same hash → same label).
- Positional is stable per template order, easy to communicate ("query3 failed"), matches the ordering users read in their YAML.

### Affected files

- `src/config_parser/models.py`: `QueryConfig` adds `name: Optional[str] = None` + `name_normalize` validator (strip whitespace, treat empty as None).
- `src/jmx_skeleton_generator/generators/query_groups.py`: in the `enumerate(query_config)` loop, build `query_label = qc.name if qc.name else f"query{idx}"` and use it for both ThreadGroup `name` and `testname`.
- `tests/jmx_skeleton_generator/test_generators.py`: 3 new assertions in `TestGenerateQueryThreadGroups`:
  - `test_query_label_uses_template_order_when_name_unset` — 3 configs without `name` produce `[Query] query1`, `[Query] query2`, `[Query] query3`.
  - `test_query_label_uses_explicit_name_when_provided` — `[Query] foo`, `[Query] query2` when first has `name="foo"`.
  - `test_query_name_field_round_trip` — `QueryConfig(name="  hello  ").name == "hello"`.

### What does NOT change

- SQL content (`?` placeholders preserved per F-14).
- `queryArgumentsTypes` count (per F-6).
- PreProcessor / Sampler script body.
- The JSR223 PreProcessor's `vars.put("param_0", ...)` key naming.
- Throughput / num_threads / duration handling.

## Test plan

- pytest `tests/jmx_skeleton_generator/test_generators.py::TestGenerateQueryThreadGroups` covers all three naming paths.
- smoke: regenerate `test_model_shig.yaml` + `test_cfg_shig.yaml`, JMeter run, then `grep "testname=" test_plan.jmx | sort -u` to confirm `query1..query12` labels appear in order.