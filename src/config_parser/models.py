"""Configuration data models for KaiwuDB SVT test plan generator."""

from __future__ import annotations

import re
from typing import Any, Iterator, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from utils.val_range_parser import ValRange, ValRangeType, parse_val_range
from utils.rest_errors import RestConfigError


class ConfigParserError(Exception):
    """Raised when configuration parsing or validation fails."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _validate_col_type(v: str) -> str:
    """Strip and reject empty column type values."""
    if not v or not v.strip():
        raise ValueError("col_type must not be empty")
    return v.strip()


def _validate_type_proportions(
    groups: dict[str, list[Any]],
) -> None:
    """Validate that type_proportion sums to 1.0 within each column group."""
    for group_name, cols in groups.items():
        if not cols:
            continue
        total = sum(c.type_proportion for c in cols)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"{group_name} type_proportion sums to {total}, expected 1.0"
            )


def _validate_primary_tag_constraints(
    primary_tags: list[Any],
) -> None:
    """Validate primary tag column type constraints."""
    for col in primary_tags:
        base = col.col_type.lower()
        if base in ("float4", "float8", "nvarchar"):
            raise ValueError(
                f"primary_tags does not allow col_type={col.col_type}"
            )
        match = re.fullmatch(r"varchar\((\d+)\)", base)
        if match:
            length = int(match.group(1))
            if length > 128:
                raise ValueError(
                    f"primary_tags varchar length {length} exceeds 128"
                )


def _validate_tag_type_constraints(
    primary_tags: list[Any],
    regular_tags: list[Any],
) -> None:
    """Validate that tags don't use forbidden types."""
    forbidden = {"timestamp", "timestamptz", "geometry"}
    for col in list(primary_tags) + list(regular_tags):
        base = col.col_type.lower()
        # strip size suffix like varchar(64) for type name check
        type_name = base.split("(")[0].strip()
        if type_name in forbidden:
            raise ValueError(
                f"tags do not allow col_type={col.col_type}"
            )


# ---------------------------------------------------------------------------
# Column type configuration
# ---------------------------------------------------------------------------

class ColTypeConfig(BaseModel):
    """Column type configuration for primary_keys, data_cols, regular_tags."""

    model_config = ConfigDict(extra="forbid", strict=False)

    col_type: str
    type_proportion: float
    val_range: Optional[str] = None
    seed_num: int = Field(default=1000, ge=0)
    nullable: bool = True
    null_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("col_type")
    @classmethod
    def col_type_not_empty(cls, v: str) -> str:
        return _validate_col_type(v)

    @model_validator(mode="after")
    def check_nullable_null_rate(self) -> "ColTypeConfig":
        if not self.nullable and self.null_rate > 0:
            raise ValueError("nullable must be true when null_rate > 0")
        return self


class PrimaryTagColTypeConfig(BaseModel):
    """Column type configuration for primary_tags (no nullable field)."""

    model_config = ConfigDict(extra="forbid")

    col_type: str
    type_proportion: float
    val_range: Optional[str] = None
    seed_num: int = Field(default=1000, ge=0)

    @field_validator("col_type")
    @classmethod
    def col_type_not_empty(cls, v: str) -> str:
        return _validate_col_type(v)


class TsColConfig(BaseModel):
    """Time-series table timestamp column configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["timestamp", "timestamptz"]
    ms_step: int = Field(ge=1)


# ---------------------------------------------------------------------------
# Table configuration (inheritance hierarchy)
# ---------------------------------------------------------------------------

class TableConfig(BaseModel):
    """Table configuration base class (shared by relational and time-series tables)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    comment: Optional[str] = None
    if_not_exists: bool = True
    data_col_count: int = Field(ge=0)
    data_cols: list[ColTypeConfig] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("table name must not be empty")
        return v.strip()


