"""Throughput timer generators.

Design: openspec/changes/throughput-control/design.md

Two consumers:

- :func:`generate_write_timer` — emit a ``ConstantThroughputTimer`` that
  references the JMeter UDV variable ``${write_throughput}``. The UDV
  itself is populated by
  :func:`jmx_skeleton_generator.generators.test_plan.generate_user_defined_variables`
  with a default value of :data:`DEFAULT_WRITE_THROUGHPUT` (120
  samples per minute).
- :func:`generate_query_timer` — emit a ``ConstantThroughputTimer`` that
  carries the literal numeric throughput from ``QueryConfig.throughput``
  (no JMeter variable). Each query gets its own literal value.

The two functions never consult a multi-end config nor split throughput
across ends; multi-end coordination is the caller's responsibility
(see design.md §"Multi-end coordination: NO-OP").
"""

from throughput_control.throughput_timer_generator import (
    DEFAULT_WRITE_THROUGHPUT,
    generate_query_timer,
    generate_write_timer,
)

__all__ = [
    "DEFAULT_WRITE_THROUGHPUT",
    "generate_query_timer",
    "generate_write_timer",
]
