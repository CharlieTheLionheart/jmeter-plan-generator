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

    def test_script_falls_back_to_device_id_when_no_match(self):
        """design decision 17 / tasks §4.6: missing seed file → device-id fallback.

        F-4 (2026-07-20): the previous ``['null']`` fallback passed the
        string ``"null"`` through the ``"null".equalsIgnoreCase ? "" : raw``
        ternary, which silently bound ``param_N`` to the empty string.
        Queries like ``WHERE ptag_varchar_1 = ${param_N}`` then became
        ``WHERE ptag_varchar_1 =`` and failed with
        ``at or near "EOF": syntax error``. The new fallback derives a
        device-id-shaped default (``device_<device_start>``) so the
        query gets a valid ptag value.
        """
        sql = "SELECT * FROM db.t WHERE col_int8_1 = ?"
        script = generate_param_binding_script(sql)
        assert "device_start" in script, (
            "fallback must derive a device-id-shaped default from the "
            "device_start UDV so queries filtering on the first ptag "
            "(whose seed is virtual) get a valid value (F-4)"
        )
        # The literal ``['null']`` fallback path must be gone.
        assert "['null']" not in script
        # The "null"-ternary must also be gone — it was the silent
        # empty-binding trap that produced the EOF syntax error.
        assert 'equalsIgnoreCase(raw_' not in script

    def test_param_never_binds_to_empty_string(self):
        """F-4 regression: the runtime ``vars.put`` must always receive
        a non-empty value. Previously the ``"null".equalsIgnoreCase(raw)
        ? "" : raw`` ternary collapsed the explicit ``'null'`` fallback
        list down to the empty string, producing ``WHERE ptag_varchar_1
        =`` and ``at or near "EOF": syntax error``.
        """
        sql = "SELECT * FROM db.t WHERE col_int8_1 = ?"
        script = generate_param_binding_script(sql)
        # The runtime binding must be unconditional ``vars.put(...,
        # raw_N)`` — no ternary, no empty-string branch.
        assert 'vars.put("param_0", raw_0)' in script, (
            "param binding must write raw_N directly to vars without "
            "the empty-string ternary (F-4)"
        )