class RelTableConfig(TableConfig):
    """Relational table configuration."""

    model_config = ConfigDict(extra="forbid")

    primary_key_count: int = Field(ge=0)
    primary_keys: list[ColTypeConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_type_proportions(self) -> "RelTableConfig":
        _validate_type_proportions({
            "primary_keys": self.primary_keys,
            "data_cols": self.data_cols,
        })
        return self

    @model_validator(mode="after")
    def check_primary_key_count(self) -> "RelTableConfig":
        """R-PAR-003: primary_key_count must equal len(primary_keys)."""
        if self.primary_key_count != len(self.primary_keys):
            raise ValueError(
                f"primary_key_count={self.primary_key_count} "
                f"but len(primary_keys)={len(self.primary_keys)}; "
                f"they must be equal"
            )
        return self


class TsTableConfig(TableConfig):
    """Time-series table configuration."""

    model_config = ConfigDict(extra="forbid")

    with_hash: Optional[int] = None
    ts_col: Optional[TsColConfig] = None
    primary_tag_count: int = Field(default=0, ge=0, le=4)
    regular_tag_count: int = Field(default=0, ge=0)
    primary_tags: list[PrimaryTagColTypeConfig] = Field(default_factory=list)
    regular_tags: list[ColTypeConfig] = Field(default_factory=list)
    retentions: Optional[str] = None

    @model_validator(mode="after")
    def check_type_proportions(self) -> "TsTableConfig":
        _validate_type_proportions({
            "data_cols": self.data_cols,
            "primary_tags": self.primary_tags,
            "regular_tags": self.regular_tags,
        })
        return self

    @model_validator(mode="after")
    def check_primary_tag_constraints(self) -> "TsTableConfig":
        if self.primary_tags:
            _validate_primary_tag_constraints(self.primary_tags)
        return self

    @model_validator(mode="after")
    def check_tag_type_constraints(self) -> "TsTableConfig":
        if self.primary_tags or self.regular_tags:
            _validate_tag_type_constraints(self.primary_tags, self.regular_tags)
        return self

    @model_validator(mode="after")
    def check_with_hash(self) -> "TsTableConfig":
        if self.with_hash is not None and not (1 <= self.with_hash <= 50000):
            raise ValueError("with_hash must be between 1 and 50000")
        return self

    @model_validator(mode="after")
    def check_tag_counts(self) -> "TsTableConfig":
        """R-PAR-004: primary_tag_count + regular_tag_count must equal len(primary_tags) + len(regular_tags)."""
        expected = self.primary_tag_count + self.regular_tag_count
        actual = len(self.primary_tags) + len(self.regular_tags)
        if expected != actual:
            raise ValueError(
                f"primary_tag_count({self.primary_tag_count}) + "
                f"regular_tag_count({self.regular_tag_count}) = {expected}, "
                f"but len(primary_tags)({len(self.primary_tags)}) + "
                f"len(regular_tags)({len(self.regular_tags)}) = {actual}; "
                f"they must be equal"
            )
        return self


# ---------------------------------------------------------------------------
# Database configuration (inheritance hierarchy)
# ---------------------------------------------------------------------------

class DatabaseConfig(BaseModel):
    """Database configuration base class."""

    model_config = ConfigDict(extra="forbid")

    name: str
    if_not_exists: bool = True
    comment: Optional[str] = None


class RelDbConfig(DatabaseConfig):
    """Relational database configuration."""

    model_config = ConfigDict(extra="forbid")

    with_encoding: Optional[str] = None
    tables: list[RelTableConfig] = Field(default_factory=list)


class TsDbConfig(DatabaseConfig):
    """Time-series database configuration."""

    model_config = ConfigDict(extra="forbid")

    retentions: Optional[str] = None
    partition_interval: Optional[str] = None
    tables: list[TsTableConfig] = Field(default_factory=list)


class TestModelConfig(BaseModel):
    """Top-level test model configuration."""

    model_config = ConfigDict(extra="forbid")

    rel_dbs: list[RelDbConfig] = Field(default_factory=list)
    ts_dbs: list[TsDbConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def at_least_one_database(self) -> "TestModelConfig":
        if not self.rel_dbs and not self.ts_dbs:
            raise ValueError("at least one database must be defined")
        return self


# ---------------------------------------------------------------------------
# test_cfg.yaml configuration
# ---------------------------------------------------------------------------

class ConnConfig(BaseModel):
    """Connection configuration."""

    model_config = ConfigDict(extra="forbid")

    db_url: str
    db_username: str = Field(default="root")
    db_password: str = Field(default="")
    conn_pool_size: int = Field(default=10, ge=1)
    device_start: int = Field(default=1, ge=0)
    test_duration: int = Field(default=60, ge=1)


WriteMode = Literal[
    "single_insert",
    "batch_insert",
    "single_prepared",
    "batch_prepared",
    "schemaless",
]


class RestApiConfig(BaseModel):
    """KaiwuDB RESTful API connection configuration.

    Note (2026-07-27): schemaless Login 强制非空密码用户，非空密码用户只能
    通过安全模式（TLS）创建；因此 ``https_mode`` 不再支持 ``insecure``，
    必须为 ``"tls"``。字段保留仅为显式记录 TLS 模式与历史兼容入口；
    新代码可省略该字段（默认 ``tls``）。
    """

    model_config = ConfigDict(extra="forbid")

    https_mode: Literal["tls"] = "tls"
    ca_cert_path: Optional[str] = None
    http_port: int = Field(default=8080, ge=1, le=65535)
    login_user: str
    login_password: str = ""
    login_url_path: str = "/restapi/login"
    ddl_url_path: str = "/restapi/ddl"
    write_url_path: str = "/restapi/influxdb"
    query_url_path: str = "/restapi/query"
    default_db: str = "defaultdb"
    timezone: Optional[str] = None
    pre_create_tables: bool = True

    @model_validator(mode="after")
    def check_tls_requires_ca_cert(self) -> "RestApiConfig":
        if not self.ca_cert_path:
            raise RestConfigError.missing_ca_cert()
        return self


class WriteConfig(BaseModel):
    """Write workload configuration."""

    model_config = ConfigDict(extra="forbid")

    tbl_name: str
    throughput: float = Field(default=1000.0, gt=0)
    mode: WriteMode
    batch_lines: int = Field(default=1, ge=1)
    device_per_thread: int = Field(default=1, ge=1)
    num_threads: int = Field(default=1, ge=1)
    # col-tag-bind-write (2026-08-05): per-table column-tag binding sub-mode.
    # When True, Orchestrator skips row-aggregate generation for this table
    # and Write TG emits inline INSERT with a ptag-bound subset of data
    # columns. Orthogonal to ``mode`` (applies to all 5 WriteMode values).
    col_tag_bind_mode: bool = False
    col_num_per_tag: int = 0

    @model_validator(mode="after")
    def check_single_insert_batch_lines(self) -> "WriteConfig":
        """R-PAR-016: single_insert mode requires batch_lines == 1."""
        if self.mode == "single_insert" and self.batch_lines != 1:
            raise ValueError(
                f"single_insert mode requires batch_lines=1, "
                f"but got batch_lines={self.batch_lines}"
            )
        return self

    @model_validator(mode="after")
    def check_col_tag_bind_mode_positive(self) -> "WriteConfig":
        """col-tag-bind-write (2026-08-05): ``col_num_per_tag`` must be > 0
        when ``col_tag_bind_mode=True``. Per-table upper-bound validation
        (``col_num_per_tag <= data_col_count``) and ptag-count check
        (``primary_tag_count >= 1``) are enforced at the main entry, since
        they require cross-reference to ``TestModelConfig``."""
        if self.col_tag_bind_mode and self.col_num_per_tag <= 0:
            raise ValueError(
                f"col_num_per_tag must be > 0 when col_tag_bind_mode=true; "
                f"got col_num_per_tag={self.col_num_per_tag}"
            )
        return self


class QueryConfig(BaseModel):
    """Query workload configuration.

    R-2 (2026-07-21, openspec/changes/query-naming): optional ``name``
    field selects the ThreadGroup testname; when unset, the generator
    falls back to ``query{N}`` by template order.
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    # R-2 (2026-07-21): optional human-readable name for the query
    # ThreadGroup. When unset, the generator assigns ``query{N}`` based
    # on template order (1-indexed). Naming failed queries is easier
    # when the label is ``[Query] query3`` instead of the truncated
    # SQL text ``[Query] SELECT rtag_varchar_1, count(*)...``.
    name: Optional[str] = None
    throughput: float = Field(default=100.0, gt=0)
    num_threads: int = Field(default=1, ge=1)

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query must not be empty")
        return v.strip()

    @field_validator("name")
    @classmethod
    def name_normalize(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class TestConfig(BaseModel):
    """Top-level test configuration."""

    model_config = ConfigDict(extra="forbid")

    conn_config: ConnConfig
    write_config: list[WriteConfig] = Field(default_factory=list)
    query_config: list[QueryConfig] = Field(default_factory=list)
    rest_api_config: Optional[RestApiConfig] = None

    def find_write_config(self, db_name: str, table_name: str) -> Optional["WriteConfig"]:
        """Return the ``WriteConfig`` for ``db_name.table_name`` or ``None``.

        col-tag-bind-write (2026-08-05): shared lookup used by Orchestrator
        (skip row aggregate) and main entry (per-table validations). Matches
        ``WriteConfig.tbl_name`` exactly (``{db}.{table}`` format).
        """
        key = f"{db_name}.{table_name}"
        for wc in self.write_config:
            if wc.tbl_name == key:
                return wc
        return None

    @model_validator(mode="after")
    def check_write_num_threads_consistency(self) -> "TestConfig":
        if len(self.write_config) > 1:
            values = {w.num_threads for w in self.write_config}
            if len(values) > 1:
                raise ValueError(
                    "all write_config entries must share the same num_threads"
                )
        return self

    @model_validator(mode="after")
    def check_query_placeholders(self) -> "TestConfig":
        # Every '?' must be bound to a column reference (e.g. "WHERE col = ?").
        # Full semantic binding against generated column names is performed downstream.
        for qc in self.query_config:
            placeholders = list(re.finditer(r"\?", qc.query))
            bindings = list(re.finditer(r"(\w+)\s*=\s*\?", qc.query))
            if len(bindings) != len(placeholders):
                raise ValueError(
                    "every query placeholder '?' must be bound to a column reference (column = ?)"
                )
            for match in bindings:
                col_ref = match.group(1)
                if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", col_ref):
                    raise ValueError(
                        f"query placeholder not bound to a valid column reference: {col_ref}"
                    )
        return self


# ---------------------------------------------------------------------------
# Post-load business rule validation
# ---------------------------------------------------------------------------

def _iter_columns(
    model: TestModelConfig,
    *,
    include_primary_tags: bool = False,
) -> Iterator[tuple[DatabaseConfig, TableConfig, Any]]:
    """Yield (database, table, column) for every column in the model."""
    for db in model.rel_dbs + model.ts_dbs:
        for table in db.tables:
            # primary_keys only exists on RelTableConfig;
            # regular_tags/primary_tags only exist on TsTableConfig.
            columns: list[Any] = (
                list(getattr(table, "primary_keys", []))
                + list(table.data_cols)
                + list(getattr(table, "regular_tags", []))
            )
            if include_primary_tags:
                columns += list(getattr(table, "primary_tags", []))
            for col in columns:
                yield db, table, col


def validate_foreign_key_refs(model: TestModelConfig) -> None:
    """Validate that every ref: target exists in the model.

    Refs use the same ``db.table.column_name`` format as the
    seed_data_generator registry (column_namer-allocated names like
    ``pk_int8_1``), NOT ``col_type`` — multiple columns with the same
    type must be addressable by their generated name.
    """
    from seed_data_generator.reference import iter_table_columns

    refs: dict[str, list[str]] = {}
    existing: set[str] = set()

    for db in model.rel_dbs + model.ts_dbs:
        for table in db.tables:
            for _index, name, col, _group, _base_type in iter_table_columns(table):
                key = f"{db.name}.{table.name}.{name}"
                existing.add(key)
                if col.val_range and col.val_range.startswith("ref:"):
                    target = col.val_range[4:]
                    refs.setdefault(target, []).append(key)

    if not refs:
        return

    missing = [target for target in refs if target not in existing]
    if missing:
        raise ConfigParserError(f"foreign key target(s) not found: {missing}")


def validate_val_ranges(model: TestModelConfig) -> None:
    """Parse and validate all val_range expressions."""
    for db, table, col in _iter_columns(model, include_primary_tags=True):
        if not col.val_range:
            continue
        try:
            parsed = parse_val_range(col.val_range)
        except ValueError as exc:
            raise ConfigParserError(
                f"{db.name}.{table.name}: invalid val_range for {col.col_type}: {exc}"
            ) from exc

        if parsed.range_type is not ValRangeType.INTERVAL:
            continue

        if parsed.interval is None:
            raise ConfigParserError(
                f"{db.name}.{table.name}: interval val_range missing parsed interval"
            )

        low, high = parsed.interval.low, parsed.interval.high
        if low > high:
            raise ConfigParserError(
                f"{db.name}.{table.name}: interval lower bound {low} exceeds upper bound {high}"
            )

        base_type = col.col_type.lower().split("(")[0].strip()
        if base_type in ("int", "int2", "int4", "int8", "bigint", "smallint", "tinyint"):
            # For integer types, ensure the open interval contains at least one integer.
            if parsed.interval.low_open and parsed.interval.high_open:
                first_int = int(low) + 1
                if first_int >= high:
                    raise ConfigParserError(
                        f"{db.name}.{table.name}: open interval ({low},{high}) contains no valid integer"
                    )


__all__ = [
    "ConfigParserError",
    "ColTypeConfig",
    "PrimaryTagColTypeConfig",
    "TsColConfig",
    "TableConfig",
    "RelTableConfig",
    "TsTableConfig",
    "DatabaseConfig",
    "RelDbConfig",
    "TsDbConfig",
    "TestModelConfig",
    "ConnConfig",
    "WriteConfig",
    "WriteMode",
    "QueryConfig",
    "TestConfig",
    "validate_foreign_key_refs",
    "validate_val_ranges",
]
