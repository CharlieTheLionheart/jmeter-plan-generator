"""DDL script generator for relational and time-series databases."""

from __future__ import annotations

import re
from typing import Any, List, Optional

from column_namer import allocate_columns
from config_parser.models import (
    ColTypeConfig,
    DatabaseConfig,
    PrimaryTagColTypeConfig,
    RelTableConfig,
    TableConfig,
    TestModelConfig,
    TsTableConfig,
)
from ddl_generator.column_name_generator import ColumnNameGenerator
from ddl_generator.data_type_mapper import DataTypeMapper, UnsupportedDataTypeError


class DdlGenerationError(Exception):
    """Raised when DDL generation fails."""


# SQL reserved keywords that cannot be used as unquoted identifiers.
_RESERVED_KEYWORDS = frozenset(
    {
        "select",
        "insert",
        "update",
        "delete",
        "from",
        "where",
        "and",
        "or",
        "not",
        "null",
        "create",
        "drop",
        "table",
        "database",
        "primary",
        "key",
        "tags",
        "timestamp",
    }
)

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _validate_identifier(name: str) -> None:
    """Reject empty names, special characters, and reserved keywords."""
    if not name:
        raise DdlGenerationError("identifier must not be empty")
    if not _IDENTIFIER_RE.match(name):
        raise DdlGenerationError(f"invalid identifier: {name}")
    if name.lower() in _RESERVED_KEYWORDS:
        raise DdlGenerationError(f"reserved keyword cannot be used as identifier: {name}")


def _build_foreign_key_clause(val_range: Optional[str]) -> Optional[str]:
    """Return a ``REFERENCES db.table(col)`` clause when ``val_range`` is a ref.

    The fixture encodes the FK target as ``ref:<db>.<table>.<col>`` in
    val_range; this function translates that into a KaiwuDB REFERENCES
    fragment that the DDL generator appends to the column definition.
    Returns None when val_range is not a ref.

    外键关系生成（T1）落地于 commit ``8614b90``（R-3 续 FK 约束 +
    workshop 100 行）；主 spec §7 历史排期跟踪 + §2.0 ref: 字段定义。
    """
    if not val_range or not val_range.startswith("ref:"):
        return None
    target = val_range[4:].strip()
    parts = target.split(".")
    if len(parts) != 3:
        raise DdlGenerationError(
            f"ref: target must be db.table.col, got {target!r}"
        )
    ref_db, ref_table, ref_col = parts
    for ident in (ref_db, ref_table, ref_col):
        _validate_identifier(ident)
    return f"references {ref_db}.{ref_table}({ref_col})"


def _single_quote(value: str) -> str:
    """Wrap a string in single quotes, escaping internal single quotes."""
    return "'" + value.replace("'", "''") + "'"


class _ColumnSpec:
    """Internal column specification used during DDL generation."""

    def __init__(
        self,
        name: str,
        ddl_type: str,
        nullable: bool,
        group: str,
        val_range: Optional[str] = None,
    ):
        self.name = name
        self.ddl_type = ddl_type
        self.nullable = nullable
        self.group = group
        self.val_range = val_range


def _allocate_group(
    table: TableConfig,
    group: str,
    total: int,
    generator: ColumnNameGenerator,
) -> List[_ColumnSpec]:
    """Allocate column counts and names for a single column group."""
    cols = getattr(table, group)
    if total == 0 or not cols:
        return []

    proportions = [c.type_proportion for c in cols]
    counts = allocate_columns(total, proportions)

    specs: List[_ColumnSpec] = []
    for col, count in zip(cols, counts):
        names = generator.generate(group, col.col_type, count)
        try:
            ddl_type = DataTypeMapper.map(col.col_type)
        except UnsupportedDataTypeError as exc:
            raise DdlGenerationError(str(exc)) from exc
        nullable = _nullable_for_group(group, col)
        val_range = getattr(col, "val_range", None)
        for name in names:
            specs.append(_ColumnSpec(name, ddl_type, nullable, group, val_range))
    return specs


def _nullable_for_group(group: str, col: Any) -> bool:
    """Primary tags are always NOT NULL; otherwise honour ``col.nullable``."""
    if group == "primary_tags":
        return False
    return getattr(col, "nullable", True)


