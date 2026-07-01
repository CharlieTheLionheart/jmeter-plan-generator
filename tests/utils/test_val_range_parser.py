"""Tests for val_range_parser utility."""

import re

import pytest

from utils.val_range_parser import ValRangeType, parse_val_range


def test_parse_lower_bound():
    result = parse_val_range(">=10")
    assert result.range_type is ValRangeType.LOWER_EQUAL_BOUND
    assert result.interval.low == 10.0


def test_parse_upper_bound():
    result = parse_val_range("<=100")
    assert result.range_type is ValRangeType.UPPER_EQUAL_BOUND
    assert result.interval.high == 100.0


def test_parse_strict_lower_bound():
    result = parse_val_range(">10")
    assert result.range_type is ValRangeType.LOWER_BOUND
    assert result.interval.low == 10.0
    assert result.interval.low_open is True


def test_parse_strict_upper_bound():
    result = parse_val_range("<100")
    assert result.range_type is ValRangeType.UPPER_BOUND
    assert result.interval.high == 100.0
    assert result.interval.high_open is True


def test_parse_equal_bound():
    result = parse_val_range("=42")
    assert result.range_type is ValRangeType.EQUAL
    assert result.interval.low == 42.0
    assert result.interval.high == 42.0
    assert result.interval.low_open is False
    assert result.interval.high_open is False


def test_parse_closed_interval():
    result = parse_val_range("[1, 100]")
    assert result.range_type is ValRangeType.INTERVAL
    assert result.interval.low == 1.0
    assert result.interval.high == 100.0
    assert not result.interval.low_open
    assert not result.interval.high_open


def test_parse_open_interval():
    result = parse_val_range("(1, 100)")
    assert result.interval.low_open
    assert result.interval.high_open


def test_parse_half_open_interval():
    result = parse_val_range("[1, 100)")
    assert not result.interval.low_open
    assert result.interval.high_open


def test_parse_regex():
    result = parse_val_range(r"^[a-z]+$")
    assert result.range_type is ValRangeType.REGEX
    assert result.regex_pattern == r"^[a-z]+$"


def test_parse_invalid_regex():
    with pytest.raises(ValueError):
        parse_val_range(r"[invalid(")


def test_parse_enum():
    result = parse_val_range("enum:M1,M2,M3")
    assert result.range_type is ValRangeType.ENUM
    assert result.enum_values == ["M1", "M2", "M3"]


def test_parse_empty_enum():
    with pytest.raises(ValueError):
        parse_val_range("enum:")


def test_parse_foreign_key():
    result = parse_val_range("ref:iot_metadata.t_workshop.pk_int8_1")
    assert result.range_type is ValRangeType.FOREIGN_KEY
    assert result.foreign_key == "ref:iot_metadata.t_workshop.pk_int8_1"


def test_parse_malformed_foreign_key():
    with pytest.raises(ValueError):
        parse_val_range("ref:missing_parts")


def test_parse_empty():
    with pytest.raises(ValueError):
        parse_val_range("")
