"""Tests for TsTableConfig.sparse flag and data_col_count cap enforcement.

sparse (KaiwuDB 2.4.1+): emit ``create sparse table`` and raise the
data_col_count cap from 4096 to 20000. The cap is enforced at parse time
so misconfigured fixtures fail before JMX emission.
"""

import pytest
from pydantic import ValidationError

from config_parser.models import (
    ColTypeConfig,
    PrimaryTagColTypeConfig,
    TsTableConfig,
)


def _ts_table(**kwargs) -> TsTableConfig:
    return TsTableConfig(
        name="t_sparse",
        data_col_count=kwargs.pop("data_col_count", 1),
        primary_tag_count=1,
        regular_tag_count=0,
        data_cols=kwargs.pop(
            "data_cols", [ColTypeConfig(col_type="int8", type_proportion=1.0)]
        ),
        primary_tags=[PrimaryTagColTypeConfig(col_type="int8", type_proportion=1.0)],
        regular_tags=[],
        **kwargs,
    )


def test_sparse_defaults_to_false():
    table = _ts_table()
    assert table.sparse is False


def test_regular_cap_4096_ok():
    table = _ts_table(sparse=False, data_col_count=4096)
    assert table.data_col_count == 4096


def test_regular_cap_4097_rejected():
    with pytest.raises(ValidationError) as exc:
        _ts_table(sparse=False, data_col_count=4097)
    assert "regular cap 4096" in str(exc.value)


def test_sparse_cap_20000_ok():
    table = _ts_table(sparse=True, data_col_count=20000)
    assert table.data_col_count == 20000
    assert table.sparse is True


def test_sparse_cap_20001_rejected():
    with pytest.raises(ValidationError) as exc:
        _ts_table(sparse=True, data_col_count=20001)
    assert "sparse cap 20000" in str(exc.value)


def test_sparse_coexists_with_other_options():
    table = _ts_table(
        sparse=True,
        with_hash=64,
        retentions="5d",
        comment="sparse 表",
    )
    assert table.sparse is True
    assert table.with_hash == 64
    assert table.retentions == "5d"
    assert table.comment == "sparse 表"


def test_sparse_does_not_enforce_nullable_or_null_rate():
    # Intentional non-coupling: sparse is a column-cap / DDL-keyword flag,
    # not a semantic constraint on column nullability.
    table = _ts_table(
        sparse=True,
        data_cols=[
            ColTypeConfig(
                col_type="int8", type_proportion=1.0, nullable=False, null_rate=0.0
            )
        ],
    )
    assert table.sparse is True
    assert table.data_cols[0].nullable is False
    assert table.data_cols[0].null_rate == 0.0
