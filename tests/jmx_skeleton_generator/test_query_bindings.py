"""Tests for column binding, IN clause handling, and error type uniformity.

Closes review.md §1 §3 by exercising:

- design decision 13: ``IN (?)`` (single) accepted; ``IN (?, ?)`` rejected.
- design decision 15: every rejection path raises ``QueryGenerationError``,
  no special subclasses are defined.
- design decision 2 + design decisions 1+4: table-qualified / bare column
  names bind to the column seed file glob.
"""

from __future__ import annotations

import pytest

from jmx_skeleton_generator.generators._query_errors import QueryGenerationError
from jmx_skeleton_generator.generators.query_groups import (
    _extract_column_context,
    generate_param_binding_script,
)


def _script(sql: str) -> str:
    return generate_param_binding_script(sql)


class TestInClause:
    def test_single_placeholder_in_clause_accepted(self):
        """design decision 13: IN(?) is allowed; equivalent to ``=``."""
        sql = "SELECT * FROM db.t WHERE col IN (?)"
        # Should not raise; script is produced.
        script = _script(sql)
        assert "param_0" in script

    def test_multi_placeholder_in_clause_rejected(self):
        """design decision 13: IN(?, ?) is rejected."""
        sql = "SELECT * FROM db.t WHERE col IN (?, ?)"
        with pytest.raises(QueryGenerationError) as ei:
            _script(sql)
        assert ei.value.kind == "IN_MULTI_PLACEHOLDER"
        assert "IN clauses" in str(ei.value)

    def test_three_placeholders_in_clause_rejected(self):
        sql = "SELECT * FROM db.t WHERE col IN (?, ?, ?)"
        with pytest.raises(QueryGenerationError) as ei:
            _script(sql)
        assert ei.value.kind == "IN_MULTI_PLACEHOLDER"


class TestErrorTypeUniformity:
    @pytest.mark.parametrize(
        "sql,expected_kind",
        [
            ("SELECT * FROM db.t LIMIT ?", None),  # kind varies by clause; allow either
            ("SELECT * FROM db.t WHERE col IS ?", None),
        ],
    )
    def test_rejection_errors_are_querygenerationerror_instances(self, sql, expected_kind):
        """design decision 15: every rejection is ``QueryGenerationError`` (no subclasses)."""
        with pytest.raises(QueryGenerationError):
            _script(sql)

    def test_no_querygenerationerror_subclass(self):
        """design decision 15: enforcement — only the base class exists."""
        from jmx_skeleton_generator.generators import _query_errors as err_mod

        defined = [
            n
            for n, obj in vars(err_mod).items()
            if isinstance(obj, type) and issubclass(obj, QueryGenerationError)
        ]
        assert defined == ["QueryGenerationError"], (
            f"unexpected QueryGenerationError subclasses: {defined}"
        )


class TestColumnBinding:
    def test_table_qualified_column(self):
        sql = "SELECT * FROM db.t WHERE t.col_int8_1 = ?"
        col = _extract_column_context(sql, sql.index("?"))
        assert col == "col_int8_1"

    def test_bare_column(self):
        sql = "SELECT * FROM db.t WHERE col_int8_1 = ?"
        col = _extract_column_context(sql, sql.index("?"))
        assert col == "col_int8_1"
