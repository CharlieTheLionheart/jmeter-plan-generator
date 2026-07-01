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
