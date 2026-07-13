"""Internal implementations for :mod:`throughput_control`.

Two thin wrappers over :func:`utils.xml_helpers.constant_throughput_timer_element`:

- write timer → references the UDV variable ``${write_throughput}``
- query timer → embeds the literal numeric value

Both timers pin ``calcMode=0`` (per-thread targeting); the
:data:`DEFAULT_WRITE_THROUGHPUT` constant holds the JMeter-native
``samples per minute`` default applied by the UDV generator.
"""

from __future__ import annotations

from typing import Tuple

from utils.xml_helpers import constant_throughput_timer_element

#: Default value injected into the ``${write_throughput}`` UDV
#: (samples per minute). 120 = 2 samples per second per thread.
DEFAULT_WRITE_THROUGHPUT: float = 120.0


def generate_write_timer(
    name: str = "Constant Throughput Timer",
    *,
    testname: str = "Constant Throughput Timer",
) -> Tuple:
    """Emit the write-thread ``ConstantThroughputTimer``.

    The timer's ``throughput`` attribute is the JMeter variable
    reference ``${write_throughput}``, defined by
    :func:`generate_user_defined_variables` with
    :data:`DEFAULT_WRITE_THROUGHPUT` as default.
    """
    return constant_throughput_timer_element(
        name=name,
        throughput="${write_throughput}",
        calc_mode=0,
        testname=testname,
    )


def generate_query_timer(
    query_throughput: float,
    name: str = "Constant Throughput Timer",
    *,
    testname: str = "Constant Throughput Timer",
) -> Tuple:
    """Emit the query-thread ``ConstantThroughputTimer``.

    The timer's ``throughput`` attribute is the literal numeric value
    of ``QueryConfig.throughput`` (no ``${...}`` wrapping). Different
    queries receive different literals — they do not share a UDV.

    Integer-valued floats render without the trailing ``.0`` (so
    ``4.0`` → ``"4"``); non-integer floats render with full precision
    via ``repr`` (so ``0.016666667`` → ``"0.016666667"``).
    """
    if query_throughput == int(query_throughput):
        throughput_text = str(int(query_throughput))
    else:
        throughput_text = repr(query_throughput)
    return constant_throughput_timer_element(
        name=name,
        throughput=throughput_text,
        calc_mode=0,
        testname=testname,
    )
