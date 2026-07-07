"""Backward-compatibility tests for the dedicated write-side error type."""

from __future__ import annotations

import pytest

from ddl_generator.generator import DdlGenerationError
from direct_insert_write import DirectInsertGenerationError


class TestErrorTypeContracts:
    def test_direct_insert_inherits_from_ddl_generation_error(self):
        # Backward compat: project-wide ``except DdlGenerationError``
        # must continue to catch direct-insert failures.
        assert issubclass(DirectInsertGenerationError, DdlGenerationError)

    def test_direct_insert_raised_caught_as_ddl_generation(self):
        with pytest.raises(DdlGenerationError):
            raise DirectInsertGenerationError("boom")

    def test_direct_insert_caught_as_its_own_type(self):
        with pytest.raises(DirectInsertGenerationError):
            raise DirectInsertGenerationError("boom")
