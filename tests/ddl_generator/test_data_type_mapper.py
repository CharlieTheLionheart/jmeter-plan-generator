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


def test_map_unknown_type():
    with pytest.raises(UnsupportedDataTypeError, match="unsupported data type"):
        DataTypeMapper.map("xml")


def test_is_supported():
    assert DataTypeMapper.is_supported("varchar(64)") is True
    assert DataTypeMapper.is_supported("jsonb") is False