class DDLGenerator:
    """Generate KaiwuDB DDL scripts from a parsed ``TestModelConfig``."""

    _TS_DEFAULT_NAME = "ts"
    _TS_DEFAULT_TYPE = "timestamp"

    def __init__(self, model: TestModelConfig):
        self.model = model

    def generate(self) -> str:
        """Return a semicolon-separated SQL script."""
        statements = self.generate_statements()
        if not statements:
            return ""
        return ";\n".join(statements) + ";"

    def generate_statements(self) -> List[str]:
        """Return DDL statements in dependency order."""
        statements: List[str] = []
        for db in self.model.rel_dbs:
            statements.extend(self._relational_database(db))
        for db in self.model.ts_dbs:
            statements.extend(self._ts_database(db))
        return statements

    # ------------------------------------------------------------------
    # Relational databases
    # ------------------------------------------------------------------

    def _relational_database(self, db: DatabaseConfig) -> List[str]:
        _validate_identifier(db.name)
        statements = [self._create_rel_database(db)]
        for table in db.tables:
            statements.append(self._create_rel_table(db.name, table))
        return statements

    def _create_rel_database(self, db: DatabaseConfig) -> str:
        parts = ["create database"]
        if db.if_not_exists:
            parts.append("if not exists")
        parts.append(db.name)
        if db.with_encoding:
            parts.append(f"with encoding {_single_quote(db.with_encoding)}")
        if db.comment:
            parts.append(f"comment {_single_quote(db.comment)}")
        return " ".join(parts)

    def _create_rel_table(self, db_name: str, table: RelTableConfig) -> str:
        _validate_identifier(table.name)
        generator = ColumnNameGenerator(table)
        pk_specs = _allocate_group(table, "primary_keys", table.primary_key_count, generator)
        data_specs = _allocate_group(table, "data_cols", table.data_col_count, generator)

        if not pk_specs and not data_specs:
            raise DdlGenerationError(
                f"table {db_name}.{table.name} has no columns"
            )

        # When a data_col carries a ``ref:db.table.col`` val_range, the
        # generated DDL column must declare a foreign key to the target.
        # Tag columns (regular_tags/primary_tags) are not supported here —
        # KaiwuDB does not accept cross-table REFERENCES inside ``tags(...)``
        # clauses, so the logical relationship is recorded only in the
        # seed data, not in DDL constraints.
        all_specs = pk_specs + data_specs
        defs = self._column_definitions(all_specs)
        for spec in all_specs:
            fk_clause = _build_foreign_key_clause(spec.val_range)
            if fk_clause:
                defs[all_specs.index(spec)] += f" {fk_clause}"
        pk_names = [spec.name for spec in pk_specs]
        if pk_names:
            defs.append(f"primary key ({', '.join(pk_names)})")

        parts = ["create table"]
        if table.if_not_exists:
            parts.append("if not exists")
        parts.append(f"{db_name}.{table.name}")
        parts.append(f"({', '.join(defs)})")
        if table.comment:
            parts.append(f"comment {_single_quote(table.comment)}")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Time-series databases
    # ------------------------------------------------------------------

    def _ts_database(self, db: DatabaseConfig) -> List[str]:
        _validate_identifier(db.name)
        statements = [self._create_ts_database(db)]
        for table in db.tables:
            statements.append(self._create_ts_table(db.name, table))
        return statements

    def _create_ts_database(self, db: DatabaseConfig) -> str:
        parts = ["create ts database"]
        if db.if_not_exists:
            parts.append("if not exists")
        parts.append(db.name)
        if db.retentions:
            parts.append(f"retentions {db.retentions}")
        if db.partition_interval:
            parts.append(f"partition interval {db.partition_interval}")
        if db.comment:
            parts.append(f"comment {_single_quote(db.comment)}")
        return " ".join(parts)

    def _create_ts_table(self, db_name: str, table: TsTableConfig) -> str:
        _validate_identifier(table.name)
        generator = ColumnNameGenerator(table)

        ts_name, ts_type = self._parse_ts_column(table)
        ts_col_def = f"{ts_name} {ts_type} not null"

        ptag_specs = _allocate_group(
            table, "primary_tags", table.primary_tag_count, generator
        )
        rtag_specs = _allocate_group(
            table, "regular_tags", table.regular_tag_count, generator
        )
        data_specs = _allocate_group(
            table, "data_cols", table.data_col_count, generator
        )

        if not (ptag_specs or data_specs):
            raise DdlGenerationError(
                f"time-series table {db_name}.{table.name} has no usable columns"
            )

        all_tag_specs = ptag_specs + rtag_specs
        tag_defs = self._column_definitions(all_tag_specs)

        # KaiwuDB convention: tag columns live only in the ``tags(...)`` /
        # ``primary tags(...)`` clauses. Inlining them into the main column
        # list triggers ``duplicate column name`` at DDL time.
        column_defs = [ts_col_def]
        column_defs.extend(self._column_definitions(data_specs))

        parts = ["create table"]
        if table.if_not_exists:
            parts.append("if not exists")
        parts.append(f"{db_name}.{table.name}")
        parts.append(f"({', '.join(column_defs)})")

        if all_tag_specs:
            parts.append(f"tags ({', '.join(tag_defs)})")
        if ptag_specs:
            ptag_names = [spec.name for spec in ptag_specs]
            parts.append(f"primary tags ({', '.join(ptag_names)})")

        extras: List[str] = []
        # Per spec §8.2 / §8.2-WITH HASH: KaiwuDB time-series DDL accepts
        # ``[retentions <dur>] [dict encoding] [comment [=] <text>] [with hash(<n>)]``
        # — ``retentions`` is bare (no ``with`` prefix and unquoted),
        # ``comment`` accepts an optional ``=`` between keyword and value,
        # and ``with hash`` must be LAST. The previous shape
        # (``with retentions '3d' comment ... with hash(N)``) was rejected
        # by KaiwuDB because retentions was both over-quoted and
        # over-prefixed.
        if table.retentions:
            extras.append(f"retentions {table.retentions}")
        if table.comment:
            extras.append(f"comment {_single_quote(table.comment)}")
        if table.with_hash is not None:
            extras.append(f"with hash({table.with_hash})")
        if extras:
            parts.append(" ".join(extras))

        return " ".join(parts)

    def _parse_ts_column(self, table: TableConfig) -> tuple[str, str]:
        """Parse the time-series timestamp column name and type.

        Defaults to ``ts timestamp``.  A configured ``ts_col`` value may be
        a ``TsColConfig`` object or absent.
        """
        if not isinstance(table, TsTableConfig):
            return self._TS_DEFAULT_NAME, self._TS_DEFAULT_TYPE

        ts_col = table.ts_col
        if ts_col is None:
            return self._TS_DEFAULT_NAME, self._TS_DEFAULT_TYPE

        name = ts_col.name.strip()
        _validate_identifier(name)

        ts_type = DataTypeMapper.map(ts_col.type)

        return name, ts_type

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _column_definitions(specs: List[_ColumnSpec]) -> List[str]:
        defs: List[str] = []
        for spec in specs:
            _validate_identifier(spec.name)
            fragment = f"{spec.name} {spec.ddl_type}"
            if not spec.nullable:
                fragment += " not null"
            defs.append(fragment)
        return defs
