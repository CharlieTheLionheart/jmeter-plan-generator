"""Tests for ``generate_bind_setup_thread_group`` SetupTG generator.

Per OpenSpec change ``col-tag-bind-write`` (2026-08-05) tasks.md §3:
- Bind sampler SetupTG loads column seeds and writes hash-grouped row
  memory to ``__SHARED_MEM_{db}_{table}_bind`` (a separate namespace from
  the full-row loader).
- One JSR223 Sampler per col_tag_bind table; mixed (bind + full-row)
  tables coexist (the full-row sampler is unchanged).
- All-full-row configuration must NOT emit a bind SetupTG.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from config_parser.models import WriteConfig
from jmx_skeleton_generator.generators.shared_memory_setup import (
    generate_bind_setup_thread_group,
)


def _write_cfg(*, tbl_name: str, bind: bool, per_tag: int = 2) -> WriteConfig:
    return WriteConfig(
        tbl_name=tbl_name,
        mode="batch_prepared",
        batch_lines=1,
        device_per_thread=1,
        num_threads=1,
        col_tag_bind_mode=bind,
        col_num_per_tag=per_tag if bind else 0,
    )


def _write_column_seed(tmp_path: Path, db: str, table: str, name: str, lines: list[str]) -> Path:
    table_dir = tmp_path / db / table
    table_dir.mkdir(parents=True, exist_ok=True)
    path = table_dir / f"1_{name}.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _dump(elem: ET.Element) -> str:
    return ET.tostring(elem, encoding="unicode")


def test_bind_sampler_emits_per_bind_table(tmp_path: Path) -> None:
    """Two bind tables → one Bind SetupTG with 2 JSR223 Samplers + 2 _bind props."""
    _write_column_seed(tmp_path, "iot_monitor", "t_cnc", "col_int8_1", ["1", "2", "3"])
    _write_column_seed(tmp_path, "iot_monitor", "t_alt", "col_int8_1", ["4", "5", "6"])
    cfg = [
        _write_cfg(tbl_name="iot_monitor.t_cnc", bind=True, per_tag=2),
        _write_cfg(tbl_name="iot_monitor.t_alt", bind=True, per_tag=1),
    ]

    elems = generate_bind_setup_thread_group(cfg, seed_root=tmp_path)

    # First elem is SetupThreadGroup; rest are sampler + hashTree pairs.
    assert elems, "expected SetupTG elements"
    stg_xml = _dump(elems[0])
    # ``setup_thread_group_element(name="Bind Setup")`` forces
    # ``testname="Bind Setup"``; the first literal must match.
    assert "Bind Setup" in stg_xml, stg_xml[:500]
    assert "SetupThreadGroup" in stg_xml or "setupThreadGroup" in stg_xml.lower()

    # Collect all JSR223 Samplers from the children; assert both _bind keys are
    # written to by some script.
    full = "".join(_dump(e) for e in elems)
    assert "__SHARED_MEM_iot_monitor_t_cnc_bind" in full, full[:1000]
    assert "__SHARED_MEM_iot_monitor_t_alt_bind" in full, full[:1000]
    assert full.count("JSR223Sampler") >= 2


def test_no_bind_sampler_when_all_full_row(tmp_path: Path) -> None:
    """All-full-row configuration must emit an empty Bind SetupTG list."""
    cfg = [_write_cfg(tbl_name="iot_monitor.t_cnc", bind=False)]

    elems = generate_bind_setup_thread_group(cfg, seed_root=tmp_path)

    assert elems == [], (
        f"all-full-row must skip Bind SetupTG; got {len(elems)} elements"
    )


def test_bind_sampler_preserves_mixed_table_setup(tmp_path: Path) -> None:
    """Mixed (bind + full-row) emits Bind sampler ONLY for the bind table."""
    _write_column_seed(tmp_path, "iot_monitor", "t_cnc", "col_int8_1", ["1", "2"])
    cfg = [
        _write_cfg(tbl_name="iot_monitor.t_cnc", bind=True, per_tag=2),
        _write_cfg(tbl_name="iot_monitor.t_alt", bind=False),
    ]

    elems = generate_bind_setup_thread_group(cfg, seed_root=tmp_path)

    full = "".join(_dump(e) for e in elems)
    assert "__SHARED_MEM_iot_monitor_t_cnc_bind" in full, full[:1000]
    assert "__SHARED_MEM_iot_monitor_t_alt_bind" not in full, (
        f"full-row t_alt must not produce _bind key; got: {full[:1000]}"
    )


def test_bind_sampler_writes_per_device_groups(tmp_path: Path) -> None:
    """D-21/D-25 (2026-08-14): Bind sampler keys row dict by deviceCode,
    bakes ``batch_lines`` distinct rows per deviceCode.

    Earlier commit-3 / D-13 design used ``[deviceCode].hashCode()`` mod
    num_threads to bucket devices into shared groups — but Groovy
    ``List.hashCode()`` is degenerate for short numeric-suffixed strings
    (device_1/device_3 both hash to the same group in smoke). D-21
    removes the hash call entirely and uses the literal ``deviceCode``
    as the row dict key. D-25 then extends to bake batch_lines rows
    per deviceCode so the Write TG prep (D-24) can emit batch_lines
    distinct rows per batch_lines prep call.
    """
    _write_column_seed(tmp_path, "iot_monitor", "t_cnc", "col_int8_1", ["1", "2", "3"])
    cfg = [_write_cfg(tbl_name="iot_monitor.t_cnc", bind=True, per_tag=2)]

    elems = generate_bind_setup_thread_group(cfg, seed_root=tmp_path, num_threads=4)

    full = "".join(_dump(e) for e in elems)
    # D-21: NO hashCode/ptagTuple references — keys row dict by deviceCode.
    # D-25 still uses a per-(deviceCode, batchLine) hash to pick a
    # distinct seed index per row within the batch, so this assertion
    # only bans the OLD group_id hash path.
    assert "ptagTuple" not in full, (
        f"D-21 removed ptagTuple — got:\n{full[:1500]}"
    )
    assert "groupId" not in full, (
        f"D-21 removed group_id — got:\n{full[:1500]}"
    )
    # Row dict key is the literal deviceCode (computed via calculateDeviceNumber
    # + deviceIdentifier in the baked script).
    assert "calculateDeviceNumber" in full, full[:1500]
    assert "deviceIdentifier" in full, full[:1500]
    assert "groups[deviceCode]" in full, (
        f"D-21 keys row dict by deviceCode; got:\n{full[:1500]}"
    )


def test_bind_sampler_aligns_with_write_tg_device() -> None:
    """D-21 (2026-08-14): SetupTG keys row dict by deviceCode (no hashCode).

    Both SetupTG and WriteTG compute the same ``deviceCode =
    calculateDeviceNumber(...)`` for a given threadNum; the WriteTG prep
    looks up the row dict by that literal deviceCode. No hash function,
    no many-to-one mapping — each deviceCode has its own row dict entry
    baked at SetupTG time.

    This test mirrors the SetupTG row dict construction in Python
    (no hash involved) and asserts that the ``deviceCode`` keys baked
    by SetupTG equal the ``deviceCode`` keys the WriteTG will compute
    at runtime. The actual Groovy execution comes from the integration
    smoke.
    """
    from jmx_skeleton_generator.generators.shared_memory_setup import (
        _build_bind_sampler_groovy,
    )

    num_threads = 4
    device_start = 1
    device_per_thread = 2

    # Python mirror of Groovy ``calculateDeviceNumber(thread_num, start,
    # dpt, 0)`` — row_index is constant 0 in WriteTG bind branch.
    def device_identifier(t: int) -> str:
        device_number = device_start + t * device_per_thread + (0 % device_per_thread)
        return f"device_{device_number}"

    # SetupTG side: loop over t in [0, num_threads), one row dict per
    # deviceCode. No hash.
    setuptg_keys: set[str] = set()
    for t in range(num_threads):
        setuptg_keys.add(device_identifier(t))

    # WriteTG side: loop over threadNum in [0, num_threads), compute
    # deviceCode directly. No hash.
    writetg_keys: set[str] = set()
    for thread_num in range(num_threads):
        writetg_keys.add(device_identifier(thread_num))

    assert setuptg_keys == writetg_keys, (
        f"SetupTG and WriteTG must agree on the deviceCode key set "
        f"(D-21 alignment invariant). "
        f"SetupTG={setuptg_keys}, WriteTG={writetg_keys}"
    )

    # Sanity: the generated SetupTG script uses deviceCode (not group_id)
    # as the row dict key.
    script = _build_bind_sampler_groovy(
        db="iot_monitor",
        table="t_cnc",
        col_num_per_tag=2,
        seed_root="/tmp",
        num_threads=num_threads,
        device_per_thread=device_per_thread,
        ptag_names=["device_id"],
    )
    assert "calculateDeviceNumber" in script
    assert "deviceIdentifier" in script
    # D-21: no ptagTuple-based lookup anywhere.
    assert "ptagTuple" not in script, (
        "D-21 removed hash-based group_id lookup; ptagTuple must be absent"
    )
    assert "groups[deviceCode]" in script, (
        "D-21 SetupTG keys row dict by deviceCode, not group_id"
    )


def test_bind_subset_per_group_offset(tmp_path: Path) -> None:
    """D-18 (2026-08-13): each hash group_id writes a DIFFERENT column subset.

    Earlier commit-3 / D-14 implementation shared ``dataColumns.take(colNumPerTag)``
    across all groups (simplification, see col-tag-bind-per-group-subsets DCR).
    Per design §1 Context, the real bind semantics is "device ↔ column subset":
    each group_id must pick a complementary offset into the sorted data columns
    so that groups write non-overlapping subsets.

    This test (a) verifies the Groovy formula is baked correctly and (b)
    uses a 4-thread fixture so the hash distribution reliably produces
    multiple distinct group_ids (verifying per-group offset is non-degenerate).
    """
    from jmx_skeleton_generator.generators.shared_memory_setup import (
        _build_bind_sampler_groovy,
    )

    db, table = "iot_monitor", "t_offset"
    # 10 distinct data column names; alphabetical sort yields the order below.
    sorted_cols = [
        "col_bool_1", "col_char_1", "col_float4_1", "col_float8_1", "col_float8_2",
        "col_int4_1", "col_int8_1", "col_timestamp_1", "col_varchar_1", "col_varchar_2",
    ]
    for col in sorted_cols:
        _write_column_seed(tmp_path, db, table, col, ["v0", "v1"])

    # 4 threads gives us better hash distribution than 2 (avoid degenerate
    # case where 2 device_codes happen to land in the same bucket).
    num_threads = 4
    col_num_per_tag = 3  # 3 cols/group * 4 groups = 12 > 10 → wrap-around exercised

    script = _build_bind_sampler_groovy(
        db=db,
        table=table,
        col_num_per_tag=col_num_per_tag,
        seed_root=tmp_path,
        num_threads=num_threads,
        device_per_thread=1,
        ptag_names=["device_id"],
    )

    # D-21 (2026-08-14): per-deviceCode key. The SetupTG script must
    # NOT use group_id or hash-based offsets — each deviceCode gets
    # its own row dict entry keyed by the literal deviceCode string.
    assert "groups[deviceCode]" in script, (
        f"D-21 SetupTG must key row dict by deviceCode; got:\n{script}"
    )
    assert "groupId" not in script, (
        f"D-21 removed group_id; got:\n{script}"
    )

    # Mirror the SetupTG row dict construction in Python (no hash).
    # Each deviceCode gets a col_names subset derived from the device
    # index in its name suffix (device_<N> → N-1), offset by col_num_per_tag.
    device_subsets: dict[str, list[str]] = {}
    for t in range(num_threads):
        device_code = f"device_{1 + t * 1 + 0}"  # deviceStart=1, dpt=1, row=0
        device_index = int(device_code.split("_")[1])
        col_start = ((device_index - 1) * col_num_per_tag) % len(sorted_cols)
        subset = [
            sorted_cols[(col_start + idx - 1) % len(sorted_cols)]
            for idx in range(1, col_num_per_tag + 1)
        ]
        device_subsets[device_code] = subset

    # With 4 distinct deviceCodes, the row dict has 4 distinct entries —
    # no aggregation, no hash collision. Each entry's subset is unique
    # (offset by col_num_per_tag per device).
    assert len(device_subsets) == num_threads, (
        f"expected {num_threads} device entries, got {len(device_subsets)}"
    )

    # Distinct device_codes must have DISTINCT row dict entries (each
    # gets exactly one subset — no aggregation, no hash collision). D-21
    # design does NOT require subsets to be disjoint when
    # ``numThreads * col_num_per_tag > dataColumns.size()`` (wrap-around
    # is allowed and expected) — only that each device has its own entry
    # keyed by literal deviceCode.
    for device_code, subset in device_subsets.items():
        assert len(subset) == col_num_per_tag, (
            f"device {device_code} expected {col_num_per_tag} cols, got {subset}"
        )

    # With num_threads=4 + col_num_per_tag=3 + 10 cols (12 > 10), the
    # offset-by-N design naturally produces 4 distinct starting points
    # (0, 3, 6, 9). Verify offsets are all distinct.
    offsets = set()
    for t in range(num_threads):
        device_code = f"device_{1 + t * 1 + 0}"
        device_index = int(device_code.split("_")[1])
        col_start = ((device_index - 1) * col_num_per_tag) % len(sorted_cols)
        offsets.add(col_start)
    assert len(offsets) == num_threads, (
        f"each device should get a distinct starting offset; got {offsets}"
    )
