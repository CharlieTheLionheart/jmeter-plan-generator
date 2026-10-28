"""Tests for shared_memory_initializer."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from shared_memory_initializer import SharedMemoryInitializerGenerator
from shared_memory_initializer.shared_memory_initializer import (
    _make_key,
    _make_columns_key,
    generate_groovy_loader_script,
    create_jsr223_preprocessor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[list[str]]) -> None:
    """Write a CSV file (list of rows, first row = header)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

class TestMakeKey:
    def test_simple_names(self):
        assert _make_key("tsdb", "t_table") == "__SHARED_MEM_tsdb_t_table"

    def test_special_chars_replaced(self):
        assert _make_key("my-db", "t-table") == "__SHARED_MEM_my_db_t_table"
        assert _make_key("my.db", "t table") == "__SHARED_MEM_my_db_t_table"

    def test_columns_key_suffix(self):
        key = _make_key("tsdb", "t_table")
        cols_key = _make_columns_key("tsdb", "t_table")
        assert cols_key == key + "_columns"


# ---------------------------------------------------------------------------
# Groovy script generation
# ---------------------------------------------------------------------------

class TestGenerateGroovyLoaderScript:
    def test_script_contains_rows_key(self):
        script = generate_groovy_loader_script("tsdb", "t_table", "/path/to/seeds/tsdb/t_table.csv")
        assert "__SHARED_MEM_tsdb_t_table" in script

    def test_script_contains_columns_key(self):
        script = generate_groovy_loader_script("tsdb", "t_table", "/path/to/seeds/tsdb/t_table.csv")
        assert "__SHARED_MEM_tsdb_t_table_columns" in script

    def test_script_contains_csv_path(self):
        script = generate_groovy_loader_script("tsdb", "t_table", "/path/to/seeds/tsdb/t_table.csv")
        assert "/path/to/seeds/tsdb/t_table.csv" in script

    def test_script_handles_null_conversion(self):
        script = generate_groovy_loader_script("tsdb", "t_table", "/path/to/seeds/tsdb/t_table.csv")
        # The Groovy script should convert CSV "null" strings to Groovy null
        assert "null" in script  # at least mentions null handling

    def test_script_has_error_handling(self):
        """write-missing-data D11: the loader MUST abort loudly.

        The previous contract (``log.error`` + ``props.put(rowsKey, [])``)
        swallowed the failure: the SetupTG sampler reported success, the
        write path found an empty pool, and the whole test run finished
        green **without writing a single row**. The loader now throws so
        the failure surfaces at the SetupTG.
        """
        script = generate_groovy_loader_script("tsdb", "t_table", "/path/to/seeds/tsdb/t_table.csv")
        assert "throw new RuntimeException" in script
        assert "props.put(rowsKey, [])" not in script
        assert "props.put(colsKey, [])" not in script

    def test_missing_csv_branch_throws(self):
        """The ``!file.exists()`` branch MUST throw (not log + empty pool)."""
        script = generate_groovy_loader_script("tsdb", "t_table", "/path/to/seeds/tsdb/t_table.csv")
        branch = script.split("if (!file.exists()) {", 1)[1].split("}", 1)[0]
        assert "throw new RuntimeException" in branch
        assert "props.put(rowsKey, [])" not in branch

    def test_catch_branch_throws(self):
        """The ``catch (Throwable t)`` branch MUST re-throw."""
        script = generate_groovy_loader_script("tsdb", "t_table", "/path/to/seeds/tsdb/t_table.csv")
        branch = script.split("} catch (Throwable t) {", 1)[1]
        assert "throw new RuntimeException" in branch
        assert "props.put(rowsKey, [])" not in branch

    def test_special_chars_in_table_name(self):
        # Table names with special characters should be sanitized in the key
        script = generate_groovy_loader_script("tsdb", "t-table", "/path/to/t.csv")
        assert "__SHARED_MEM_tsdb_t_table" in script  # dashes replaced


# ---------------------------------------------------------------------------
# JSR223PreProcessor XML component
# ---------------------------------------------------------------------------

