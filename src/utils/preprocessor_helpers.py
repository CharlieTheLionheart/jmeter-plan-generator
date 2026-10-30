"""JSR223PreProcessor Groovy helper functions for write-side data assembly.

These helpers expose a Groovy source snippet that gets embedded into
JSR223PreProcessor scripts in
:mod:`jmx_skeleton_generator.generators.write_groups` and
:mod:`shared_memory_initializer`. The Python implementations exist
so callers can unit-test the same algorithms without bootstrapping a
JMeter/JVM runtime.

Helpers exposed:

- :func:`calculate_timestamps` — per-row timestamp list given base, batch
  sequence, ms_step, batch_lines. Python-only (not embedded into
  generated scripts).
- :func:`calculate_device_number` — device number from thread index,
  device_start, device_per_thread, and per-row index. Embedded as Groovy.
- :func:`build_device_identifier` — formats ``device_{n}``.
- :func:`clone_rows` — shallow per-row list clone.

Numeric type policy:

- All timestamp and device-number arithmetic uses Python ``int`` /
  Groovy ``long`` to avoid overflow on long-running batches.
- Inter-timestamp step uses integer division (``ms_step // batch_lines``)
  in :func:`calculate_timestamps`. When ``ms_step < batch_lines`` the
  per-row intra-step rounds to 0.

Boundary guarantees:

- ``batch_lines <= 0`` raises :class:`PreprocessorHelperError`.
- ``device_per_thread <= 0`` raises :class:`PreprocessorHelperError`.
- ``row_index < 0`` raises :class:`PreprocessorHelperError`.
"""

from __future__ import annotations

from typing import Any, List, Sequence


class PreprocessorHelperError(Exception):
    """Raised when a preprocessor helper fails a precondition."""


def calculate_timestamps(
    *,
    base_time_ms: int,
    batch_seq: int,
    ms_step: int,
    batch_lines: int,
    row_count: int,
) -> List[int]:
    """Compute one timestamp (epoch ms) per row for a single batch.

    Formula (design.md §"时间戳计算公式")::
        ts[i] = base_time + batch_seq * ms_step + i * (ms_step / batch_lines)

    All intermediate arithmetic runs in ``long`` to avoid overflow on
    long-running batches.

    Parameters
    ----------
    base_time_ms:
        Thread-local captured epoch millis.
    batch_seq:
        0-based sequence index of the current batch.
    ms_step:
        Milliseconds between successive batches.
    batch_lines:
        Configured batch size (rows per batch).
    row_count:
        Number of rows to produce. For a non-tail batch this equals
        ``batch_lines``; for the tail it may be smaller.

    Returns
    -------
    List of ``row_count`` integer timestamps.
    """
    if batch_lines <= 0:
        raise PreprocessorHelperError(
            f"batch_lines must be > 0, got {batch_lines}"
        )
    if row_count < 0:
        raise PreprocessorHelperError(
            f"row_count must be >= 0, got {row_count}"
        )
    # Python ints are arbitrary precision ⇒ same overflow protection as
    # Groovy ``long`` at the script emission site.
    base = int(base_time_ms) + int(batch_seq) * int(ms_step)
    intra_step = int(ms_step) // int(batch_lines)
    return [base + i * intra_step for i in range(row_count)]


def calculate_device_number(
    *,
    thread_num: int,
    device_start: int,
    device_per_thread: int,
    row_index: int,
) -> int:
    """Compute device number for a single row.

    Formula (design.md §"线程索引获取方式")::

        device_number = device_start
                       + thread_num * device_per_thread
                       + (row_index % device_per_thread)
    """
    if device_per_thread <= 0:
        raise PreprocessorHelperError(
            f"device_per_thread must be > 0, got {device_per_thread}"
        )
    if row_index < 0:
        raise PreprocessorHelperError(
            f"row_index must be >= 0, got {row_index}"
        )
    return (
        int(device_start)
        + int(thread_num) * int(device_per_thread)
        + (int(row_index) % int(device_per_thread))
    )


def build_device_identifier(device_number: int) -> str:
    """Format device number as the identifier that replaces ``${device_code}``."""
    return f"device_{device_number}"


def clone_rows(rows: Sequence[Sequence[Any]]) -> List[List[Any]]:
    """Shallow-clone each row so mutations do not leak back to the source."""
    return [list(row) for row in rows]


# ---------------------------------------------------------------------------
# Groovy source-form helpers (string snippets embedded in scripts).
# All arithmetic in Groovy is coerced to ``long`` (closes review.md §1 阻塞项 #1).
# ---------------------------------------------------------------------------

