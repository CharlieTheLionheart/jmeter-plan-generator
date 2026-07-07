"""Errors raised by ``direct_insert_write``.

DirectInsertGenerationError subclasses :class:`ddl_generator.generator.DdlGenerationError`
so callers using ``except DdlGenerationError`` upstream continue to catch
boundary failures from INSERT/PreProcessor/Sampler generation. The dedicated
type exists so stack traces and ``except`` blocks can target write-side
failures specifically.
"""

from __future__ import annotations

from ddl_generator.generator import DdlGenerationError


class DirectInsertGenerationError(DdlGenerationError):
    """Raised when direct-INSERT write generation fails validation.

    Inherits :class:`DdlGenerationError` for backward compatibility with
    callers using a project-wide ``except DdlGenerationError``.
    """
