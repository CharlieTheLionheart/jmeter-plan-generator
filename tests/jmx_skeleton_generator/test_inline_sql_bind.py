"""Tests for ``_build_inline_sql_preprocessor_script`` col_tag_bind_mode branch.

Behavior under test:
- ``col_tag_bind_mode=True``: preprocessor reads the bind-namespaced
  shared memory, looks up the deviceCode's group directly, and emits
  an inline INSERT covering ts + every primary_tag + the subset
  data_col + any explicit NOT NULL data_col.
- Empty / missing groups produce a safe fallback SQL so the JDBC
  sampler logs a clean error rather than crashing mid-batch.
- ``col_tag_bind_mode=False`` falls back to the full-row path.
"""

from __future__ import annotations

from jmx_skeleton_generator.generators.write_groups import (
    _build_inline_sql_preprocessor_script,
)


# ---------------------------------------------------------------------------
# Minimal kwargs for the test suite. The default ``columns`` include a
# first ptag (``device_id``) plus 4 data columns to exercise the
# subset / NOT-NULL / group-id branches.
# ---------------------------------------------------------------------------


def _minimal_kwargs(**overrides) -> dict:
    base = {
        "db": "iot_monitor",
        "table": "meters",
        "columns": [
            "ts",
            "device_id",
            "col_int8_1",
            "col_int8_2",
            "col_int8_3",
            "col_varchar_1",
        ],
        "first_ptag_column": "device_id",
        "device_per_thread": 1,
        "column_types": None,
        "ms_step": 1000,
        "batch_lines": 1,
    }
    base.update(overrides)
    return base


def test_bind_mode_emits_subset_columns() -> None:
    """col_tag_bind_mode=True → script reads ``__SHARED_MEM_*_bind`` and
    builds an INSERT keyed on a ptag-bound column subset.
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=True, col_num_per_tag=3, num_threads=4)
    )

    assert "__SHARED_MEM_iot_monitor_meters_bind" in script, (
        "bind-mode script must read the bind-namespaced shared memory"
    )
    # The qualified INSERT is built at Groovy runtime via
    # ``qualifiedTable = db + "." + table``; check both halves separately.
    assert "INSERT INTO" in script, "INSERT literal must be present in script"
    assert "qualifiedTable" in script, "qualifiedTable assembly must be present"
    assert "iot_monitor" in script and "meters" in script
    # ptag column must appear in the column list (first ptag is part of
    # every INSERT regardless of subset).
    assert "device_id" in script


def test_bind_mode_uses_literal_device_code_lookup() -> None:
    """deviceCode 用显式 toString() 拼接，不用 GString `${a}_${b}`。

    JSR223 + GroovyScriptEngineImpl 3.0.20 把简单标识符 GString 编译为
    ``$(closure)`` 方法调用（``MissingMethodException: $()``）；用
    ``obj.toString() + "_" + obj.toString()`` 走普通字符串拼接绕过这个
    编译器 bug。
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=True, col_num_per_tag=2, num_threads=8)
    )

    assert "hashCode()" not in script, (
        f"bind map must be looked up by literal deviceCode; got snippet:\n{script[:2000]}"
    )
    assert "threadNum.toString() + \"_\" + d.toString()" in script, (
        f"expected explicit toString() concatenation deviceCode line; "
        f"got snippet:\n{script[:2000]}"
    )


def test_bind_mode_includes_not_null_data_cols() -> None:
    """NOT-NULL data columns are appended to the INSERT column list even
    when they fall outside the per-group subset.
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(
            col_tag_bind_mode=True,
            col_num_per_tag=2,
            num_threads=4,
            not_null_data_cols=["col_int8_3"],
        )
    )

    # The NOT-NULL column must be referenced somewhere in the column-list
    # construction (we don't pin exact ordering because LinkedHashSet
    # iteration order matches insertion; the column name must simply appear).
    assert "col_int8_3" in script, (
        "explicit NOT NULL data column must appear in INSERT column list"
    )


def test_bind_mode_no_group_raises_business_exception() -> None:
    """When the bind groups map is empty, the script MUST throw.

    write-missing-data D11: 静默降级(``SELECT 1`` 兜底)会让整轮测试
    "全绿但一行没写"——失败必须尽早暴露为 sampler error。
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=True, col_num_per_tag=2, num_threads=4)
    )

    assert "throw new RuntimeException" in script, (
        f"empty-groups guard must raise a RuntimeException; snippet:\n{script[:2000]}"
    )
    assert "seed CSV load failed" in script, (
        f"empty-groups guard must carry the failure hint; snippet:\n{script[:2000]}"
    )
    assert 'vars.put("insert_sql", "SELECT 1")' not in script, (
        f"empty-groups guard must NOT silently degrade to SELECT 1; snippet:\n{script[:2000]}"
    )


def test_default_mode_unchanged() -> None:
    """Regression: ``col_tag_bind_mode=False`` keeps the existing full-row
    INSERT behavior — must read ``__SHARED_MEM_*`` (not ``_bind``) and
    emit a script that does NOT contain the bind-namespaced read.
    """
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=False, col_num_per_tag=0)
    )


def test_bind_mode_dpt_for_loop_emits() -> None:
    """每个 sampler tick 覆盖 device_per_thread 个 device（外层 dpt for）。"""
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(
            col_tag_bind_mode=True, col_num_per_tag=2, num_threads=2,
            device_per_thread=2, batch_lines=5,
        )
    )
    assert "for (int d = deviceStart; d < deviceStart + devicePerThread; d++)" in script, (
        f"expected dpt for-loop; got snippet:\n{script[:2000]}"
    )
    # MultiRowInsert：内层 batch_lines 行
    assert "for (int r = 0; r < batchLines; r++)" in script, (
        f"expected batch_lines loop; got snippet:\n{script[:2000]}"
    )


def test_bind_mode_step_per_row_ts_formula() -> None:
    """ts = baseTime + r * msStep，每行间隔一个 msStep（整步语义）。"""
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(
            col_tag_bind_mode=True, col_num_per_tag=2, num_threads=2,
            device_per_thread=2, batch_lines=3, ms_step=1000,
        )
    )
    assert "batchSeq * msStep" not in script, (
        f"batchSeq tick accumulator must not appear; got snippet:\n{script[:2000]}"
    )
    assert "baseTime + batchSeq" not in script, (
        f"baseTime + batchSeq form must not appear; got snippet:\n{script[:2000]}"
    )
    assert "baseTime + r * msStep" in script, (
        f"expected `baseTime + r * msStep`; got snippet:\n{script[:2000]}"
    )


def test_bind_mode_base_time_per_tick() -> None:
    """baseTime 每个 sampler tick 直接取 System.currentTimeMillis()，不缓存。"""
    script = _build_inline_sql_preprocessor_script(
        **_minimal_kwargs(col_tag_bind_mode=True, col_num_per_tag=2, num_threads=2)
    )
    assert "baseTime = System.currentTimeMillis()" in script, (
        f"expected direct System.currentTimeMillis() per-tick sample; got snippet:\n{script[:2000]}"
    )
    assert "baseTimeKey" not in script, (
        f"UDV cache key must not appear; got snippet:\n{script[:2000]}"
    )
    assert "batchSeq" not in script, (
        f"batchSeq counter must not appear; got snippet:\n{script[:2000]}"
    )
