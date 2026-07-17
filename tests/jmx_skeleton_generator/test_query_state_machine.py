"""Tests for the SQL state machine and its rejection rules.

Closes review.md §3 "测试覆盖" and validates design decisions:

- §16 _scan_sql_tokens is the single source consumed by both
  ``_extract_placeholders`` and ``_replace_placeholders_with_vars``
  (byte-equal count between extraction and rewriting).
- §9 SQL escape sequences inside string literals (``''`` / ``""``).
- §11 SQL templates must not contain ``--`` / ``/* */`` comments.
- §11 EOF hard-fail for unterminated string literals.
- §7 LIMIT ? / BETWEEN ? AND ? / IS NULL placeholders are rejected.
"""

from __future__ import annotations

import pytest

from jmx_skeleton_generator.generators._query_errors import QueryGenerationError
from jmx_skeleton_generator.generators.query_groups import (
    _extract_placeholders,
    _replace_placeholders_with_vars,
    _scan_sql_tokens,
)


def _placeholder_count_via_tokens(sql: str) -> int:
    """Helper: extract placeholder count via the new single-source scanner."""
    tokens, _ = _scan_sql_tokens(sql)
    return sum(1 for t in tokens if t.kind == "PLACEHOLDER")


class TestSingleSourceScanner:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM db.t",
            "SELECT a, b FROM db.t WHERE col = ?",
            "SELECT col FROM db.t WHERE a = ? AND b = ?",
        ],
    )
    def test_extract_and_replace_counts_match(self, sql):
        """design decision 16: extraction/rewriting cannot drift."""
        positions = _extract_placeholders(sql)
        rewritten, count = _replace_placeholders_with_vars(sql)
        assert len(positions) == count == _placeholder_count_via_tokens(sql)
        assert "${param_0}" in rewritten or count == 0

    def test_replace_emits_param_n_refs(self):
        sql = "SELECT a FROM t WHERE x = ? AND y = ? AND z = ?"
        rewritten, count = _replace_placeholders_with_vars(sql)
        assert count == 3
        assert rewritten.count("${param_0}") == 1
        assert rewritten.count("${param_1}") == 1
        assert rewritten.count("${param_2}") == 1


class TestStringLiteralEscapes:
    def test_empty_double_quote_string_inside_expression(self):
        """Both single- and double-quoted runs are tokenised as a single chunk."""
        sql = 'SELECT * FROM t WHERE name = \'\' AND col = ?'
        positions = _extract_placeholders(sql)
        assert len(positions) == 1

    def test_escaped_single_quote_does_not_close_string(self):
        """design decision 9: ``''`` is an embedded escaped quote, string stays open."""
        sql = "SELECT * FROM t WHERE name = 'O''Brien' AND col = ?"
        # Two real placeholders: 1 inside (none — the inner O'' has no ?), and
        # only the trailing `?` after ` AND col = `.
        tokens, _ = _scan_sql_tokens(sql)
        placeholders = [t for t in tokens if t.kind == "PLACEHOLDER"]
        assert len(placeholders) == 1
        assert placeholders[0].start == sql.index("AND col = ?") + len("AND col = ")

    def test_double_quoted_identifier_with_inner_single_quote(self):
        """design decision 1 (no nesting): single-quote inside DQ_STRING is data."""
        sql = 'SELECT * FROM t WHERE col = ? AND "weird\'name" = ?'
        tokens, _ = _scan_sql_tokens(sql)
        placeholders = [t for t in tokens if t.kind == "PLACEHOLDER"]
        assert len(placeholders) == 2


class TestCommentRejection:
    def test_line_comment_rejected(self):
        sql = "SELECT * FROM t WHERE col = ? -- some annotation"
        with pytest.raises(QueryGenerationError) as ei:
            _scan_sql_tokens(sql)
        assert ei.value.kind == "COMMENT_LINE"
        assert "must not contain comments" in str(ei.value)

    def test_block_comment_rejected(self):
        sql = "SELECT * FROM t WHERE col = ? /* some annotation */"
        with pytest.raises(QueryGenerationError) as ei:
            _scan_sql_tokens(sql)
        assert ei.value.kind == "COMMENT_BLOCK"
        assert "must not contain comments" in str(ei.value)

    def test_comment_inside_string_does_not_trigger_rejection(self):
        """``--`` inside a string literal is regular character data."""
        sql = "SELECT * FROM t WHERE name = '-- not a comment' AND col = ?"
        tokens, _ = _scan_sql_tokens(sql)
        placeholders = [t for t in tokens if t.kind == "PLACEHOLDER"]
        assert len(placeholders) == 1
        # The ``--`` lives inside an SQ_STRING token; no COMMENT_LINE token emitted.
        kinds = [t.kind for t in tokens]
        assert "COMMENT_LEADER" not in kinds
        assert "PLACEHOLDER" in kinds


