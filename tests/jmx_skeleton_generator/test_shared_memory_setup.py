"""Tests for the shared-memory SetupThreadGroup generator.

F-5 (2026-07-20): the SetupThreadGroup's ``duration=1`` was too short
for 5+ table loaders — the scheduler cut the thread before the last
JSR223PreProcessor ran, leaving the Write PreProcessor's
``__SHARED_MEM_{db}_{table}`` lookup null. Raised to ``60s``.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from jmx_skeleton_generator.generators.shared_memory_setup import (
    generate_shared_memory_setup_thread_group,
)


class TestSetupThreadGroupDuration:
    def test_duration_is_at_least_30_seconds(self):
        """SetupThreadGroup must give loaders enough time to finish.

        With 5+ table loaders, durations under ~10s left the
        scheduler cutting the thread before the last loader ran.
        Pin the floor at 30s so a future tweak can't quietly
        re-introduce the flake (F-5).
        """
        seed_csv_paths = {
            "db1": {"t1": "/tmp/t1.csv", "t2": "/tmp/t2.csv"},
        }
        elements = generate_shared_memory_setup_thread_group(seed_csv_paths)
        # The first element is the SetupThreadGroup; the second is its
        # hashTree opener.
        stg = elements[0]
        xml = ET.tostring(stg, encoding="unicode")
        # Pull the duration stringProp value.
        import re
        match = re.search(r'name="ThreadGroup\.duration">(\d+)', xml)
        assert match is not None, "SetupThreadGroup must set a duration"
        duration = int(match.group(1))
        assert duration >= 30, (
            f"SetupThreadGroup.duration must be >= 30s (got {duration}); "
            f"durations under ~10s leave loaders unfinished and the "
            f"Write PreProcessor's sharedRows lookup returns null (F-5)"
        )

    def test_loops_is_one(self):
        """``loops=1`` keeps loaders single-shot — no duplicate writes to props."""
        seed_csv_paths = {"db1": {"t1": "/tmp/t1.csv"}}
        elements = generate_shared_memory_setup_thread_group(seed_csv_paths)
        stg = elements[0]
        xml = ET.tostring(stg, encoding="unicode")
        assert 'LoopController.loops">1' in xml, (
            "SetupThreadGroup must have loops=1 so each loader runs "
            "exactly once (no duplicate props writes)"
        )
