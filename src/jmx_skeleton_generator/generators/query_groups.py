"""Query ThreadGroup generators."""

from __future__ import annotations

import re
from typing import List, Tuple

from config_parser.models import QueryConfig
from utils.xml_helpers import (
    constant_throughput_timer_element,
    jdbc_sampler_element,
    jsr223_preprocessor_element,
    thread_group_element,
)


def _extract_table_path(sql: str) -> str | None:
    """Extract 'db.table' from the FROM clause of a SQL query.

    Scans FROM and JOIN clauses for patterns like ``db.table`` or ``table``.
    Returns the first match (single-table query assumption).
    Returns ``None`` if no table path could be resolved.
    """
    # Match FROM db.table or FROM table
    patterns = [
        r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b",
        r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, sql, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    return None


def _extract_placeholders(sql: str) -> List[Tuple[int, int]]:
    """Extract (start, end) positions of each ? placeholder in SQL.

    Skips ? inside string literals.
    """
    positions = []
    in_string = False
    string_char = None
    for i, ch in enumerate(sql):
        if ch in ("'", '"'):
            if not in_string:
                in_string = True
                string_char = ch
            elif string_char == ch:
                in_string = False
                string_char = None
        if not in_string and ch == "?":
            positions.append((i, i + 1))
    return positions


def _extract_column_context(sql: str, pos: int) -> str | None:
    """Extract column name just before the placeholder at SQL[pos].

    e.g.  "WHERE t_cnc.col_int8_1 = ?"  → "col_int8_1"
          "ptag_varchar_1 LIKE ?"         → "ptag_varchar_1"
    """
    prefix = sql[:pos].rstrip()

    match = re.search(
        r"([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\s*(?:=|<>|!=|<=|>=|<|>|LIKE|IN)\s*$",
        prefix,
        re.IGNORECASE,
    )
    if match:
        col_ref = match.group(1)
        return col_ref.split(".")[-1] if "." in col_ref else col_ref
    return None


def _build_query_param_script(sql: str, param_count: int, seed_dir: str) -> str:
    """Build the Groovy JSR223PreProcessor script for a query.

    Extracts db.table from the SQL to build the seed directory path
    (``seeds/{db}/{table}/``), then generates Groovy code that uses
    ``*_{col_name}.csv`` glob pattern to locate column seed files.

    Parameters
    ----------
    sql:
        The raw query SQL with ``?`` placeholders.
    param_count:
        Number of ``?`` placeholders (already computed by caller).
    seed_dir:
        JMeter variable referencing the seed directory
        (e.g. ``"${seed_dir}"``).

    Returns
    -------
    Groovy script string for the JSR223PreProcessor.
    """
    if param_count == 0:
        return "// No placeholders in query"

    table_path = _extract_table_path(sql)
    if not table_path:
        return f"// Could not resolve table path from query: {sql[:60]}..."

    placeholders = _extract_placeholders(sql)
    lines = [
        "// JSR223PreProcessor (groovy): 查询参数绑定",
        f"// Table: {table_path}",
        f"def seedDir = vars.get('seed_dir') ?: 'seeds'",
        f"def tableDir = new File(seedDir + '/{table_path}')",
        "",
    ]

    param_idx = 0
    for start, end in placeholders:
        col_name = _extract_column_context(sql, start)
        if col_name:
            # Seed file: seeds/{db}/{table}/*_{col_name}.csv
            # Use glob pattern to find the file (col_name is globally unique)
            lines.extend([
                f"// param_{param_idx}: {col_name}",
                f"def matched_{param_idx} = tableDir.listFiles()?.find{{ it.name.endsWith('_{col_name}.csv') }}",
                f"def lines_{param_idx} = matched_{param_idx}?.readLines() ?: ['null']",
                f"def raw_{param_idx} = lines_{param_idx}.get((int)(Math.random() * lines_{param_idx}.size()))",
                f'vars.put("param_{param_idx}", "null".equalsIgnoreCase(raw_{param_idx}) ? "" : raw_{param_idx})',
                "",
            ])
        else:
            lines.extend([
                f"// param_{param_idx}: (unresolved column, generic fallback)",
                f"def f_{param_idx} = new File(seedDir + '/param.csv')",
                f"def lines_{param_idx} = f_{param_idx}.exists() ? f_{param_idx}.readLines() : ['null']",
                f"def raw_{param_idx} = lines_{param_idx}.get((int)(Math.random() * lines_{param_idx}.size()))",
                f'vars.put("param_{param_idx}", "null".equalsIgnoreCase(raw_{param_idx}) ? "" : raw_{param_idx})',
                "",
            ])
        param_idx += 1

    return "\n".join(lines)


def _replace_placeholders_with_vars(sql: str) -> Tuple[str, int]:
    """Replace each ? in sql with ${param_N} and return (new_sql, count).

    Skips ? inside string literals.
    """
    result = []
    param_count = 0
    in_string = False
    string_char = None
    for ch in sql:
        if ch in ("'", '"'):
            if not in_string:
                in_string = True
                string_char = ch
            elif string_char == ch:
                in_string = False
                string_char = None
        if not in_string and ch == "?":
            result.append(f"${{param_{param_count}}}")
            param_count += 1
        else:
            result.append(ch)
    return "".join(result), param_count


def generate_query_thread_groups(
    query_config: List[QueryConfig],
    seed_dir: str = "${seed_dir}",
) -> List:
    """Generate query ThreadGroups for all query configuration entries.

    Each query ThreadGroup includes a JSR223PreProcessor that binds
    ``?`` placeholders by randomly sampling from column seed files.

    Parameters
    ----------
    query_config:
        All query configuration entries from ``TestConfig``.
    seed_dir:
        Path to the seeds directory (JMeter variable, default ``${seed_dir}``).

    Returns
    -------
    A flat list of elements forming all query ThreadGroups, each as:
    ``[ThreadGroup, hashTree, ConstantThroughputTimer, hashTree,
        JSR223PreProcessor, hashTree, JDBCSampler, hashTree]``.
    Returns an empty list when ``query_config`` is empty.
    """
    if not query_config:
        return []

    results: List = []

    for qc in query_config:
        # Parse SQL: replace each ? with ${param_N}
        query_with_vars, param_count = _replace_placeholders_with_vars(qc.query)
        query_var_refs = ",".join(f"${{param_{i}}}" for i in range(param_count))

        # Build JSR223PreProcessor script
        if param_count > 0:
            param_script = _build_query_param_script(qc.query, param_count, seed_dir)
        else:
            param_script = "// No placeholders in query"

        preprocessor, preproc_hash = jsr223_preprocessor_element(
            name=f"Query-param-{hash(qc.query) & 0x7FFFFFFF}",
            script=param_script,
            script_language="groovy",
            testname=f"[Query] param preprocessor",
        )

        sampler, samp_hash = jdbc_sampler_element(
            name="Query",
            query=query_with_vars,
            data_source="${db_url}",
            query_type="Prepared Select Statement",
            query_arguments=query_var_refs,
            testname=f"[Query]",
        )

        tg, tg_hash = thread_group_element(
            name=f"Query-{qc.query[:30]}",
            testname=f"[Query] {qc.query[:50]}",
            num_threads=qc.num_threads,
            ramp_time=1,
            duration="${test_duration}",
            loops="-1",
            scheduler=True,
        )

        timer, timer_hash = constant_throughput_timer_element(
            name="Constant Throughput Timer",
            throughput="${read_throughput}",
            calc_mode=0,
            testname="Constant Throughput Timer",
        )

        # Order: ThreadGroup → hashTree → Timer → hashTree → PreProcessor → hashTree → Sampler → hashTree
        results.extend([
            tg, tg_hash,
            timer, timer_hash,
            preprocessor, preproc_hash,
            sampler, samp_hash,
        ])

    return results
