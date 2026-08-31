"""Tests that ``calculateLocalDeviceStart`` is the single source of
device-start arithmetic inside ``batch_prepared`` (JSR223PreProcessor).

Closes multi-end-coordination design §"单一设备号计算 helper".

Note: 2026-08-31 refactor removed the ``write_strategies`` layer and the
``SinglePreparedStatementStrategy`` preprocessor code path; the
``single_prepared`` half of this test (used to live here) is no longer
applicable. Only the ``batch_prepared`` side survives.
"""

from __future__ import annotations

from jmx_skeleton_generator.generators.write_groups import build_batch_prepared_preprocessor_script


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

    def test_helper_decl_token_byte_equal(self):
        """The helper function name token embedded in the preprocessor body
        matches the ``all_groovy_decls`` declaration byte-for-byte — guards
        against silent drift between call site and helper definition."""
        from utils.preprocessor_helpers import (
            groovy_calculate_local_device_start_decl,
        )

        batch_script = build_batch_prepared_preprocessor_script(
            table_name="db.t", first_ptag="ptag_varchar_1",
            batch_lines=1, ms_step=1000,
        )
        assert (
            "calculateLocalDeviceStart(deviceStart, threadNum, devicePerThread)"
            in batch_script
        )

        decl = groovy_calculate_local_device_start_decl()
        assert "long calculateLocalDeviceStart" in decl