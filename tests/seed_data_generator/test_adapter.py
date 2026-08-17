"""Tests for the val_range adapter."""

from __future__ import annotations

import pytest

from seed_data_generator.adapter import DomainKind, SeedGenError, classify_val_range


def test_lower_bound_integer():
    domain = classify_val_range("int8", ">=1")
    assert domain.kind is DomainKind.NUMERIC
    assert domain.is_integer is True
    assert domain.low == 1
    assert domain.high is None or domain.high == pytest.approx(float("inf"))
    assert domain.low_inclusive is True


def test_upper_bound_integer():
    domain = classify_val_range("int8", "<=100")
    assert domain.is_integer is True
    assert domain.high == 100
    assert domain.high_inclusive is True


def test_closed_interval_integer():
    domain = classify_val_range("int8", "[1,100]")
    assert domain.low == 1
    assert domain.high == 100
    assert domain.low_inclusive is True
    assert domain.high_inclusive is True


def test_open_interval_integer():
    domain = classify_val_range("int8", "(1,100)")
    assert domain.low == 2
    assert domain.high == 99


def test_float_domain():
    domain = classify_val_range("float8", ">=0.0")
    assert domain.is_integer is False
    assert domain.precision == 2
    assert domain.low == pytest.approx(0.0)


def test_enum_domain():
    domain = classify_val_range("varchar(16)", "enum:M1,M2,M3")
    assert domain.kind is DomainKind.ENUM
    assert domain.enum_values == ["M1", "M2", "M3"]


def test_regex_domain():
    domain = classify_val_range("varchar(16)", "^[a-z]{2,10}$")
    assert domain.kind is DomainKind.REGEX
    assert domain.regex_pattern == "^[a-z]{2,10}$"


def test_foreign_key_domain():
    domain = classify_val_range("int8", "ref:iot_metadata.t_workshop.pk_int8_1")
    assert domain.kind is DomainKind.FOREIGN_KEY
    assert domain.foreign_key == "ref:iot_metadata.t_workshop.pk_int8_1"


def test_numeric_val_range_on_string_type_rejected():
    with pytest.raises(SeedGenError, match="numeric val_range is not supported"):
        classify_val_range("varchar(16)", "[1,10]")


def test_regex_val_range_on_numeric_type_rejected():
    with pytest.raises(SeedGenError, match="regex val_range is not supported"):
        classify_val_range("int8", "^[0-9]+$")


def test_decimal_float_interval_accepted():
    """spec §403 列 decimal 为支持类型 — adapter 应识别为 numeric。

    历史坑: 生成器只把 int/float 加入 _FLOAT_TYPES，decimal/numeric 被
    误判成非 numeric，numeric range 抛 SeedGenError。修复后 decimal
    按 float 路径走（is_integer=False, precision=2）。
    """
    domain = classify_val_range("decimal", "[0.0, 1000.0]")
    assert domain.kind is DomainKind.NUMERIC
    assert domain.is_integer is False
    assert domain.precision == 2
    assert domain.low == pytest.approx(0.0)
    assert domain.high == pytest.approx(1000.0)
    assert domain.low_inclusive is True
    assert domain.high_inclusive is True


def test_numeric_alias_float_interval_accepted():
    """``numeric`` 是 KaiwuDB decimal 的 SQL 标准别名（同为 arbitrary precision）。"""
    domain = classify_val_range("numeric", "(0.0, 100.0)")
    assert domain.kind is DomainKind.NUMERIC
    assert domain.is_integer is False
    assert domain.precision == 2
    assert domain.low_inclusive is False
    assert domain.high_inclusive is False


def test_decimal_parens_ignored_in_base_type():
    """``decimal(10,2)`` 形参应被 _base_type 切到 'decimal'，与 decimal 同路径。"""
    domain = classify_val_range("decimal(10,2)", "[0.0, 9999.99]")
    assert domain.kind is DomainKind.NUMERIC
    assert domain.is_integer is False


def test_missing_val_range_rejected():
    with pytest.raises(SeedGenError, match="val_range is required"):
        classify_val_range("int8", None)
