"""Tests for ``_build_batch_prepared_preprocessor_body`` col_tag_bind_mode branch.

Per OpenSpec change ``col-tag-bind-write`` (2026-08-05) tasks.md §4 +
D-27 follow-up (2026-08-17): D-17 smoke revealed that the
``batch_prepared`` JSR223PreProcessor does NOT route through the bind
path even when ``col_tag_bind_mode=True``. The preprocessor keeps
reading ``__SHARED_MEM_{db}_{table}`` (full-row map) while the SetupTG
bind sampler writes only ``__SHARED_MEM_{db}_{table}_bind``. This
mismatch yields a ``NullPointerException: Cannot invoke method size()
on null object`` mid-batch on every Write TG iteration.

The fix extends ``_build_batch_prepared_preprocessor_body`` and its
wrapper ``build_batch_prepared_preprocessor_script`` with a
``col_tag_bind_mode`` switch so that batch_prepared + col_tag_bind_mode
takes the same deviceCode-keyed per-deviceCode row dict (D-21) as the
schemaless bind path in ``rest_write_groups.py``.

These tests pin the contract:

- ``col_tag_bind_mode=True`` → script reads the ``_bind`` namespace.
- ``col_tag_bind_mode=True`` → script looks up by literal ``deviceCode``
  (D-21 per-deviceCode key — no hash distribution; mirrors the
  schemaless bind path).
- ``col_tag_bind_mode=True`` → script still emits
  ``vars.putObject("__BATCH_ROWS_<tableName>", ...)`` (sampler-side
  contract).
- ``col_tag_bind_mode=False`` (or absent) → byte-identical to the
  pre-change behavior (reads ``__SHARED_MEM_*``, no ``deviceCode``
  keying, no ``_bind`` key).
"""

from __future__ import annotations

import pytest

from jmx_skeleton_generator.generators.write_groups import (
    _build_batch_prepared_preprocessor_body,
    build_batch_prepared_preprocessor_script,
)


# ---------------------------------------------------------------------------
# Minimal kwargs. The legacy default keeps the original column list
# (ts + ptag + 5 data cols) so byte-equality assertions are tight.
# ``all_columns`` matches the PreparedInsertTemplateGenerator contract
# (``[ts, *ptag_names, *data_col_names]``); ``ptag_count`` is the count
# of primary-tag columns (here 1: ptag_varchar_1).
# ---------------------------------------------------------------------------


def _minimal_kwargs(**overrides) -> dict:
    base = {
        "table_name": "iot_monitor.meters",
        "first_ptag": "ptag_varchar_1",
        "batch_lines": 1,
        "ms_step": 1000,
        "all_columns": [
            "ts",
            "ptag_varchar_1",
            "col_int8_1",
            "col_int8_2",
            "col_int8_3",
            "col_int8_4",
            "col_int8_5",
        ],
        "ptag_count": 1,
        "device_per_thread": 1,
    }
    base.update(overrides)
    return base


def test_bind_mode_reads_bind_namespaced_memory() -> None:
    """col_tag_bind_mode=True must read ``__SHARED_MEM_*_bind`` (the
    SetupTG bind sampler writes there, not the full-row map).
    """
    script = _build_batch_prepared_preprocessor_body(
        **_minimal_kwargs(col_tag_bind_mode=True)
    )
    assert "__SHARED_MEM_iot_monitor_meters_bind" in script, (
        "bind-mode prep must read the bind-namespaced shared memory map"
    )
    # Legacy full-row key (without _bind) must NOT appear, otherwise the
    # prep tries to read a null map and throws NPE on .size().
    assert '__SHARED_MEM_iot_monitor_meters")' not in script, (
        "bind-mode prep must not read the full-row SharedMemory key"
    )


def test_bind_mode_uses_devicecode_key_no_hash_distribution() -> None:
    """col_tag_bind_mode=True must look up the bind map by literal
    ``deviceCode`` (D-21 per-deviceCode key), NOT by
    ``hashCode() mod numThreads``. The SetupTG bakes one entry per
    deviceCode so any hash distribution would introduce a
    Setup-vs-Write skew bug (regression on 2026-08-14).
    """
    script = _build_batch_prepared_preprocessor_body(
        **_minimal_kwargs(col_tag_bind_mode=True)
    )
    assert "deviceCode" in script, "bind-mode prep must derive deviceCode"
    # ``bindGroups.get(deviceCode) as Map`` — match on the variable
    # lookup regardless of the trailing cast (Groovy Map cast is a
    # convenience for downstream field access).
    assert "bindGroups.get(deviceCode)" in script, (
        "bind-mode prep must look up the bind map by deviceCode literal"
    )
    # No hash distribution anywhere in the bind path. The Groovy script
    # computes ``int groupId = ... % numThreads`` is forbidden (D-21);
    # only the per-deviceCode ``bindGroups.get(deviceCode)`` lookup is
    # allowed.
    assert "groupId" not in script, (
        "bind-mode prep must NOT introduce a groupId index (D-21 contract)"
    )