def groovy_calculate_timestamps_decl() -> str:
    """Groovy source for timestamp calc matching :func:`calculate_timestamps`."""
    return (
        "def calculateTimestamps(long base_time_ms, long batch_seq, "
        "long ms_step, long batch_lines, int row_count) {\n"
        "    if (batch_lines <= 0L) { throw new RuntimeException("
        "'batch_lines must be > 0: ' + batch_lines) }\n"
        "    if (row_count < 0) { throw new RuntimeException("
        "'row_count must be >= 0: ' + row_count) }\n"
        "    long intra = ms_step / batch_lines\n"
        "    long base = base_time_ms + batch_seq * ms_step\n"
        "    def out = []\n"
        "    for (int i = 0; i < row_count; i++) { out.add(base + i * intra) }\n"
        "    return out\n"
        "}\n"
    )


def groovy_calculate_device_number_decl() -> str:
    """Groovy source for device number calculation matching :func:`calculate_device_number`."""
    return (
        "long calculateDeviceNumber(long thread_num, long device_start, "
        "long device_per_thread, int row_index) {\n"
        "    if (device_per_thread <= 0L) { throw new RuntimeException("
        "'device_per_thread must be > 0: ' + device_per_thread) }\n"
        "    if (row_index < 0) { throw new RuntimeException("
        "'row_index must be >= 0: ' + row_index) }\n"
        "    return device_start + thread_num * device_per_thread "
        "+ ((long) row_index % device_per_thread)\n"
        "}\n"
    )


def groovy_device_identifier_decl() -> str:
    """Groovy source for device identifier formatting."""
    return (
        "def deviceIdentifier(long device_number) {\n"
        "    return 'device_' + device_number\n"
        "}\n"
    )


def groovy_clone_rows_decl() -> str:
    """Groovy source for clone_rows matching :func:`clone_rows`."""
    return (
        "def cloneRows(def rows) {\n"
        "    def out = []\n"
        "    rows.each { row -> out.add(new ArrayList(row)) }\n"
        "    return out\n"
        "}\n"
    )


def groovy_calculate_local_device_start_decl() -> str:
    """Groovy source for thread-local device-start calculation.

    Companion to :func:`groovy_calculate_device_number_decl` — emits the
    simpler formula used by ``write_groups`` and ``single_prepared``
    strategies to compute the local base per-thread device number before
    applying the per-row ``row_index % device_per_thread`` offset::

        local_device_start = device_start + thread_num * device_per_thread

    The ``device_per_thread <= 0`` boundary is enforced here so both
    downstream callers share a single point of defence (review §1
    Resolution). OpenSpec tasks §2.1 + §2.5.
    """
    return (
        "long calculateLocalDeviceStart(long deviceStart, int threadNum, "
        "long devicePerThread) {\n"
        "    if (devicePerThread <= 0L) { throw new RuntimeException("
        "'devicePerThread must be > 0: ' + devicePerThread) }\n"
        "    return deviceStart + (long) threadNum * devicePerThread\n"
        "}\n"
    )


def all_groovy_decls() -> str:
    """Concatenate all helper declarations for embedding in a Groovy script.

    Only helpers that current generators call are injected here. Helpers
    kept as Python-only (e.g. :func:`calculate_timestamps`) remain
    importable for callers that want to replicate the Groovy logic in
    Python tests, but are not embedded into generated JMX scripts.
    """
    return "\n".join(
        [
            groovy_calculate_device_number_decl(),
            groovy_device_identifier_decl(),
            groovy_clone_rows_decl(),
            groovy_calculate_local_device_start_decl(),
        ]
    )


# ---------------------------------------------------------------------------
# write-missing-data D10: 缺失判定 helper(Python / Groovy 同构)
# ---------------------------------------------------------------------------


def should_skip_row(
    device_idx: int,
    ts_idx: int,
    *,
    missing_device_count: int,
    missing_ts_count: int,
    device_per_thread: int,
    batch_lines: int,
) -> bool:
    """Whether one grid cell is skipped by the missing-data rule.

    Tail truncation per dimension, combined by intersection (design.md D1)::

        device_missing_hit = device_idx >= device_per_thread - missing_device_count
        ts_missing_hit     = ts_idx >= batch_lines - missing_ts_count
        skip = device_missing_hit && ts_missing_hit

    A dimension whose count is ``0`` is not configured and does not take
    part in the decision; both ``0`` → nothing is dropped.

    Indices are **round-relative** (``device_idx`` = position inside this
    round's grid), never absolute device numbers.
    """
    missing_device_and_ts = missing_device_count > 0 and missing_ts_count > 0
    missing_device_only = missing_device_count > 0 and missing_ts_count == 0
    missing_ts_only = missing_ts_count > 0 and missing_device_count == 0
    if missing_device_and_ts:
        return (
            device_idx >= device_per_thread - missing_device_count
            and ts_idx >= batch_lines - missing_ts_count
        )
    if missing_device_only:
        return device_idx >= device_per_thread - missing_device_count
    if missing_ts_only:
        return ts_idx >= batch_lines - missing_ts_count
    return False


