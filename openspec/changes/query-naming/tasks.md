# Tasks — query ThreadGroup naming

## 1. Model field
- [x] 1.1 Add `name: Optional[str] = None` to `QueryConfig` in `src/config_parser/models.py`
- [x] 1.2 Add `name_normalize` validator: strip whitespace, treat empty string as `None`

## 2. Generator
- [x] 2.1 Switch `enumerate(query_config)` loop in `generate_query_thread_groups`
- [x] 2.2 Compute `query_label = qc.name if qc.name else f"query{idx}"`
- [x] 2.3 Use `query_label` in both ThreadGroup `name` and `testname`

## 3. Tests
- [x] 3.1 `test_query_label_uses_template_order_when_name_unset` — 3 configs → `query1`/`query2`/`query3`
- [x] 3.2 `test_query_label_uses_explicit_name_when_provided` — `name="foo"` overrides
- [x] 3.3 `test_query_name_field_round_trip` — strip + validate

## 4. Smoke
- [x] 4.1 Run `python -m kwjdbc_svt.main` with `test_model_shig.yaml` + `test_cfg_shig.yaml`
- [x] 4.2 `grep testname= test_plan.jmx` shows `query1..query12` in order
- [x] 4.3 pytest 633 passed (was 630; +3 new tests)

## 5. Documentation
- [x] 5.1 Write `proposal.md`
- [x] 5.2 Write `design.md`
- [x] 5.3 Write `tasks.md` (this file)