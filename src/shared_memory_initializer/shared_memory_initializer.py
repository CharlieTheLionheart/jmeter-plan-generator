"""Shared memory initializer - generates Groovy CSV loader scripts and JSR223 XML.

Design: openspec/changes/shared-memory-initializer/design.md
Spec:    openspec/changes/shared-memory-initializer/specs/shared-memory-initialization/spec.md
Tasks:   openspec/changes/shared-memory-initializer/tasks.md
"""

from __future__ import annotations

import csv
import logging
import os
import re
from typing import List, Optional, Tuple

from xml.etree import ElementTree as ET

from utils.xml_helpers import (
    JMETER_NS,
    empty_hash_tree,
    jsr223_preprocessor_element,
    jsr223_sampler_element,
    string_prop,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key names in JMeter props
# ---------------------------------------------------------------------------

def _make_key(db: str, table: str) -> str:
    """Build shared-memory key for a table, replacing special chars with underscores."""
    safe_db = re.sub(r"[^a-zA-Z0-9_]", "_", db)
    safe_table = re.sub(r"[^a-zA-Z0-9_]", "_", table)
    return f"__SHARED_MEM_{safe_db}.{safe_table}"


def _make_columns_key(db: str, table: str) -> str:
    """Build shared-memory key for column list."""
    return _make_key(db, table) + "_columns"


# ---------------------------------------------------------------------------
# Groovy script generation
# ---------------------------------------------------------------------------

def generate_groovy_loader_script(
    db: str,
    table: str,
    csv_path: str,
) -> str:
    """Generate a Groovy script that loads a CSV file into JMeter shared memory.

    Parameters
    ----------
    db:
        Database name (used in the shared-memory key).
    table:
        Table name (used in the shared-memory key).
    csv_path:
        Absolute or relative path to the CSV seed file.

    Returns
    -------
    A Groovy script string that reads the CSV, stores the row list and column
    list in ``props``, and handles errors gracefully.

    Shared memory keys stored:
        - ``__SHARED_MEM_{db}.{table}``   → List[List[Any]] (row-first)
        - ``__SHARED_MEM_{db}.{table}_columns`` → List[String]

    CSV format (from seed-data-generator):
        - First line: column names (header)
        - Subsequent lines: data rows
        - CSV string ``null`` → Groovy ``null`` object
    """
    rows_key = _make_key(db, table)
    cols_key = _make_columns_key(db, table)

    # Escape single-quotes in Groovy string literals
    safe_csv_path = csv_path.replace("\\", "\\\\").replace("'", "\\'")

    script = f"""\
import java.io.File

def csvPath = '{safe_csv_path}'
def rowsKey = '{rows_key}'
def colsKey = '{cols_key}'

try {{
    def file = new File(csvPath)
    if (!file.exists()) {{
        log.error("SharedMemoryLoader: CSV file not found: " + csvPath)
        props.put(rowsKey, [])
        props.put(colsKey, [])
        return
    }}

    def rows = []
    def columns = []

    file.eachLine {{ line, lineNum ->
        if (lineNum == 1) {{
            // Header line: parse column names. CSV is simple
            // comma-separated in the SVT seed format; use Groovy native
            // ``String.split`` instead of OpenCSV to drop the
            // jmeter-lib dependency.
            def headerFields = (line.split(',') as List<String>)
            if (headerFields != null) {{
                columns = headerFields.collect {{ it != null ? it.trim() : it }}
            }}
        }} else if (lineNum > 1) {{
            // Data line
            if (line == null || line.trim().isEmpty()) {{
                return  // skip blank lines
            }}
            def fields = (line.split(',') as List<String>)
            if (fields != null) {{
                def row = fields.collect {{ field ->
                    if (field == null) {{
                        return null
                    }}
                    def trimmed = field.trim()
                    if (trimmed.equalsIgnoreCase('null') || trimmed.isEmpty()) {{
                        return null
                    }}
                    return trimmed
                }}
                rows.add(row)
            }}
        }}
    }}

    props.put(colsKey, columns)
    props.put(rowsKey, rows)

    log.info("SharedMemoryLoader: loaded " + rows.size() + " rows for " + rowsKey)

}} catch (Throwable t) {{
    log.error("SharedMemoryLoader: failed to load CSV " + csvPath + ": " + t.getMessage())
    props.put(rowsKey, [])
    props.put(colsKey, [])
}}
"""
    return script


# ---------------------------------------------------------------------------
# JSR223PreProcessor XML component
# ---------------------------------------------------------------------------

def create_jsr223_preprocessor(
    db: str,
    table: str,
    csv_path: str,
    *,
    testname: Optional[str] = None,
) -> Tuple[ET.Element, ET.Element]:
    """Create a JSR223PreProcessor XML element that loads CSV into shared memory.

    Parameters
    ----------
    db:
        Database name.
    table:
        Table name.
    csv_path:
        Path to the CSV seed file.
    testname:
        Display name in the JMeter tree (defaults to "SharedMemoryLoader <db>.<table>").

    Returns
    -------
    A (JSR223PreProcessor element, hashTree element) tuple.
    """
    if testname is None:
        testname = f"SharedMemoryLoader {db}.{table}"

    groovy_script = generate_groovy_loader_script(db, table, csv_path)

    # Use JSR223Sampler (NOT JSR223PreProcessor) so the script actually
    # runs. JSR223PreProcessor only fires when a sibling Sampler is
    # present — and the SetupThreadGroup here has no other sampler, so
    # the CSV load was silently skipped in earlier builds.
    sampler, hash_tree = jsr223_sampler_element(
        name=f"SharedMemoryLoader_{db}_{table}",
        script=groovy_script,
        script_language="groovy",
        cache_key="true",
        testname=testname,
    )

    # Add the CSV path as a parameter property so it can be overridden
    # (not used in the inline script but available for external script mode)
    path_prop = string_prop("csvPath", csv_path)
    sampler.append(path_prop)

    return sampler, hash_tree


# ---------------------------------------------------------------------------
# Multi-table batch generation
# ---------------------------------------------------------------------------

class SharedMemoryInitializerGenerator:
    """Generates shared-memory loader components for one or more tables.

    Usage::

        generator = SharedMemoryInitializerGenerator()
        results = generator.generate_for_tables([
            {"db": "tsdb", "table": "t_table", "csv_path": "seeds/tsdb/t_table.csv"},
            {"db": "tsdb", "table": "t_table2", "csv_path": "seeds/tsdb/t_table2.csv"},
        ])
    """

    def generate_for_table(
        self,
        db: str,
        table: str,
        csv_path: str,
        *,
        testname: Optional[str] = None,
    ) -> Tuple[ET.Element, ET.Element]:
        """Generate loader components for a single table.

        Returns
        -------
        (JSR223PreProcessor element, hashTree element)
        """
        return create_jsr223_preprocessor(db, table, csv_path, testname=testname)

    def generate_for_tables(
        self,
        tables: List[dict],
    ) -> List[Tuple[ET.Element, ET.Element]]:
        """Generate loader components for multiple tables.

        Parameters
        ----------
        tables:
            List of dicts, each with keys ``db``, ``table``, ``csv_path``,
            and optionally ``testname``.

        Returns
        -------
        List of (JSR223PreProcessor element, hashTree element) tuples, one per table.
        """
        results = []
        for t in tables:
            result = self.generate_for_table(
                db=t["db"],
                table=t["table"],
                csv_path=t["csv_path"],
                testname=t.get("testname"),
            )
            results.append(result)
        return results
