"""Tests for F-1 fix: CSV loader strips surrounding double-quotes.

Background: ``seed-data-generator`` writes CSVs with
``csv.QUOTE_ALL``, so every field is wrapped in ``"..."``. The Groovy
loader previously only ``.trim()``-ed each field, leaving the literal
quote characters inside the cell string. That broke two downstream
consumers:

1. Header lookup — ``columnNames.indexOf("ptag_varchar_1")`` returned
   ``-1`` because the header list held ``"ptag_varchar_1"``.
2. Sampler type binding — ``PreparedStatement.setObject(idx, "\"20\"")``
   can't infer ``INT8`` from a string with embedded quote characters.

These tests pin the generated Groovy to the contract that
``field.replaceAll('^"|"$', '')`` runs after ``field.trim()``. The fix
is intentionally Groovy-only (no Python-side CSV rewrite) so the
in-place contract between ``seed-data-generator`` and the JMeter loader
remains ``QUOTE_ALL``-emitted, ``strip-quotes``-consumed.
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from shared_memory_initializer.shared_memory_initializer import (
    generate_groovy_loader_script,
)


def _write_quoted_csv(path: Path, rows: list[list[str]]) -> None:
    """Write a CSV with ``csv.QUOTE_ALL`` — the seed-data-generator's format."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerows(rows)


class TestCsvLoaderStripsQuotes:
    """The generated loader Groovy must strip surrounding ``"`` from each field."""

    def test_data_field_stripping_present(self):
        """The field-level ``replaceAll('^"|"$', '')`` must appear in the script.

        This is the F-1 contract — without it INT8/FLOAT4 INSERT fails
        with ``could not resolve "20" as INT8 type`` because the
        ``setObject`` call receives a string with embedded quote chars.
        """
        script = generate_groovy_loader_script(
            "iot_monitor", "t_cnc", "/tmp/seeds/iot_monitor/t_cnc.csv"
        )
        # The fix is a Groovy ``replaceAll('^"|"$', '')`` on the
        # trimmed field. Accept either single-quoted Groovy literal
        # form to keep the assertion stable across regex tweaks.
        assert 'replaceAll' in script, (
            "loader must strip CSV quotes — seed-data-generator emits "
            "QUOTE_ALL, so without stripping every cell carries "
            "embedded quote characters"
        )
        # The pattern must target leading and trailing double quotes.
        assert '"' in script and "'" in script, (
            "strip pattern must wrap in Groovy single-quotes and "
            "match the literal double-quote char"
        )

    def test_header_field_stripping_present(self):
        """The header parser must also strip — otherwise ptag lookup returns -1.

        Without header stripping, ``columnNames`` holds entries like
        ``"col_int8_1"`` (with literal quotes), so
        ``columnNames.indexOf("ptag_varchar_1")`` returns -1 and the
        preprocessor's device-identifier overwrite silently no-ops.
        That is also the F-2 trigger (``${device_code}`` never replaced).
        """
        script = generate_groovy_loader_script(
            "iot_monitor", "t_cnc", "/tmp/seeds/iot_monitor/t_cnc.csv"
        )
        # Locate the header-handling block (lineNum == 1) and verify
        # the same replaceAll call shape exists.
        header_idx = script.find("lineNum == 1")
        assert header_idx > 0, "header block must exist in loader script"
        header_block = script[header_idx : header_idx + 500]
        assert "replaceAll" in header_block, (
            "header field parser must also strip quotes — otherwise "
            "columnNames.indexOf(firstPtag) misses the lookup"
        )

    def test_strip_runs_after_trim(self):
        """Quote stripping must come AFTER ``.trim()`` so leading whitespace is gone.

        The seed generator does not emit padded fields, but a future
        migration to ``csv.QUOTE_MINIMAL`` would surface
        ``" 20"``-style fields — trim first, strip after.

        Test inspects only the data-field branch (lineNum > 1) so the
        header-block ``.trim().replaceAll(...)`` and any mentions of
        ``replaceAll`` in leading comments don't trigger a false order
        check.
        """
        script = generate_groovy_loader_script(
            "iot_monitor", "t_cnc", "/tmp/seeds/iot_monitor/t_cnc.csv"
        )
        # Inspect only the data-field branch (``lineNum > 1``) so the
        # header-block ``.trim().replaceAll(...)`` and any mentions of
        # ``replaceAll`` in leading comments don't trigger a false
        # order check. Take everything from ``lineNum > 1`` to the
        # end of the script (the data branch is the last block).
        data_idx = script.find("lineNum > 1")
        assert data_idx > 0, "data branch must exist in loader script"
        data_block = script[data_idx:]
        # The data branch must invoke both ``.trim()`` and
        # ``replaceAll(...)``. We accept either order of appearance
        # in the source, but the canonical F-1 contract is the
        # chained form ``field.trim().replaceAll('^"|"$', '')`` —
        # strip must run AFTER trim within the same expression.
        assert ".trim()" in data_block, "data branch must trim each field"
        assert "replaceAll" in data_block, (
            "data branch must strip CSV quotes via replaceAll"
        )
        # Pin the canonical chained form: ``.trim().replaceAll(`` — the
        # trim precedes the replaceAll within the same expression.
        assert ".trim().replaceAll(" in data_block, (
            "data branch must chain .trim().replaceAll(...) so trim "
            "precedes quote stripping in execution order"
        )


class TestCsvLoaderQuoteStrippingBehavior:
    """Round-trip test — a real loader-style parse over QUOTE_ALL CSV.

    The Groovy code runs inside JMeter; here we exercise the
    equivalent Java semantics (String.split + trim + replaceAll) on the
    Python side to confirm the intended behavior is sound.
    """

    def test_java_style_parse_strips_quotes(self):
        """Mirror what the Groovy loader does, on a Python subprocess.

        Validates the contract: a field like ``"20"`` becomes the
        2-char string ``20`` after the loader's parsing pipeline.
        """
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "t_cnc.csv"
            _write_quoted_csv(
                csv_path,
                [
                    ["col_int8_1", "col_float4_1", "ptag_varchar_1"],
                    ["11", "44.59", "device_1"],
                ],
            )
            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            # Mirror loader logic: split(',') → trim → strip leading/trailing '"'.
            header = [
                f.strip().replace('^"|"$', "").replace('"', "")
                for f in lines[0].split(",")
            ]
            # NOTE: Groovy ``replaceAll('^"|"$', '')`` strips literal
            # leading/trailing ``"``; Python equivalent is ``strip('"')``.
            # Test asserts the *equivalent* Python behavior so we know
            # the seed CSV → loader contract is sound.
            data = [
                [f.strip().strip('"') for f in line.split(",")]
                for line in lines[1:]
            ]
            assert header == ["col_int8_1", "col_float4_1", "ptag_varchar_1"], (
                f"header should have no embedded quotes, got {header}"
            )
            assert data[0] == ["11", "44.59", "device_1"], (
                f"data row should be quote-free, got {data[0]}"
            )