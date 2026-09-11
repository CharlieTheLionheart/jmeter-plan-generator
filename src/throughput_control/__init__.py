"""Throughput timer generators.

Design: openspec/changes/throughput-control/design.md

Two consumers, both embedding cfg literals (no JMeter UDV):

- :func:`generate_write_timer` — emit a ``ConstantThroughputTimer`` whose
  ``throughput`` attribute is the literal string form of the per-table
  ``WriteConfig.throughput`` cfg value (samples per minute, per-thread).
  The caller must pass the throughput explicitly — there is no
  process-wide default.
- :func:`generate_query_timer` — same shape, but the throughput comes
  from ``QueryConfig.throughput`` and each query gets its own literal.

The two functions never consult a multi-end config nor split throughput
across ends; multi-end coordination is the caller's responsibility
(see design.md §"Multi-end coordination: NO-OP").
"""

from throughput_control.throughput_timer_generator import (
    generate_query_timer,
    generate_write_timer,
)

__all__ = [
    "generate_query_timer",
    "generate_write_timer",
]