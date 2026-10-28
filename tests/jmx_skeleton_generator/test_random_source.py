"""Tests for the ThreadLocalRandom replacement across generated Groovy scripts.

Background (OpenSpec change ``write-missing-data``, design D4(b)):

The generated Groovy scripts used three different random sources:
``new Random()`` (fresh instance per call — entropy collection + static
seed CAS contention), ``Math.random()`` (global CAS — the slowest of all
legitimate sources) and a reusable ``new Random()`` instance.

All 7 call sites are replaced by ``java.util.concurrent.ThreadLocalRandom``
(per-thread, lock-free). The replacement MUST be behavior-equivalent: the
value range stays ``[0, n)``.

These tests pin the *generated script text* — the Groovy is executed by
JMeter at runtime, so the only observable surface from Python is the
emitted source.
"""

from __future__ import annotations

from jmx_skeleton_generator.generators.query_groups import (
    generate_param_binding_script,
)
from jmx_skeleton_generator.generators.rest_write_groups import (
    _build_rest_write_preprocessor_script,
)
from jmx_skeleton_generator.generators.write_groups import (
    _build_batch_prepared_bind_preprocessor_body,
    _build_batch_prepared_preprocessor_body,
    _build_inline_sql_preprocessor_script,
)

import pytest

from config_parser.models import (
    ColTypeConfig,
    PrimaryTagColTypeConfig,
    TsTableConfig,
)


def _ts_table() -> TsTableConfig:
    return TsTableConfig(
        name="meters",
        data_col_count=1,
        primary_tag_count=1,
        regular_tag_count=0,
        data_cols=[
            ColTypeConfig(col_type="int8", type_proportion=1.0, val_range="[1,10]", seed_num=4),
        ],
        primary_tags=[
            PrimaryTagColTypeConfig(
                col_type="varchar(32)", type_proportion=1.0, val_range="enum:X,Y", seed_num=4
            )
        ],
    )


def _inline_direct(col_tag_bind_mode: bool) -> str:
    return _build_inline_sql_preprocessor_script(
        db="iot_monitor",
        table="t_cnc",
        columns=["ts", "ptag_varchar_1", "col_int8_1"],
        first_ptag_column="ptag_varchar_1",
        device_per_thread=2,
        batch_lines=5,
        col_tag_bind_mode=col_tag_bind_mode,
    )


def _prepare_non_bind() -> str:
    return _build_batch_prepared_preprocessor_body(
        table_name="iot_monitor.t_cnc",
        first_ptag="ptag_varchar_1",
        batch_lines=5,
        ms_step=1000,
        device_per_thread=2,
    )


def _prepare_bind() -> str:
    return _build_batch_prepared_bind_preprocessor_body(
        table_name="iot_monitor.t_cnc",
        ptag_names=["ptag_varchar_1"],
        ptag_col_types=["varchar"],
        col_type_buckets={"col_int8": ["int8", "bigint"]},
        batch_lines=5,
        ms_step=1000,
        device_per_thread=2,
    )


def _rest_write(col_tag_bind_mode: bool) -> str:
    return _build_rest_write_preprocessor_script(
        db="iot_monitor",
        table="meters",
        ts_table=_ts_table(),
        col_tag_bind_mode=col_tag_bind_mode,
        col_num_per_tag=2 if col_tag_bind_mode else 0,
        num_threads=4,
        device_per_thread=2,
        batch_lines=5,
    )


def _query_seed() -> str:
    return generate_param_binding_script(
        "SELECT * FROM iot_monitor.t_cnc WHERE col_int8_1 = ?"
    )


# The 7 call sites covered by this change — each entry is
# (label, script-producing callable).
_ALL_SITES = [
    ("direct non-bind", lambda: _inline_direct(False)),
    ("direct bind", lambda: _inline_direct(True)),
    ("prepare non-bind", _prepare_non_bind),
    ("prepare bind", _prepare_bind),
    ("schemaless non-bind", lambda: _rest_write(False)),
    ("schemaless bind", lambda: _rest_write(True)),
    ("query seed", _query_seed),
]


@pytest.mark.parametrize("label,factory", _ALL_SITES, ids=[s[0] for s in _ALL_SITES])
def test_no_new_random(label: str, factory) -> None:
    """No generated script may keep ``new Random()``."""
    script = factory()
    assert "new Random()" not in script, f"{label}: legacy 'new Random()' still present"


@pytest.mark.parametrize("label,factory", _ALL_SITES, ids=[s[0] for s in _ALL_SITES])
def test_no_math_random(label: str, factory) -> None:
    """No generated script may keep ``Math.random()``."""
    script = factory()
    assert "Math.random()" not in script, f"{label}: legacy 'Math.random()' still present"


@pytest.mark.parametrize("label,factory", _ALL_SITES, ids=[s[0] for s in _ALL_SITES])
def test_uses_thread_local_random(label: str, factory) -> None:
    """Every script that used to sample randomly now uses ThreadLocalRandom."""
    script = factory()
    assert "ThreadLocalRandom.current()" in script, (
        f"{label}: expected ThreadLocalRandom.current() in generated script"
    )


def test_thread_local_random_is_fully_qualified() -> None:
    """The Groovy must use the fully-qualified class name.

    ``java.util.concurrent.ThreadLocalRandom`` is not in Groovy's default
    imports, so the short name would not resolve at runtime.
    """
    script = _prepare_non_bind()
    assert "java.util.concurrent.ThreadLocalRandom.current()" in script
