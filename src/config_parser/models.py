"""Configuration data models for KaiwuDB SVT test plan generator."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Literal, Optional

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
    type: Literal["timestamp", "timestamptz", "timestamp(3)", "timestamp(6)", "timestamp(9)", "timestamptz(3)", "timestamptz(6)", "timestamptz(9)"]
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
    # sparse (KaiwuDB 2.4.1+): emit ``create sparse table`` and raise the
    # data_col_count cap from 4096 to 20000. Only valid for time-series
    # engine. Coupling with nullable/null_rate is intentionally absent —
    # see spec §3.2 / §8.3 for the narrow semantic.
    sparse: bool = False

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
    def check_data_col_count_cap(self) -> "TsTableConfig":
        """Sparse (KaiwuDB 2.4.1+) raises the data column cap from 4096 to
        20000. Regular time-series tables keep the 4096 bound. Enforced at
        parse time so misconfigured fixtures fail before JMX emission.
        """
        cap = 20000 if self.sparse else 4096
        if self.data_col_count > cap:
            raise ValueError(
                f"data_col_count={self.data_col_count} exceeds "
                f"{'sparse' if self.sparse else 'regular'} cap {cap}"
            )
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
    "direct",
    "prepare",
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
    # YAML 空值（``login_password: ``）解析为 ``None``，不是空字符串。d461e40
    # 强制 root 必须有非空密码是在 **server 端 Login API** 层面，cfg 字段
    # 只做语法兼容。运行时 ddl_setup.py:387 ``vars.get("login_password")``
    # 拿到 None 时会 log.error 退出，业务上仍受 d461e40 约束。
    login_password: Optional[str] = None
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

    @field_validator("login_password", mode="before")
    @classmethod
    def _empty_password_to_str(cls, v):
        # YAML 空值（``login_password: ``）解析为 ``None``，但下游
        # ddl_setup.py:387 / ddl_setup.py:332 直接 ``str`` 拼接 + base64
        # 编码，None 会让 Login 接口发空 Authorization header → server
        # 端 401。强制转 ``""`` 让 cfg 写法宽容（YAML 留空即视为无密码
        # 用户，TLS 模式下 server 端仍按 d461e40 强制校验）。
        return "" if v is None else v


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


# ---------------------------------------------------------------------------
# Pub-sub configuration (OpenSpec change pub-sub-end-to-end, 2026-10-12)
# ---------------------------------------------------------------------------

class PublicationTableEntry(BaseModel):
    """One table entry in ``pub_sub_config.tables`` (表级发布模式).

    Per design.md Decision 1: ``len(tables) > 1`` MUST have empty ``columns``
    and ``where`` (KaiwuDB pub-sub 文档不支持 multi-table 列子集 / WHERE
    过滤); enforcement lives in ``PubSubConfig.multi_table_forbids_columns_and_where``.
    Per design.md Decision 2: ``columns`` must cover every ``primary_tag`` of
    the table; cross-ref enforcement lives in
    ``validate_pub_sub_refs(test_model, test_config)``.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    columns: Optional[List[str]] = None
    where: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("columns")
    @classmethod
    def columns_non_empty_elements(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        for col in v:
            if not col or not col.strip():
                raise ValueError("columns elements must be non-empty")
        return v

    @field_validator("where")
    @classmethod
    def where_non_empty_when_present(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v or not v.strip():
            raise ValueError("where must be non-empty when present")
        return v


class PubSubConfig(BaseModel):
    """Configuration for pub-sub end-to-end SVT (KaiwuDB CDC).

    Per design.md §"PubSubConfig 字段清单": 7 fields. ``subscriber_db`` is
    not a field — fully hard-coded to ``f"{publisher_db}_sub"`` (D5 锁定).
    ``options.target`` is REQUIRED (D5: 同集群两库 sync-mapping discriminator;
    server cannot infer publisher_table → subscriber_table mapping without it).

    Self-consistent validation only (Pydantic-self, no test_model cross-ref):
    - ``conninfo`` must be a libpq URI (starts with ``postgresql://``) and non-empty.
    - ``options`` key whitelist: ``{buffer_size, retrieve_tags, publish,
      target, enable, ignore_history, retry}``.
    - ``options.target`` required + non-empty.
    - ``expected_min_rows >= 0`` (None accepted; 0 = 恒真 sentinel for
      WHERE-filtered scenarios).
    - ``len(tables) > 1`` ⇒ every entry's ``columns`` / ``where`` MUST be empty.

    Cross-ref validation (``publisher_db`` ∈ ts_dbs / ``tables[i].name`` ∈
    ts_tables / ``tables[i].columns`` ⊆ table columns + cover all ptags)
    lives in ``validate_pub_sub_refs(test_model, test_config)`` — see the
    docstring there for the rationale on why it cannot be a Pydantic
    ``@model_validator`` inside this class.
    """

    model_config = ConfigDict(extra="forbid")

    publisher_db: str
    publication_name: str
    subscription_name: str
    conninfo: str
    tables: Optional[List[PublicationTableEntry]] = None
    options: Dict[str, str]
    expected_min_rows: Optional[int] = None

    @field_validator("conninfo")
    @classmethod
    def conninfo_libpq_prefix(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("conninfo must be non-empty")
        v = v.strip()
        if not v.startswith("postgresql://"):
            raise ValueError(
                "conninfo must start with 'postgresql://' (libpq format; "
                "KaiwuDB server only accepts libpq-format connection strings)"
            )
        return v

    @field_validator("expected_min_rows")
    @classmethod
    def expected_min_rows_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("expected_min_rows must be >= 0")
        return v

    @model_validator(mode="after")
    def check_options(self) -> "PubSubConfig":
        """``options`` key whitelist + ``target`` required + non-empty.

        All three rules live in one validator so the error message can
        name every offending key in a single report, rather than running
        three separate field validators in undefined order.
        """
        valid_keys = {
            "buffer_size", "retrieve_tags", "publish",
            "target", "enable", "ignore_history", "retry",
        }
        invalid = set(self.options) - valid_keys
        if invalid:
            raise ValueError(f"""
options keys must be in {sorted(valid_keys)};
got invalid: {sorted(invalid)}
""")
        if "target" not in self.options:
            raise ValueError(
                "options.target is required (D5 锁定: 同集群两库 sync-mapping "
                "discriminator; server cannot infer publisher_table → "
                "subscriber_table mapping without it)"
            )
        if not self.options["target"] or not self.options["target"].strip():
            raise ValueError("options.target must be non-empty")
        return self

    @model_validator(mode="after")
    def multi_table_forbids_columns_and_where(self) -> "PubSubConfig":
        """``len(tables) > 1`` ⇒ all ``columns`` / ``where`` MUST be empty.

        Per design.md Decision 1: KaiwuDB pub-sub 文档明确不支持 multi-table
        列子集发布 / multi-table WHERE 过滤; SQL 形态见 D1 段。
        """
        if self.tables and len(self.tables) > 1:
            for i, t in enumerate(self.tables):
                if t.columns:
                    raise ValueError(f"""
tables[{i}].columns must be empty when len(tables) > 1
(KaiwuDB pub-sub 文档不支持 multi-table 列子集发布)
""")
                if t.where:
                    raise ValueError(f"""
tables[{i}].where must be empty when len(tables) > 1
(KaiwuDB pub-sub 文档不支持 multi-table WHERE 过滤)
""")
        return self


class TestConfig(BaseModel):
    """Top-level test configuration."""

    model_config = ConfigDict(extra="forbid")

    conn_config: ConnConfig
    write_config: list[WriteConfig] = Field(default_factory=list)
    query_config: list[QueryConfig] = Field(default_factory=list)
    rest_api_config: Optional[RestApiConfig] = None
    pub_sub_config: Optional[PubSubConfig] = None

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


def validate_pub_sub_refs(
    model: TestModelConfig, test_config: TestConfig
) -> None:
    """Enforce ts_table **自身属性存在性** for ``TestConfig.pub_sub_config``.

    Independent of ``validate_foreign_key_refs`` (which handles
    ``col.val_range: "ref:db.table.column"`` cross-db references —
    rel_db primary_key → ts_table regular_tag val_range, used by
    seed_data_generator). ``validate_pub_sub_refs`` only checks
    existence within ``TestModelConfig.ts_dbs`` for the fields
    ``pub_sub_config`` references; no foreign-key / val_range /
    cross-db reference is involved.

    Rules (per design.md Decision 1 / Decision 2 + column_namer shape):

    - ``pub_sub_config.publisher_db`` must be in
      ``test_model.ts_dbs[*].name``.
    - For every ``pub_sub_config.tables[i]``:
      - ``name`` must be in ``test_model.ts_dbs[*].tables[*].name``.
      - If ``columns`` is set, every element must match the
        **column_namer-rule shape** (the exact column names are only
        known at JMX generation time, so the check is shape-based):
        - the column name equals ``TsTableConfig.ts_col.name`` (the
          user-configured timestamp column name, default ``ts``), OR
        - the column name matches
          ``^{col|rtag|ptag}_{normalize_type(col_type)}_{int}$`` where
          ``normalize_type(col_type)`` is the normalized form of some
          ``col_type`` declared in the table's primary_tags +
          regular_tags + data_cols.
      - At least one column name must start with ``ptag_`` (spec §2.0:
        ptag ``nullable=false``, 必含 in any column-subset publication).

    Why this lives outside Pydantic ``@model_validator``: ``PubSubConfig``
    is loaded from ``test_cfg.yaml`` and ``TestModelConfig`` is loaded
    from ``test_model.yaml``; the two are independent YAML roots. Pydantic
    model validators can only access ``self``, so cross-ref enforcement
    must happen post-load, after both models are in memory.

    Why the column-name check is shape-based (not name-based): the
    actual column names are allocated by ``column_namer.ColumnNameGenerator``
    during JMX generation (``src/ddl_generator/column_name_generator.py``
    + ``src/column_namer/generate.py``), which depends on
    ``allocate_columns`` dispatch across declared ``col_type``s — that
    dispatch is not deterministic at config_parser time. The shape
    ``{prefix}_{normalized_type}_{sequence}`` IS deterministic (it
    only depends on per-group ``col_type`` lists + the prefix map
    ``column_namer.constants.GROUP_PREFIXES``), so the cross-ref
    validator can run at config_parser time without waiting for the
    generator.

    Raises ``ConfigParserError`` on the first violation encountered
    (matches the error-reporting style of ``validate_foreign_key_refs``).
    """
    pub_sub = test_config.pub_sub_config
    if pub_sub is None:
        return

    # Lazy import: column_namer is a leaf module without a hard
    # config_parser dependency (avoiding a circular import risk if
    # column_namer ever grows a back-reference to config_parser).
    from column_namer.constants import GROUP_PREFIXES
    from column_namer.normalize import normalize_type

    # column_namer rule: prefix in {col, rtag, ptag, pk} per GROUP_PREFIXES;
    # for ts_table validation we only need the three ts-table prefixes.
    ts_table_prefixes = (
        GROUP_PREFIXES["data_cols"],          # "col"
        GROUP_PREFIXES["regular_tags"],       # "rtag"
        GROUP_PREFIXES["primary_tags"],       # "ptag"
    )
    column_namer_pattern = re.compile(
        r"^(?P<prefix>" + "|".join(ts_table_prefixes) + r")"
        r"_(?P<type>[a-z0-9_]+)"
        r"_(?P<seq>\d+)$"
    )

    ts_db_names: set[str] = {db.name for db in model.ts_dbs}
    ts_table_lookup: dict[str, TsTableConfig] = {}
    for db in model.ts_dbs:
        for table in db.tables:
            ts_table_lookup[table.name] = table

    if pub_sub.publisher_db not in ts_db_names:
        raise ConfigParserError(f"""
pub_sub_config.publisher_db='{pub_sub.publisher_db}' not found in test_model.ts_dbs[*].name
(available: {sorted(ts_db_names)})
""")

    for i, entry in enumerate(pub_sub.tables or []):
        if entry.name not in ts_table_lookup:
            raise ConfigParserError(f"""
pub_sub_config.tables[{i}].name='{entry.name}' not found in test_model.ts_dbs[*].tables[*].name
(available: {sorted(ts_table_lookup)})
""")
        if not entry.columns:
            # Empty / unset columns → 整表发布语义, no per-column check.
            continue

        table = ts_table_lookup[entry.name]
        # ts_col.name is the user-configured timestamp column identifier.
        # Default per ddl_generator.DDLGenerator._TS_DEFAULT_NAME = "ts".
        ts_col_name = table.ts_col.name.strip() if table.ts_col else "ts"

        # Build the set of normalize_type(col_type) values the table
        # declares across primary_tags + regular_tags + data_cols.
        declared_types: set[str] = set()
        for rt in table.regular_tags:
            declared_types.add(normalize_type(rt.col_type))
        for dc in table.data_cols:
            declared_types.add(normalize_type(dc.col_type))

        # ptag is a 联合主键: every declared primary_tag col_type must be
        # represented in entry.columns by at least one matching
        # ``ptag_{normalize_type(col_type)}_{seq}`` name. Missing even one
        # ptag breaks CDC row identity (the server cannot match incoming
        # CDC events to existing rows without the full primary key), so
        # partial-publication of a ptag is rejected.
        declared_ptag_types: set[str] = {
            normalize_type(pt.col_type) for pt in table.primary_tags
        }

        covered_ptag_types: set[str] = set()
        for col_name in entry.columns:
            if col_name == ts_col_name:
                # User-configured timestamp column name — accepted as-is
                # (it's an arbitrary identifier, not column_namer-shaped).
                continue
            match = column_namer_pattern.match(col_name)
            if not match:
                raise ConfigParserError(f"""
pub_sub_config.tables[{i}].columns contains '{col_name}' which does not match the column_namer
shape '^{'|'.join(ts_table_prefixes)}_<type>_<seq>$' and is not the configured
ts_col.name='{ts_col_name}'
""")
            if match.group("prefix") == GROUP_PREFIXES["primary_tags"]:
                # Validate ptag col_type membership against the declared
                # ptag col_types (NOT the combined rtag+data set, which
                # would over-accept — a data col_type is not a valid ptag
                # even if it shares the same normalized name).
                if match.group("type") not in declared_ptag_types:
                    raise ConfigParserError(f"""
pub_sub_config.tables[{i}].columns contains '{col_name}' whose normalized type
'{match.group('type')}' is not declared as a primary_tag in table '{entry.name}'
(declared ptag types: {sorted(declared_ptag_types)})
""")
                covered_ptag_types.add(match.group("type"))
            else:
                # rtag / data col: type must be in the combined declared set.
                if match.group("type") not in declared_types:
                    raise ConfigParserError(f"""
pub_sub_config.tables[{i}].columns contains '{col_name}' whose normalized type
'{match.group('type')}' is not declared in table '{entry.name}'
(declared non-ptag types: {sorted(declared_types)})
""")

        missing_ptag_types = declared_ptag_types - covered_ptag_types
        if missing_ptag_types:
            raise ConfigParserError(f"""
pub_sub_config.tables[{i}].columns for table '{entry.name}' must include EVERY
declared primary_tag (联合主键, partial publication breaks CDC row identity);
missing ptag types: {sorted(missing_ptag_types)} (declared: {sorted(declared_ptag_types)})
""")


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
    "PubSubConfig",
    "PublicationTableEntry",
    "TestConfig",
    "validate_foreign_key_refs",
    "validate_pub_sub_refs",
    "validate_val_ranges",
]
