"""JSR223PreProcessor Groovy helper functions for write-side data assembly.

Design: openspec/changes/direct-insert-write/design.md

These helpers translate to Groovy source snippets embedded in JSR223PreProcessor
scripts (see ``direct_insert_write.preprocessor_generator``). The Python
implementations here exist so callers can unit-test the same algorithms without
bootstrapping a JMeter/JVM runtime.

Four helpers are exposed (names aligned with tasks.md §0.5 / §4):

- :func:`calculate_timestamps` — per-row timestamp list given base, batch
  sequence, ms_step, batch_lines.
- :func:`calculate_device_number` — device number from thread index,
  device_start, device_per_thread, and per-row index.
- :func:`build_device_identifier` — formats ``device_{n}``.
- :func:`clone_rows` — shallow per-row list clone.

Numeric type policy (closes review.md §1 阻塞项 #1):

- All timestamp and device-number arithmetic uses **Python ``int``** and
  emits **Groovy ``long``** at runtime to avoid ``batch_seq * ms_step``
  overflow on long runs.
- Inter-timestamp step uses integer division (``ms_step // batch_lines``).
  When ``ms_step < batch_lines`` the per-row intra-step rounds to 0;
  callers wanting finer intra-batch separation should ensure
  ``ms_step >= batch_lines``.

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
    """Concatenate all helper declarations for embedding in a Groovy script."""
    return "\n".join(
        [
            groovy_calculate_timestamps_decl(),
            groovy_calculate_device_number_decl(),
            groovy_device_identifier_decl(),
            groovy_clone_rows_decl(),
            groovy_calculate_local_device_start_decl(),
        ]
    )
