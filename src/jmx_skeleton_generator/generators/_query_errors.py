"""Query-generation exception type.

Single error class used for every rejection path in
:mod:`jmx_skeleton_generator.generators.query_groups`. The error
message is human-readable; callers identify the failure category by
grepping the message text or by inspecting the optional ``kind`` field.

Design: openspec/changes/query-functionality/design.md decision 15.

Public surface
--------------

- :class:`QueryGenerationError` — raise with a message; optional
  ``kind`` is a short tag (e.g. ``"LIMIT_NOT_SUPPORTED"``,
  ``"UNTERMINATED_SQ_STRING"``) used by tests to assert against
  documented behaviour.
"""

from __future__ import annotations

from typing import Optional


class QueryGenerationError(Exception):
    """Raised when the query generator rejects an SQL template."""

    def __init__(
        self,
        message: str,
        *,
        sql: Optional[str] = None,
        position: Optional[int] = None,
        kind: Optional[str] = None,
    ) -> None:
        self.sql = sql
        self.position = position
        self.kind = kind
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover — trivial
        return super().__str__()