def groovy_missing_data_decl(
    *,
    probability: float,
    missing_ts_count: int,
    missing_device_count: int,
) -> str:
    """Groovy source for the missing-data block injected at the 6 write sites.

    Declares ``missingProbability`` / ``missingTsCount`` /
    ``missingDeviceCount`` (the baked-in config), ``applyMissing`` (the
    per-batch Bernoulli draw, D2) and the ``skipMissingRow`` closure
    implementing the same intersection rule as :func:`should_skip_row`.

    Only the **configured** dimensions appear in the closure (a count of
    ``0`` means "not configured"); the closure reads the script-local
    ``devicePerThread`` / ``batchLines``, so a device count shrunk at
    runtime yields a non-positive threshold — every device then hits and
    the timestamp dimension alone decides (D7).
    """
    missing_device_and_ts = missing_device_count > 0 and missing_ts_count > 0
    missing_device_only = missing_device_count > 0 and missing_ts_count == 0
    missing_ts_only = missing_ts_count > 0 and missing_device_count == 0
    parts = [
        "// write-missing-data: 尾部截断(设备 × 时间戳,取交集)",
        f"def missingProbability = {probability!r}d",
        f"def missingTsCount = {int(missing_ts_count)}",
        f"def missingDeviceCount = {int(missing_device_count)}",
        "def applyMissing = false",
        "if (missingProbability == 1.0d) {",
        "    applyMissing = true",
        "} else {",
        "    applyMissing = java.util.concurrent.ThreadLocalRandom.current()"
        ".nextDouble() < missingProbability",
        "}",
        "def skipMissingRow = { int devIdx, int tsIdx ->",
    ]
    if missing_device_and_ts or missing_device_only:
        parts.append(
            "    boolean deviceMissingHit = devIdx >= devicePerThread - missingDeviceCount"
        )
    if missing_device_and_ts or missing_ts_only:
        parts.append("    boolean tsMissingHit = tsIdx >= batchLines - missingTsCount")
    if missing_device_and_ts:
        parts.append("    return deviceMissingHit && tsMissingHit")
    elif missing_device_only:
        parts.append("    return deviceMissingHit")
    elif missing_ts_only:
        parts.append("    return tsMissingHit")
    else:
        parts.append("    return false")
    parts.append("}")
    return "\n".join(parts)


def groovy_missing_data_block(missing: Any) -> str:
    """Missing-data block for embedding — empty string when disabled.

    Design D6: the block is injected **only** when the table declares a
    ``missing`` section whose ``probability`` is greater than ``0.0``.
    An absent section and ``probability: 0.0`` both yield ``""``, which
    the generators splice at the end of a line so the surrounding script
    stays byte-identical to the not-declared variant.

    The returned text starts **and** ends with a newline, so it can be
    appended directly to a template line::

        def batchLines = 5{missing_block}def msStep = 1000

    ``missing`` is a :class:`config_parser.models.MissingConfig` (or
    ``None``). It is read duck-typed on purpose — importing the config
    models here would invert the ``utils → config_parser`` layering.
    """
    if missing is None or missing.probability <= 0.0:
        return ""
    return "\n" + groovy_missing_data_decl(
        probability=missing.probability,
        missing_ts_count=missing.ts_count,
        missing_device_count=missing.device_count,
    ) + "\n"


def groovy_missing_skip_line(*, device_start_var: str, ts_var: str) -> str:
    """The per-cell skip line placed at the top of the inner (ts) loop.

    The device index is **round-relative** (``d - <device loop start>``):
    the missing set must be defined on "the devices of *this* round",
    and the absolute device number ``d`` shifts with ``device_start``
    / multi-end coordination, which would make the tail semantics drift.

    ``&&`` short-circuits, so a batch that did not trigger the rule pays
    nothing beyond the boolean check.
    """
    return (
        f"        if (applyMissing && skipMissingRow((int)(d - {device_start_var}), "
        f"{ts_var})) {{ continue }}\n"
    )



