"""KaiwuDB data type validation and normalization."""

from __future__ import annotations


class UnsupportedDataTypeError(ValueError):
    """Raised when a column type is not supported by KaiwuDB DDL."""


class DataTypeMapper:
    """Maps configuration column types to KaiwuDB-compatible lower-case DDL types."""

    # Base type names supported in KaiwuDB DDL.  Length/precision modifiers are
    # preserved when present (e.g. ``varchar(16)``).
    SUPPORTED_BASE_TYPES = frozenset(
        {
            "int8",
            "int4",
            "int2",
            "int",
            "bigint",
            "smallint",
            "tinyint",
            "float",
            "float4",
            "float8",
            "double",
            # decimal / numeric：spec §403 显式列出；D-9 (2026-08-11)
            # 修复 — 历史遗漏导致 fixture 写 ``col_type: decimal`` 报
            # ``UnsupportedDataTypeError: decimal``。KaiwuDB 与 PostgreSQL
            # 一致：``decimal`` / ``numeric`` 是 arbitrary-precision
            # decimal 同义词，DDL 接受 ``decimal(p, s)`` / ``numeric(p, s)``。
            "decimal",
            "numeric",
            # R-1 (2026-07-21): shig fixture mirrors develop-2.0
            # ``resources/db_shig/{t_cnc,t_electmeter}`` which use
            # ``char(N)`` heavily (char(20/30/10/2/63) accounts for
            # 33 of the 116 data columns). KaiwuDB accepts fixed-length
            # ``char`` natively; the previous whitelist omitted it and
            # raised ``UnsupportedDataTypeError: char(30)``.
            "char",
            "varchar",
            "nvarchar",
            "text",
            "bool",
            "timestamp",
            "timestamptz",
            "geometry",
        }
    )

    @classmethod
    def map(cls, col_type: str) -> str:
        """Return a lower-case DDL type string for ``col_type``.

        Raises:
            UnsupportedDataTypeError: When the base type is unknown.
        """
        normalized = col_type.strip().lower()
        base = normalized.split("(")[0].split("[")[0].strip()
        if base not in cls.SUPPORTED_BASE_TYPES:
            raise UnsupportedDataTypeError(f"unsupported data type: {col_type}")
        return normalized

    @classmethod
    def is_supported(cls, col_type: str) -> bool:
        """Return True if ``col_type`` is supported."""
        try:
            cls.map(col_type)
        except UnsupportedDataTypeError:
            return False
        return True