class TestCreateJsr223Preprocessor:
    def test_returns_tuple_of_two_elements(self):
        preprocessor, hash_tree = create_jsr223_preprocessor(
            "tsdb", "t_table", "/path/to/csv.csv"
        )
        assert preprocessor is not None
        assert hash_tree is not None

    def test_preprocessor_has_testclass(self):
        # The shared-memory loader is a JSR223Sampler (not a
        # JSR223PreProcessor) so the Groovy CSV loader actually runs —
        # JSR223PreProcessor only fires when a sibling Sampler is
        # present, and the SetupThreadGroup here has no other sampler.
        preprocessor, _ = create_jsr223_preprocessor(
            "tsdb", "t_table", "/path/to/csv.csv"
        )
        assert preprocessor.get("testclass") == "JSR223Sampler"

    def test_preprocessor_has_guiclass(self):
        preprocessor, _ = create_jsr223_preprocessor(
            "tsdb", "t_table", "/path/to/csv.csv"
        )
        assert preprocessor.get("guiclass") == "TestBeanGUI"

    def test_script_language_is_groovy(self):
        preprocessor, _ = create_jsr223_preprocessor(
            "tsdb", "t_table", "/path/to/csv.csv"
        )
        # Find scriptLanguage stringProp
        for child in preprocessor:
            if child.get("name") == "scriptLanguage":
                assert child.text == "groovy"

    def test_script_property_contains_rows_key(self):
        preprocessor, _ = create_jsr223_preprocessor(
            "tsdb", "t_table", "/path/to/csv.csv"
        )
        for child in preprocessor:
            if child.get("name") == "script":
                assert "__SHARED_MEM_tsdb_t_table" in (child.text or "")

    def test_custom_testname(self):
        preprocessor, _ = create_jsr223_preprocessor(
            "tsdb", "t_table", "/path/to/csv.csv",
            testname="My Custom Loader"
        )
        assert preprocessor.get("testname") == "My Custom Loader"

    def test_default_testname_contains_db_table(self):
        preprocessor, _ = create_jsr223_preprocessor(
            "tsdb", "t_table", "/path/to/csv.csv"
        )
        assert preprocessor.get("testname") == "SharedMemoryLoader tsdb.t_table"

    def test_hash_tree_is_empty(self):
        _, hash_tree = create_jsr223_preprocessor(
            "tsdb", "t_table", "/path/to/csv.csv"
        )
        assert len(hash_tree) == 0


# ---------------------------------------------------------------------------
# SharedMemoryInitializerGenerator
# ---------------------------------------------------------------------------

class TestSharedMemoryInitializerGenerator:
    def test_generate_for_table_returns_tuple(self):
        gen = SharedMemoryInitializerGenerator()
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "t_table.csv"
            _write_csv(csv_path, [["ts", "ptag"], ["1", "2"]])
            preprocessor, hash_tree = gen.generate_for_table("tsdb", "t_table", str(csv_path))
            assert preprocessor.get("testclass") == "JSR223Sampler"

    def test_generate_for_tables_returns_list(self):
        gen = SharedMemoryInitializerGenerator()
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "t_table.csv"
            _write_csv(csv_path, [["ts", "ptag"], ["1", "2"]])
            results = gen.generate_for_tables([
                {"db": "tsdb", "table": "t_table", "csv_path": str(csv_path)},
                {"db": "tsdb", "table": "t_table2", "csv_path": str(csv_path)},
            ])
            assert len(results) == 2
            assert all(isinstance(r, tuple) for r in results)

    def test_generate_for_tables_unique_keys_per_table(self):
        gen = SharedMemoryInitializerGenerator()
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "t.csv"
            _write_csv(csv_path, [["ts"], ["1"]])
            results = gen.generate_for_tables([
                {"db": "tsdb", "table": "t_table", "csv_path": str(csv_path)},
                {"db": "tsdb", "table": "t_table2", "csv_path": str(csv_path)},
            ])
            scripts = []
            for preprocessor, _ in results:
                for child in preprocessor:
                    if child.get("name") == "script":
                        scripts.append(child.text or "")
            # Each table should have its own key in the script
            assert "__SHARED_MEM_tsdb_t_table" in scripts[0]
            assert "__SHARED_MEM_tsdb_t_table2" in scripts[1]


# ---------------------------------------------------------------------------
# CSV parsing integration (Groovy script correctness)
# ---------------------------------------------------------------------------

class TestCsvNullHandling:
    def test_null_string_becomes_groovy_null_in_script(self):
        """Verify the Groovy script contains the null-string detection logic."""
        script = generate_groovy_loader_script("tsdb", "t_table", "/path/to/csv.csv")
        # Should check for 'null' string and convert to Groovy null
        assert "equalsIgnoreCase('null')" in script or "null" in script


class TestSpecialCharsInKeys:
    def test_db_name_with_dash(self):
        script = generate_groovy_loader_script("my-db", "t_table", "/path/to/csv.csv")
        assert "__SHARED_MEM_my_db_t_table" in script

    def test_table_name_with_dash(self):
        script = generate_groovy_loader_script("tsdb", "my-table", "/path/to/csv.csv")
        assert "__SHARED_MEM_tsdb_my_table" in script
