"""Internal implementations for :mod:`throughput_control`.

Two thin wrappers over :func:`utils.xml_helpers.constant_throughput_timer_element`:

- write timer → embeds the literal numeric value from the per-table
  ``WriteConfig.throughput`` cfg field (no JMeter UDV variable)
- query timer → embeds the literal numeric value from
  ``QueryConfig.throughput``

Both timers pin ``calcMode=0`` (per-thread targeting). Throughput
values are baked into the JMX as string literals at generation time;
the operator edits ``cfg.write_config[].throughput`` (or
``cfg.query_config[].throughput``) and re-runs ``python -m
kwjdbc_svt.main`` to retune.
"""

from __future__ import annotations

from typing import Tuple

from utils.xml_helpers import constant_throughput_timer_element


def _throughput_text(throughput: float) -> str:
    """Render a float as the string form JMeter's ConstantThroughputTimer accepts.

    Integer-valued floats render without the trailing ``.0`` (so
    ``4.0`` → ``"4"``); non-integer floats render with full precision
    via ``repr`` (so ``0.016666667`` → ``"0.016666667"``).
    """
    if throughput == int(throughput):
        return str(int(throughput))
    return repr(throughput)


def generate_write_timer(
    throughput: float,
    name: str = "Constant Throughput Timer",
    *,
    testname: str = "Constant Throughput Timer",
) -> Tuple:
    """Emit the write-thread ``ConstantThroughputTimer``.

    The timer's ``throughput`` attribute is the literal string form of
    the per-table ``WriteConfig.throughput`` cfg value (samples per
    minute, per-thread). No JMeter UDV is involved — the value is
    baked at generation time.
    """
    return constant_throughput_timer_element(
        name=name,
        throughput=_throughput_text(throughput),
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
    return constant_throughput_timer_element(
        name=name,
        throughput=_throughput_text(query_throughput),
        calc_mode=0,
        testname=testname,
    )