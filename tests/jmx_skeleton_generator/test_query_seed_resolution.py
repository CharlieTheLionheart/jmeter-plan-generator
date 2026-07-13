"""Tests for the seed-file resolution emitted by the generated Groovy script.

The generator emits Groovy into the JSR223PreProcessor, which runs at
JMeter runtime, so the actual ``File.listFiles()`` call is not
exercisable here. Instead, these tests assert the script's content
includes the multi-match detection guards introduced by design
decision 17.
"""

from __future__ import annotations

from jmx_skeleton_generator.generators.query_groups import (
    generate_param_binding_script,
)


class TestSeedFileResolution:
    def test_script_contains_column_lookup(self):
        sql = "SELECT * FROM db.t WHERE col_int8_1 = ?"
        script = generate_param_binding_script(sql)
        assert "tableDir.listFiles()" in script
        assert "_col_int8_1.csv" in script

    def test_script_contains_ambiguity_guard(self):
        """design decision 17: multi-file match logs an error and throws at runtime."""
        sql = "SELECT * FROM db.t WHERE col_int8_1 = ?"
        script = generate_param_binding_script(sql)
        assert "allMatches_" in script
        assert "size() > 1" in script
        assert "ambiguous seed files" in script

    def test_script_falls_back_to_null_when_no_match(self):
        """design decision 17 / tasks §4.6: missing seed file → ``'null'`` fallback."""
        sql = "SELECT * FROM db.t WHERE col_int8_1 = ?"
        script = generate_param_binding_script(sql)
        assert "['null']" in script
        assert "readLines() ?: ['null']" in script
