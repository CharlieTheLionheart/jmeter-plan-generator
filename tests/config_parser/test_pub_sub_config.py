"""Tests for ``PubSubConfig`` + ``PublicationTableEntry`` + cross-ref validator.

Per OpenSpec change ``pub-sub-end-to-end`` (2026-10-12):
- ``PubSubConfig`` is an optional ``TestConfig`` field; presence = enabled.
- ``subscriber_db`` is hard-coded to ``f"{publisher_db}_sub"`` (not a field).
- ``options.target`` is required (同集群两库 D5 锁定).
- Cross-ref rules (``publisher_db`` ∈ ts_dbs, ``tables[i].name`` ∈ ts_tables,
  ``columns`` ⊆ column set + must include all primary_tags) live in a
  **separate** post-load validator
  ``validate_pub_sub_refs(test_model, test_config) -> None``, NOT inside
  Pydantic ``@model_validator``s. This is structurally required: Pydantic
  cannot cross-reference ``TestModelConfig`` from inside ``PubSubConfig``
  model validators because the two models are loaded from separate YAML
  files (``test_model.yaml`` and ``test_cfg.yaml``).

  ``validate_pub_sub_refs`` is **independent of** ``validate_foreign_key_refs``:

  - ``validate_foreign_key_refs`` handles ``col.val_range: "ref:db.table.column"``
    cross-db references (rel_db primary_key → ts_table regular_tag val_range),
    used by seed_data_generator.
  - ``validate_pub_sub_refs`` checks ts_table **自身属性存在性** for
    ``pub_sub_config`` — ``publisher_db`` / ``tables[i].name`` /
    ``tables[i].columns`` existence within ``TestModelConfig.ts_dbs``, plus
    ``columns`` covering all of the table's ``primary_tags`` (which is a
    KaiwuDB ts_table 内置主键概念, NOT a relational foreign-key reference).
    No cross-db / val_range / foreign-key relationship is involved.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from config_parser.models import (
    ColTypeConfig,
    PrimaryTagColTypeConfig,
    PubSubConfig,
    PublicationTableEntry,
    TestConfig,
    TestModelConfig,
    TsColConfig,
    TsDbConfig,
    TsTableConfig,
    validate_pub_sub_refs,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal valid fixtures for TestModelConfig / TestConfig
# ---------------------------------------------------------------------------

def _build_minimal_ts_table(
    *,
    name: str = "t_cnc",
    primary_tag_col_types: tuple[str, ...] = ("int4", "varchar(32)"),
    regular_tag_col_types: tuple[str, ...] = ("int4",),
    data_col_types: tuple[str, ...] = ("float8",),
    ts_col_name: str = "ts",
) -> TsTableConfig:
    """Build a minimal ``TsTableConfig`` with predictable ``col_type`` lists.

    Per-group ``col_type`` tuples drive the **shape** of column names
    ``column_namer`` will eventually produce: the resulting names follow
    ``{prefix}_{normalize_type(col_type)}_{sequence}`` for the three
    groups (prefix ∈ {col, rtag, ptag}), plus the user-configured
    ``ts_col.name`` (default ``ts``). Tests that need to assert
    column-name-shape behaviour call this fixture with specific
    ``col_type`` tuples and then submit column names whose
    ``normalize_type`` parts must come from the union of these tuples.

    ``type_proportion`` is split equally across each group's ``col_type``
    list so ``TsTableConfig.check_type_proportions`` (sum-to-1.0
    constraint) always passes regardless of how many ``col_type``s the
    test passes in.
    """
    def _split_proportions(types: tuple[str, ...]) -> list[float]:
        n = len(types)
        if n == 0:
            return []
        return [1.0 / n] * n

    return TsTableConfig(
        name=name,
        primary_tag_count=len(primary_tag_col_types),
        regular_tag_count=len(regular_tag_col_types),
        data_col_count=len(data_col_types),
        primary_tags=[
            PrimaryTagColTypeConfig(col_type=ct, type_proportion=p)
            for ct, p in zip(primary_tag_col_types, _split_proportions(primary_tag_col_types))
        ],
        regular_tags=[
            ColTypeConfig(col_type=ct, type_proportion=p)
            for ct, p in zip(regular_tag_col_types, _split_proportions(regular_tag_col_types))
        ],
        data_cols=[
            ColTypeConfig(col_type=ct, type_proportion=p)
            for ct, p in zip(data_col_types, _split_proportions(data_col_types))
        ],
        ts_col=TsColConfig(name=ts_col_name, type="timestamp", ms_step=1000),
    )


def _build_test_model(
    *,
    db_name: str = "iot_monitor",
    table: TsTableConfig | None = None,
) -> TestModelConfig:
    """Build a minimal ``TestModelConfig`` with one ts db + one table."""
    return TestModelConfig(ts_dbs=[TsDbConfig(name=db_name, tables=[table or _build_minimal_ts_table()])])


def _build_minimal_pubsub(
    *,
    publisher_db: str = "iot_monitor",
    tables: list[PublicationTableEntry] | None = None,
    options: dict[str, str] | None = None,
    expected_min_rows: int | None = None,
    conninfo: str = "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
) -> PubSubConfig:
    """Build a minimal ``PubSubConfig`` that passes self-consistent validation."""
    if options is None:
        options = {"target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc"}
    return PubSubConfig(
        publisher_db=publisher_db,
        publication_name="pub_iot",
        subscription_name="sub_iot",
        conninfo=conninfo,
        tables=tables,
        options=options,
        expected_min_rows=expected_min_rows,
    )


# ---------------------------------------------------------------------------
# PubSubConfig — field shape (7 fields per design.md)
# ---------------------------------------------------------------------------

class TestPubSubConfigFields:
    """All 7 fields construct and persist as documented in design.md."""

    def test_minimal_construct_7_fields(self) -> None:
        """7 required/defaulted fields round-trip through Pydantic."""
        cfg = _build_minimal_pubsub()
        assert cfg.publisher_db == "iot_monitor"
        assert cfg.publication_name == "pub_iot"
        assert cfg.subscription_name == "sub_iot"
        assert cfg.conninfo.startswith("postgresql://")
        assert cfg.tables is None
        assert cfg.options == {"target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc"}
        assert cfg.expected_min_rows is None

    def test_tables_default_none(self) -> None:
        """Omitting ``tables`` → ``None`` (整库模式 marker)."""
        cfg = _build_minimal_pubsub()
        assert cfg.tables is None

    def test_tables_empty_list_accepted(self) -> None:
        """Empty list ``[]`` is treated as 整库模式 (same semantic as ``None``)."""
        cfg = _build_minimal_pubsub(tables=[])
        assert cfg.tables == []

    def test_options_default_none_not_allowed(self) -> None:
        """``options`` is REQUIRED (D5 锁定: ``target`` is the only sync-mapping
        discriminator in the 同集群两库 scenario; omitting the field is a
        configuration error, not a "use defaults" hint)."""
        with pytest.raises(ValidationError) as exc_info:
            PubSubConfig(
                publisher_db="iot_monitor",
                publication_name="pub_iot",
                subscription_name="sub_iot",
                conninfo="postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
            )
        assert "options" in str(exc_info.value)


# ---------------------------------------------------------------------------
# PubSubConfig — Pydantic self-consistent validators
# ---------------------------------------------------------------------------

class TestPubSubConfigValidators:
    """Self-consistent validators — no TestModelConfig required."""

    def test_conninfo_must_start_with_postgresql(self) -> None:
        """``conninfo`` must be a libpq URI; ``jdbc:`` or any other scheme
        is rejected (KaiwuDB server only accepts libpq-format strings)."""
        with pytest.raises(ValidationError) as exc_info:
            _build_minimal_pubsub(
                conninfo="jdbc:kaiwudb://localhost:26257/iot_monitor"
            )
        assert "conninfo" in str(exc_info.value)

    def test_conninfo_non_empty(self) -> None:
        """``conninfo`` must be non-empty (empty string is meaningless)."""
        with pytest.raises(ValidationError) as exc_info:
            _build_minimal_pubsub(conninfo="")
        assert "conninfo" in str(exc_info.value)

    def test_options_target_required(self) -> None:
        """``options.target`` is REQUIRED (D5: only sync-mapping discriminator
        in the 同集群两库 scenario; the server cannot infer
        ``publisher_table → subscriber_table`` without it)."""
        with pytest.raises(ValidationError) as exc_info:
            _build_minimal_pubsub(options={"enable": "on"})
        assert "target" in str(exc_info.value)

    def test_options_target_non_empty(self) -> None:
        """``options.target`` must be non-empty (empty value would emit
        ``WITH OPTIONS (target = )`` which the server rejects)."""
        with pytest.raises(ValidationError) as exc_info:
            _build_minimal_pubsub(options={"target": ""})
        assert "target" in str(exc_info.value)

    def test_options_keys_must_be_in_valid_set(self) -> None:
        """Unknown option keys are rejected (typo guard; the 7 valid keys
        are split into publication-side + subscription-side groups per D1/D8)."""
        with pytest.raises(ValidationError) as exc_info:
            _build_minimal_pubsub(
                options={
                    "target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc",
                    "buffer_szie": "4",  # typo
                }
            )
        assert "buffer_szie" in str(exc_info.value)

    def test_all_valid_option_keys_accepted(self) -> None:
        """All 7 documented option keys are accepted (no typo: publication-side
        ``buffer_size`` / ``retrieve_tags`` / ``publish`` + subscription-side
        ``target`` / ``enable`` / ``ignore_history`` / ``retry``)."""
        cfg = _build_minimal_pubsub(
            options={
                "target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc",
                "buffer_size": "4",
                "retrieve_tags": "true",
                "publish": "insert",
                "enable": "on",
                "ignore_history": "on",
                "retry": "5",
            }
        )
        assert set(cfg.options) == {
            "target", "buffer_size", "retrieve_tags", "publish",
            "enable", "ignore_history", "retry",
        }

    def test_multi_table_forbids_columns(self) -> None:
        """When ``len(tables) > 1``, all ``columns`` MUST be empty / None
        (KaiwuDB pub-sub 文档不支持 multi-table 列子集发布)."""
        with pytest.raises(ValidationError) as exc_info:
            PubSubConfig(
                publisher_db="iot_monitor",
                publication_name="pub_iot",
                subscription_name="sub_iot",
                conninfo="postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
                options={"target": "iot_monitor.t1=iot_monitor_sub.t1"},
                tables=[
                    PublicationTableEntry(name="t_cnc", columns=["col_float8_1"]),
                    PublicationTableEntry(name="t_cnc2"),
                ],
            )
        assert "columns" in str(exc_info.value)

    def test_multi_table_forbids_where(self) -> None:
        """When ``len(tables) > 1``, all ``where`` MUST be empty / None
        (KaiwuDB pub-sub 文档不支持 multi-table WHERE 过滤)."""
        with pytest.raises(ValidationError) as exc_info:
            PubSubConfig(
                publisher_db="iot_monitor",
                publication_name="pub_iot",
                subscription_name="sub_iot",
                conninfo="postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
                options={"target": "iot_monitor.t1=iot_monitor_sub.t1"},
                tables=[
                    PublicationTableEntry(name="t_cnc", where="col_float8_1 > 0"),
                    PublicationTableEntry(name="t_cnc2"),
                ],
            )
        assert "where" in str(exc_info.value)

    def test_single_table_with_columns_accepted(self) -> None:
        """``len(tables) == 1`` with ``columns`` populated is allowed."""
        cfg = _build_minimal_pubsub(
            tables=[PublicationTableEntry(name="t_cnc", columns=["col_float8_1"])],
        )
        assert cfg.tables is not None
        assert cfg.tables[0].columns == ["col_float8_1"]

    def test_single_table_with_where_accepted(self) -> None:
        """``len(tables) == 1`` with ``where`` populated is allowed."""
        cfg = _build_minimal_pubsub(
            tables=[PublicationTableEntry(name="t_cnc", where="col_float8_1 > 0")],
        )
        assert cfg.tables is not None
        assert cfg.tables[0].where == "col_float8_1 > 0"

    def test_expected_min_rows_zero_accepted(self) -> None:
        """``expected_min_rows=0`` is the "恒真" sentinel (WHERE-filtered
        scenarios that legitimately sync zero rows still pass Verify)."""
        cfg = _build_minimal_pubsub(expected_min_rows=0)
        assert cfg.expected_min_rows == 0

    def test_expected_min_rows_negative_rejected(self) -> None:
        """Negative thresholds are nonsense (``count(*) >= -1`` is
        trivially true and hides sync failures)."""
        with pytest.raises(ValidationError) as exc_info:
            _build_minimal_pubsub(expected_min_rows=-1)
        assert "expected_min_rows" in str(exc_info.value)


# ---------------------------------------------------------------------------
# PublicationTableEntry — 3 fields per design.md
# ---------------------------------------------------------------------------

class TestPublicationTableEntry:
    """``PublicationTableEntry`` field shape and self-consistent validators."""

    def test_minimal_name_only(self) -> None:
        """Only ``name`` is required; ``columns`` / ``where`` default to ``None``."""
        entry = PublicationTableEntry(name="t_cnc")
        assert entry.name == "t_cnc"
        assert entry.columns is None
        assert entry.where is None

    def test_with_columns_and_where(self) -> None:
        """All 3 fields populate when supplied."""
        entry = PublicationTableEntry(
            name="t_cnc",
            columns=["col_float8_1"],
            where="col_float8_1 > 0",
        )
        assert entry.name == "t_cnc"
        assert entry.columns == ["col_float8_1"]
        assert entry.where == "col_float8_1 > 0"

    def test_name_non_empty(self) -> None:
        """``name`` must be a non-empty string (per design.md; field validator
        parallels ``TableConfig.name_not_empty``)."""
        with pytest.raises(ValidationError) as exc_info:
            PublicationTableEntry(name="")
        assert "name" in str(exc_info.value)

    def test_columns_rejects_empty_string_element(self) -> None:
        """``columns`` items must be non-empty (no silent ``""`` columns that
        would emit ``FOR TABLE t (col1, , col2)`` SQL)."""
        with pytest.raises(ValidationError) as exc_info:
            PublicationTableEntry(name="t_cnc", columns=["col_float8_1", ""])
        assert "columns" in str(exc_info.value)

    def test_where_rejects_empty_string(self) -> None:
        """``where`` empty string is rejected (``where=""`` is meaningless and
        would emit ``FOR TABLE t WHERE`` syntax error on the server)."""
        with pytest.raises(ValidationError) as exc_info:
            PublicationTableEntry(name="t_cnc", where="")
        assert "where" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestConfig — pub_sub_config 挂载位置
# ---------------------------------------------------------------------------

class TestTestConfigIntegration:
    """``pub_sub_config`` is an optional ``TestConfig`` field; absence = disabled."""

    def test_pub_sub_config_default_none(self) -> None:
        """When the YAML omits the ``pub_sub_config`` block, the field is
        ``None`` (段不存在 = 不启用 per D5 锁定)."""
        cfg = TestConfig.model_validate(
            {"conn_config": {"db_url": "jdbc:kaiwudb://localhost:26257/defaultdb"}}
        )
        assert cfg.pub_sub_config is None

    def test_pub_sub_config_attached_when_provided(self) -> None:
        """When the YAML declares ``pub_sub_config``, the field is a fully
        validated ``PubSubConfig`` instance (not a raw dict)."""
        raw: dict[str, Any] = {
            "conn_config": {"db_url": "jdbc:kaiwudb://localhost:26257/defaultdb"},
            "pub_sub_config": {
                "publisher_db": "iot_monitor",
                "publication_name": "pub_iot",
                "subscription_name": "sub_iot",
                "conninfo": "postgresql://root@localhost:26257/iot_monitor?sslmode=disable",
                "options": {"target": "iot_monitor.t_cnc=iot_monitor_sub.t_cnc"},
            },
        }
        cfg = TestConfig.model_validate(raw)
        assert isinstance(cfg.pub_sub_config, PubSubConfig)
        assert cfg.pub_sub_config.publisher_db == "iot_monitor"


# ---------------------------------------------------------------------------
# validate_pub_sub_refs — cross-ref to TestModelConfig
# ---------------------------------------------------------------------------

def _build_test_config_with_pubsub(pubsub: PubSubConfig) -> TestConfig:
    """Wrap a ``PubSubConfig`` into a minimal ``TestConfig``."""
    return TestConfig(
        conn_config={"db_url": "jdbc:kaiwudb://localhost:26257/defaultdb"},
        pub_sub_config=pubsub,
    )


class TestPubSubCrossRefValidator:
    """``validate_pub_sub_refs(test_model, test_config)`` enforces ts_table
    自身属性存在性 for ``TestConfig.pub_sub_config``.

    **Not** the same as ``validate_foreign_key_refs`` — that one handles
    ``col.val_range: "ref:db.table.column"`` cross-db references (rel_db
    primary_key → ts_table regular_tag val_range), used by
    seed_data_generator. ``validate_pub_sub_refs`` only checks
    ``publisher_db`` / ``tables[i].name`` / ``tables[i].columns``
    column-name shape within ``TestModelConfig.ts_dbs`` —
    no foreign-key / val_range / cross-db reference is involved.

    **Column-name shape check (column_namer-rule based)**: per
    ``column_namer/constants.py`` + ``column_namer/generate.py``,
    DDL-emitted column names follow
    ``{prefix}_{normalized_type}_{sequence}`` where
    ``prefix ∈ {col, rtag, ptag}`` for time-series tables, plus the
    user-configured ``ts_col.name`` (default ``ts``). At config_parser
    stage the **exact** column names are not yet known (column_namer
    runs during JMX generation), but the **shape** is deterministic
    from ``TestModelConfig.ts_dbs`` (per-group prefix + per-column
    ``col_type``) — so we validate the user-supplied column name list
    against that shape instead of against the eventual concrete names.

    Concretely, for each entry in ``tables[i].columns``:
    - the column name must EQUAL ``TsTableConfig.ts_col.name`` (the
      timestamp column), OR
    - must match ``^{col|rtag|ptag}_{normalized_type}_{int}$`` where
      ``normalized_type`` is ``normalize_type(col_type)`` for some
      ``col_type`` declared in the table's primary_tags + regular_tags
      + data_cols.
    - at least one column name must start with ``ptag_`` (spec §2.0:
      ptag is ``nullable=false``, must be included in any column-subset
      publication)."""

    def test_publisher_db_must_exist_in_test_model(self) -> None:
        """``publisher_db`` MUST appear in ``test_model.ts_dbs[*].name``
        (else subscriber / publisher DDL target a non-existent database)."""
        model = _build_test_model(db_name="iot_monitor")
        pubsub = _build_minimal_pubsub(publisher_db="nonexistent_db")
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        assert "nonexistent_db" in str(exc_info.value)

    def test_table_name_must_exist_in_test_model(self) -> None:
        """``tables[i].name`` MUST appear in ``test_model.ts_dbs[*].tables[*].name``
        (else CREATE PUBLICATION FOR TABLE references a missing table)."""
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(name="t_cnc"),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(name="t_nonexistent")],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        assert "t_nonexistent" in str(exc_info.value)

    def test_columns_must_match_column_namer_shape(self) -> None:
        """``tables[i].columns`` elements MUST match the column_namer-rule
        shape ``^{col|rtag|ptag}_{normalize_type(col_type)}_{int}$`` —
        else CREATE PUBLICATION FOR TABLE (col) emits an unparseable SQL
        identifier (KaiwuDB rejects the publication). The exact column
        names are only known at JMX generation time, so the check is
        shape-based, not name-based.
        """
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                primary_tag_col_types=("int4", "varchar(32)"),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                # "ghost_col" does not match the column_namer pattern at
                # all (no col_/rtag_/ptag_ prefix).
                columns=["ptag_int4_1", "col_float8_1", "ghost_col"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        assert "ghost_col" in str(exc_info.value)

    def test_columns_unknown_type_rejected(self) -> None:
        """Column names with a valid prefix but an unknown ``normalize_type``
        are rejected — the ``col_type`` part must come from the table's
        declared primary_tags + regular_tags + data_cols ``col_type`` list
        (after ``normalize_type``)."""
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                primary_tag_col_types=("int4",),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                # "col_xxx_1" has the right shape but xxx is not a declared
                # col_type (the table only declares int4 + float8).
                columns=["ptag_int4_1", "col_xxx_1"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        assert "col_xxx_1" in str(exc_info.value)

    def test_columns_unknown_prefix_rejected(self) -> None:
        """A column name with a typo'd prefix (e.g. ``colx_float8_1``) is
        rejected — the prefix must be one of the three ts-table prefixes
        (``col`` / ``rtag`` / ``ptag``), or the configured ``ts_col.name``."""
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                primary_tag_col_types=("int4",),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                columns=["ptag_int4_1", "colx_float8_1"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        assert "colx_float8_1" in str(exc_info.value)

    def test_columns_missing_sequence_rejected(self) -> None:
        """A column name without the trailing ``_{int}`` sequence is
        rejected — column_namer always appends ``_{sequence}``."""
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                primary_tag_col_types=("int4",),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                columns=["ptag_int4_1", "col_float8"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        assert "col_float8" in str(exc_info.value)

    def test_columns_must_include_all_ptag_types(self) -> None:
        """``tables[i].columns`` MUST cover EVERY declared ``primary_tag``
        ``col_type`` with at least one matching ``ptag_{type}_{seq}`` name.

        ptag is a 联合主键 (composite primary key) for KaiwuDB ts tables:
        omitting any one ptag from a column-subset publication breaks CDC
        row identity (the subscriber side cannot match incoming CDC events
        to existing rows without the full primary key), and KaiwuDB
        rejects the publication at CREATE PUBLICATION execution time.

        The exact ``{seq}`` per ptag is not deterministic at config-parser
        time (it depends on ``allocate_columns`` dispatch at JMX-generation
        time), so the rule is per-type: for each declared ptag ``col_type``
        in ``TestModelConfig.ts_dbs[*].tables[*].primary_tags``, at least
        one column name in the user's list must start with
        ``ptag_{normalize_type(col_type)}_``.
        """
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                primary_tag_col_types=("int4", "varchar(32)"),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                # No ptag_ prefix at all — both declared ptag types
                # (int4 + varchar) are missing.
                columns=["rtag_int4_1", "col_float8_1"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        # Error message names the missing ptag types so the user can fix
        # the fixture without reading the validator source.
        msg = str(exc_info.value).lower()
        assert "ptag" in msg
        assert "int4" in msg and "varchar" in msg

    def test_partial_ptag_coverage_rejected(self) -> None:
        """When the table declares N>1 primary_tag col_types, the user must
        cover ALL of them in ``tables[i].columns`` — covering only a subset
        (e.g. one of two declared ptags) is rejected.

        This is the harder failure mode the user pointed out: a
        ``has_ptag = bool(...)`` shortcut would have accepted this case,
        but the 联合主键 rule requires complete coverage.
        """
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                primary_tag_col_types=("int4", "varchar(32)"),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                # Covers int4 ptag but NOT varchar ptag.
                columns=["ptag_int4_1", "col_float8_1"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        msg = str(exc_info.value).lower()
        # Specifically, varchar(32) is the uncovered ptag.
        assert "varchar" in msg
        assert "int4" not in msg or "missing" in msg

    def test_ptag_type_must_be_in_ptag_set_not_just_declared(self) -> None:
        """A column with ``ptag_`` prefix whose ``{type}`` segment matches a
        declared rtag / data col_type (but NOT a declared ptag col_type)
        is rejected. The ptag type set is checked independently of the
        combined declared-types set; sharing a ``normalize_type`` between
        a ptag and a data col does not make the data col a valid ptag
        target.
        """
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                # ptag is int4 only; float8 is a data col, not a ptag.
                primary_tag_col_types=("int4",),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                # Tries to claim a float8 ptag, but float8 is only a
                # data col_type on this table — not a ptag col_type.
                columns=["ptag_float8_1", "col_float8_1"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        with pytest.raises(Exception) as exc_info:
            validate_pub_sub_refs(model, cfg)
        msg = str(exc_info.value).lower()
        assert "ptag" in msg
        assert "float8" in msg

    def test_ts_col_name_accepted(self) -> None:
        """The user-configured ``ts_col.name`` is accepted as a valid
        column name regardless of shape (it's an arbitrary identifier
        the user picks, not column_namer-generated). Default is ``ts``;
        user can override to e.g. ``k_timestamp`` for KaiwuDB-convention
        naming."""
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                primary_tag_col_types=("int4",),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
                ts_col_name="k_timestamp",
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                columns=["k_timestamp", "ptag_int4_1", "col_float8_1"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        # No exception expected.
        validate_pub_sub_refs(model, cfg)

    def test_valid_full_config_passes(self) -> None:
        """A complete legal fixture (整库模式, no column subset) passes
        both Pydantic validation AND the cross-ref validator.

        Note: 整库模式 (``tables=None``) means ``validate_pub_sub_refs``
        does NOT inspect any column names — the cross-ref check is
        scoped to the ``tables[i].columns`` field, which is empty in
        整库模式. ``publisher_db`` + ``tables[i].name`` still get
        checked.
        """
        model = _build_test_model()
        pubsub = _build_minimal_pubsub()  # tables=None → 整库模式
        cfg = _build_test_config_with_pubsub(pubsub)
        # No exception expected.
        validate_pub_sub_refs(model, cfg)

    def test_valid_table_level_with_columns_passes(self) -> None:
        """A legal table-level fixture (1 table + columns matching the
        column_namer shape, including the timestamp column name and at
        least one ``ptag_`` entry) passes both Pydantic validation AND
        the cross-ref validator."""
        model = _build_test_model(
            db_name="iot_monitor",
            table=_build_minimal_ts_table(
                name="t_cnc",
                primary_tag_col_types=("int4", "varchar(32)"),
                regular_tag_col_types=("int4",),
                data_col_types=("float8",),
            ),
        )
        pubsub = _build_minimal_pubsub(
            tables=[PublicationTableEntry(
                name="t_cnc",
                columns=["ts", "ptag_int4_1", "ptag_varchar_1", "rtag_int4_1", "col_float8_1"],
            )],
        )
        cfg = _build_test_config_with_pubsub(pubsub)
        validate_pub_sub_refs(model, cfg)
