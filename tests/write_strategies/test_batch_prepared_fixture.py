"""Literal-output fixture for the batch_prepared sampler script.

Closes review.md §3 "测试覆盖" gap:
- Spec needs an explicit expected-output example for the batch_prepared
  Groovy sampler body so reviewers and downstream consumers share one
  canonical reference.

The fixture lives at
``openspec/changes/write-strategies/specs/write-strategies/fixtures/batch_prepared_sampler.groovy``
and is referenced by spec.md "Literal-output fixture" scenario.
"""

from __future__ import annotations

from pathlib import Path

from write_strategies.batch_prepared_strategy import BatchPreparedStatementStrategy
from write_strategies.models import ResolvedTable


_FIXTURE_REL = Path(
    "openspec/changes/write-strategies/specs/write-strategies/fixtures/"
    "batch_prepared_sampler.groovy"
)

_CANONICAL_FQN = "iot_monitor.sensor_readings"
_CANONICAL_COLUMNS = ["ts", "device_id", "val"]
_CANONICAL_BATCH_LINES = 10


def _resolved() -> ResolvedTable:
    return ResolvedTable(fqn=_CANONICAL_FQN, columns=list(_CANONICAL_COLUMNS))


class TestBatchPreparedSamplerFixture:
    def test_groovy_literal_output_matches_fixture(self):
        repo_root = Path(__file__).resolve().parents[2]
        fixture = (repo_root / _FIXTURE_REL).read_text(encoding="utf-8")
        script = BatchPreparedStatementStrategy().get_sampler_script(
            _resolved(), batch_lines=_CANONICAL_BATCH_LINES
        )
        assert script == fixture

    def test_groovy_structure_contains_param_vars(self):
        script = BatchPreparedStatementStrategy().get_sampler_script(
            _resolved(), batch_lines=1
        )
        assert "vars.get" in script

    def test_groovy_structure_contains_rollback(self):
        """review.md §1 + tasks.md §11.1: batch_prepared must roll back on SQLException."""
        script = BatchPreparedStatementStrategy().get_sampler_script(
            _resolved(), batch_lines=1
        )
        assert "rollback" in script