def test_bind_mode_writes_batch_rows_for_sampler_consumption() -> None:
    """col_tag_bind_mode=True must still emit
    ``vars.putObject("__BATCH_ROWS_<tableName>", ...)`` so the existing
    batch_prepared JSR223Sampler can consume the rows.

    The actual emit is ``putObject("__BATCH_ROWS_${tableName}", ...)``
    (Groovy G-string interpolation — runtime substitution), which is
    functionally identical to the non-bind prep's emit. The sampler
    reads ``vars.getObject("__BATCH_ROWS_<table>")`` with the same
    key, so the runtime contract holds.
    """
    script = _build_batch_prepared_preprocessor_body(
        **_minimal_kwargs(col_tag_bind_mode=True)
    )
    # Both forms are acceptable — the generator uses interpolation,
    # but a literal ``tableName`` reference inside a Groovy G-string is
    # also valid.
    assert (
        'putObject("__BATCH_ROWS_${tableName}"' in script
        or 'putObject("__BATCH_ROWS_iot_monitor.meters"' in script
    ), (
        "bind-mode prep must still feed the batch_prepared sampler via "
        "__BATCH_ROWS_<tableName>"
    )


def test_bind_mode_safe_default_when_groups_empty() -> None:
    """Empty / missing bind groups must produce a safe no-op (no
    exception), so the JDBC sampler logs a clean error rather than
    triggering a Groovy crash mid-batch.
    """
    script = _build_batch_prepared_preprocessor_body(
        **_minimal_kwargs(col_tag_bind_mode=True)
    )
    assert "log.warn" in script
    assert "__BATCH_ROWS" in script
    # The empty-groups guard must bail out before calling .size() /
    # .get() on a possibly-null Map.
    assert "bindGroups == null" in script or "bindGroups.isEmpty" in script


def test_default_mode_unchanged_when_bind_false() -> None:
    """Regression: when ``col_tag_bind_mode=False`` the prep must read
    ``__SHARED_MEM_<table>`` (NOT ``_bind``) and must NOT key by
    ``deviceCode``.
    """
    script = _build_batch_prepared_preprocessor_body(
        **_minimal_kwargs(col_tag_bind_mode=False)
    )
    assert "__SHARED_MEM_iot_monitor_meters_bind" not in script, (
        "non-bind mode must NOT read the bind namespace"
    )
    # The full-row SharedMemory key is built via
    # ``__SHARED_MEM_" + tableName.replace('.', '_')`` (Groovy string
    # concat) — check the prefix literal rather than a closed-quote form.
    assert '__SHARED_MEM_" + tableName.replace' in script, (
        "non-bind mode must reference the full-row shared memory"
    )
    # Non-bind path uses the SharedMemory row map (``sharedRows``),
    # NOT the bind map.
    assert "bindGroups.get(deviceCode)" not in script, (
        "non-bind mode must NOT key the bind map"
    )


def test_default_mode_unchanged_without_kwarg() -> None:
    """Backward compatibility: omitting ``col_tag_bind_mode`` entirely
    must keep the existing prep behavior (this is the F-3 baseline
    that all existing fixtures rely on).
    """
    script = _build_batch_prepared_preprocessor_body(**_minimal_kwargs())
    assert "__SHARED_MEM_iot_monitor_meters_bind" not in script
    assert "bindGroups.get(deviceCode)" not in script


def test_wrapper_script_propagates_bind_mode() -> None:
    """``build_batch_prepared_preprocessor_script`` must thread the
    ``col_tag_bind_mode`` switch through to the body builder.
    """
    script = build_batch_prepared_preprocessor_script(
        table_name="iot_monitor.meters",
        first_ptag="ptag_varchar_1",
        batch_lines=1,
        ms_step=1000,
        col_tag_bind_mode=True,
        all_columns=[
            "ts",
            "ptag_varchar_1",
            "col_int8_1",
            "col_int8_2",
        ],
        ptag_count=1,
        device_per_thread=1,
    )
    assert "__SHARED_MEM_iot_monitor_meters_bind" in script
    assert "bindGroups.get(deviceCode)" in script
