"""Tests for table-level ColumnNamer."""

from config_parser.models import ColTypeConfig, PrimaryTagColTypeConfig, RelTableConfig, TsTableConfig
from column_namer import ColumnNamer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_rel_table() -> RelTableConfig:
    """RelTableConfig supports: primary_keys, data_cols (not primary_tags/regular_tags)."""
    return RelTableConfig(
        name="t_rel",
        primary_key_count=2,
        data_col_count=5,
        primary_keys=[
            ColTypeConfig(col_type="int8", type_proportion=0.5),
            ColTypeConfig(col_type="int8", type_proportion=0.5),
        ],
        data_cols=[
            ColTypeConfig(col_type="int8", type_proportion=0.4),
            ColTypeConfig(col_type="varchar(64)", type_proportion=0.6),
        ],
    )


def _make_ts_table() -> TsTableConfig:
    """TsTableConfig supports: primary_tags, regular_tags, data_cols (not primary_keys)."""
    return TsTableConfig(
        name="t_workshop",
        data_col_count=5,
        primary_tag_count=2,
        regular_tag_count=1,
        data_cols=[
            ColTypeConfig(col_type="int8", type_proportion=0.4),
            ColTypeConfig(col_type="varchar(64)", type_proportion=0.6),
        ],
        primary_tags=[
            PrimaryTagColTypeConfig(col_type="varchar(32)", type_proportion=0.5),
            PrimaryTagColTypeConfig(col_type="varchar(32)", type_proportion=0.5),
        ],
        regular_tags=[
            ColTypeConfig(col_type="int8", type_proportion=1.0),
        ],
    )


# ---------------------------------------------------------------------------
# RelTableConfig tests
# ---------------------------------------------------------------------------

def test_rel_table_names():
    namer = ColumnNamer(_make_rel_table())
    names = namer.names
    # GROUP_ORDER: primary_keys first (2), then data_cols (5) → total 7
    assert len(names) == 7
    assert names[0].startswith("pk_")
    assert names[1].startswith("pk_")
    assert names[2].startswith("col_")


def test_rel_table_index_map():
    namer = ColumnNamer(_make_rel_table())
    index_map = namer.index_map
    # primary_keys first (2 cols), then data_cols (5 cols)
    assert index_map["pk_int8_1"] == 1
    assert index_map["pk_int8_2"] == 2
    assert index_map["col_int8_1"] == 3
    assert index_map["col_varchar_3"] == 7


def test_rel_table_sequential_indices():
    namer = ColumnNamer(_make_rel_table())
    indices = sorted(namer.index_map.values())
    assert indices == list(range(1, len(namer.names) + 1))


# ---------------------------------------------------------------------------
# TsTableConfig tests
# ---------------------------------------------------------------------------

def test_ts_table_names():
    namer = ColumnNamer(_make_ts_table())
    names = namer.names
    # GROUP_ORDER: primary_keys skipped (empty), data_cols first (5),
    # then primary_tags (2), then regular_tags (1) → total 8
    assert len(names) == 8
    assert names[0].startswith("col_")
    assert names[5].startswith("ptag_")
    assert names[7].startswith("rtag_")


def test_ts_table_index_map():
    namer = ColumnNamer(_make_ts_table())
    index_map = namer.index_map
    # data_cols first (5 cols), then primary_tags (2 cols), then regular_tags (1 col)
    assert index_map["col_int8_1"] == 1
    assert index_map["col_varchar_3"] == 5
    assert index_map["ptag_varchar_1"] == 6
    assert index_map["rtag_int8_1"] == 8


def test_ts_table_sequential_indices():
    namer = ColumnNamer(_make_ts_table())
    indices = sorted(namer.index_map.values())
    assert indices == list(range(1, len(namer.names) + 1))


def test_large_column_count():
    """TsTableConfig with only data_cols, primary_tag_count=0, regular_tag_count=0."""
    table = TsTableConfig(
        name="t_big",
        data_col_count=10000,
        primary_tag_count=0,
        regular_tag_count=0,
        data_cols=[
            ColTypeConfig(col_type="int8", type_proportion=0.5),
            ColTypeConfig(col_type="varchar(64)", type_proportion=0.5),
        ],
    )
    namer = ColumnNamer(table)
    assert len(namer.names) == 10000
    assert namer.index_map["col_varchar_5000"] == 10000