class TestEofHardFail:
    def test_unterminated_single_quote_string_rejected(self):
        sql = "SELECT * FROM t WHERE name = 'O'Bri AND col = ?"
        # SQLite/KaiwuDB would treat ``'O'`` as a string and continue; our
        # explicit scanner sees ``'O'`` close, then ``Bri AND col = ?`` SQL, so
        # this case actually parses OK. Use a definite unterminated string:
        sql = "SELECT * FROM t WHERE name = 'unterminated AND col = ?"
        with pytest.raises(QueryGenerationError) as ei:
            _extract_placeholders(sql)
        assert ei.value.kind == "UNTERMINATED_SQ_STRING"

    def test_unterminated_double_quote_identifier_rejected(self):
        sql = 'SELECT * FROM t WHERE "weird name AND col = ?'
        with pytest.raises(QueryGenerationError) as ei:
            _extract_placeholders(sql)
        assert ei.value.kind == "UNTERMINATED_DQ_STRING"

    def test_string_literal_ending_at_eof_is_closed(self):
        """SQL ending at a closing ``'`` must NOT be flagged unterminated.

        Regression: 2026-07-17 shig smoke — ``INTERVAL '1 hour'`` at the
        end of the SQL tripped a false ``UNTERMINATED_SQ_STRING`` because
        the inner ``while i < n`` exhausted the cursor without
        distinguishing "ran out of chars mid-string" from "closed at EOF".
        """
        sql = "SELECT 1 FROM t WHERE ts > NOW() - INTERVAL '1 hour'"
        tokens, final_state = _scan_sql_tokens(sql)
        assert final_state == "NORMAL"
        sqs = [t for t in tokens if t.kind == "SQ_STRING"]
        assert len(sqs) == 1
        assert sqs[0].text == "'1 hour'"

    def test_double_quoted_identifier_ending_at_eof_is_closed(self):
        sql = 'SELECT * FROM "Foo"'
        tokens, final_state = _scan_sql_tokens(sql)
        assert final_state == "NORMAL"
        dqs = [t for t in tokens if t.kind == "DQ_STRING"]
        assert len(dqs) == 1
        assert dqs[0].text == '"Foo"'


class TestUnsupportedOperators:
    def test_limit_placeholder_rejected(self):
        from jmx_skeleton_generator.generators.query_groups import (
            generate_param_binding_script,
        )

        sql = "SELECT * FROM db.t LIMIT ?"
        with pytest.raises(QueryGenerationError) as ei:
            generate_param_binding_script(sql)
        assert ei.value.kind in {"UNSUPPORTED_OPERATOR", "UNRESOLVED_COLUMN"}
        assert "LIMIT" in str(ei.value)

    def test_between_placeholder_rejected(self):
        from jmx_skeleton_generator.generators.query_groups import (
            generate_param_binding_script,
        )

        sql = "SELECT * FROM db.t WHERE col BETWEEN ? AND ?"
        with pytest.raises(QueryGenerationError) as ei:
            generate_param_binding_script(sql)
        assert "cannot bind placeholder" in str(ei.value)

    def test_is_null_placeholder_rejected(self):
        """``IS NULL ?`` — placeholder directly follows the literal ``IS NULL``."""
        from jmx_skeleton_generator.generators.query_groups import (
            generate_param_binding_script,
        )

        sql = "SELECT * FROM db.t WHERE col IS NULL ?"
        with pytest.raises(QueryGenerationError) as ei:
            generate_param_binding_script(sql)
        assert "cannot bind placeholder" in str(ei.value)

    def test_is_placeholder_rejected(self):
        """``IS ?`` (parameterised NULL check) is also unsupported."""
        from jmx_skeleton_generator.generators.query_groups import (
            generate_param_binding_script,
        )

        sql = "SELECT * FROM db.t WHERE col IS ?"
        with pytest.raises(QueryGenerationError) as ei:
            generate_param_binding_script(sql)
        assert ei.value.kind == "UNSUPPORTED_OPERATOR"
        assert "IS" in str(ei.value)
