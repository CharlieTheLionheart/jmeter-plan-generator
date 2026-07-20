"""Tests that ``calculateLocalDeviceStart`` is the single source of
device-start arithmetic across ``batch_prepared`` (JSR223PreProcessor)
and ``single_prepared`` (JSR223PreProcessor inline) callers.

Closes multi-end-coordination design §"单一设备号计算 helper".
"""

from __future__ import annotations

from jmx_skeleton_generator.generators.write_groups import build_batch_prepared_preprocessor_script
from write_strategies.single_prepared_strategy import SinglePreparedStatementStrategy
from write_strategies.models import ResolvedTable, WriteRuntime


class TestSingleSourceHelper:
    def test_batch_prepared_preprocessor_uses_helper(self):
        script = build_batch_prepared_preprocessor_script(
            table_name="db.t", first_ptag="ptag_varchar_1",
            batch_lines=1, ms_step=1000,
        )
        # Helper invoked inside the body.
        assert "calculateLocalDeviceStart(" in script

    def test_batch_prepared_preprocessor_body_uses_helper(self):
        """After the helpers are prepended, the *body* section of
        ``build_batch_prepared_preprocessor_script`` must call the helper
        rather than inline the formula. The helper decl itself contains
        ``threadNum * devicePerThread`` — that's expected; we slice off
        the decls prefix and check the body."""
        script = build_batch_prepared_preprocessor_script(
            table_name="db.t", first_ptag="ptag_varchar_1",
            batch_lines=1, ms_step=1000,
        )
        body = script.split(
            "// -------- batch_prepared: JSR223Sampler body --------"
        )[-1] if False else script
        # Split off the all_groovy_decls prefix by finding the body's
        # comment marker.
        from utils.preprocessor_helpers import all_groovy_decls
        decls = all_groovy_decls()
        assert script.startswith(decls)
        body = script[len(decls):]
        assert "calculateLocalDeviceStart(" in body
        # The naked expression must NOT appear in the body (it's only
        # inside the helper definition).
        assert "threadNum * devicePerThread" not in body

    def test_single_prepared_preprocessor_uses_helper(self):
        s = SinglePreparedStatementStrategy()
        script = s.get_preprocessor_code(
            ResolvedTable(fqn="db.t", columns=["ts", "c1"]),
            batch_lines=1,
            runtime=WriteRuntime(device_per_thread=1),
        )
        assert "calculateLocalDeviceStart(" in script

    def test_helper_name_byte_equal_across_two_callers(self):
        """Both batch_prepared and single_prepared invoke the SAME helper name
        with the SAME casing — eliminates any future drift."""
        from write_strategies.batch_prepared_strategy import (
            BatchPreparedStatementStrategy,
        )

        # single_prepared
        single_script = SinglePreparedStatementStrategy().get_preprocessor_code(
            ResolvedTable(fqn="db.t", columns=["c1"]),
            batch_lines=1,
            runtime=WriteRuntime(device_per_thread=1),
        )
        assert "calculateLocalDeviceStart(0L, threadNum, devicePerThread)" in single_script

        # batch_prepared
        batch_script = build_batch_prepared_preprocessor_script(
            table_name="db.t", first_ptag="ptag_varchar_1",
            batch_lines=1, ms_step=1000,
        )
        assert (
            "calculateLocalDeviceStart(deviceStart, threadNum, devicePerThread)"
            in batch_script
        )

        # Both call the SAME function; verify the function-name token matches
        # the all-groovy-decls declaration exactly.
        from utils.preprocessor_helpers import (
            groovy_calculate_local_device_start_decl,
        )

        decl = groovy_calculate_local_device_start_decl()
        assert "long calculateLocalDeviceStart" in decl
