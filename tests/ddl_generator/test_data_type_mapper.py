"""Tests for DataTypeMapper."""

import pytest

from ddl_generator import DataTypeMapper
from ddl_generator.data_type_mapper import UnsupportedDataTypeError


def test_map_int8():
    assert DataTypeMapper.map("int8") == "int8"


def test_map_varchar():
    assert DataTypeMapper.map("VARCHAR(16)") == "varchar(16)"


def test_map_timestamptz():
    assert DataTypeMapper.map("TIMESTAMPTZ") == "timestamptz"


def test_map_decimal_preserves_precision_scale():
    """D-9 (2026-08-11): spec §403 列 decimal/numeric 为支持类型 — mapper 应原样返回小写 + 修饰符。

    历史坑: SUPPORTED_BASE_TYPES 未含 ``decimal`` / ``numeric``,
    fixture 写 ``col_type: decimal(10,2)`` 报
    ``UnsupportedDataTypeError: decimal(10,2)``。
    """
    assert DataTypeMapper.map("decimal(10,2)") == "decimal(10,2)"
    assert DataTypeMapper.map("DECIMAL(18, 4)") == "decimal(18, 4)"


def test_map_numeric_alias():
    """``numeric`` 是 ``decimal`` 的 SQL 标准别名。"""
    assert DataTypeMapper.map("numeric") == "numeric"
    assert DataTypeMapper.map("NUMERIC(20, 6)") == "numeric(20, 6)"


def test_is_supported_decimal_numeric():
    assert DataTypeMapper.is_supported("decimal") is True
    assert DataTypeMapper.is_supported("decimal(10,2)") is True
    assert DataTypeMapper.is_supported("numeric(20,6)") is True


def test_map_unknown_type():
    with pytest.raises(UnsupportedDataTypeError, match="unsupported data type"):
        DataTypeMapper.map("xml")


def test_is_supported():
    assert DataTypeMapper.is_supported("varchar(64)") is True
    assert DataTypeMapper.is_supported("jsonb") is False
