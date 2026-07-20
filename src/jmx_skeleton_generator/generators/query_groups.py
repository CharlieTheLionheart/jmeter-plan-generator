"""Query ThreadGroup generators.

This module owns three logical concerns, kept in one file per the design
committee's "stay put, fix in place" decision (see
openspec/changes/query-functionality/design.md §1 and tasks §11.4):

1. **SQL state machine** (single source): ``_scan_sql_tokens`` tokenises
   the query template; helpers consume the token stream. Adding a new
   rule (e.g. an escape sequence) is a one-place change.
2. **Parameter binding**: ``generate_param_binding_script`` builds the
   JSR223PreProcessor Groovy body that samples column seeds.
3. **ThreadGroup assembly**: ``generate_query_thread_groups`` wraps
   (2) plus a ``JDBCSampler`` and a ``ConstantThroughputTimer`` into a
   JMeter thread group.

Open follow-up tracked in tasks §13: a future iteration may extract
(1) into ``src/query_functionality/sql_parser.py``. The function
boundaries here are designed to make that mechanical.
"""

from __future__ import annotations

import re
from collections import namedtuple
from typing import List, Optional, Tuple

from config_parser.models import QueryConfig
from jmx_skeleton_generator.generators._query_errors import QueryGenerationError
from throughput_control import generate_query_timer
from utils.xml_helpers import (
    jdbc_sampler_element,
    jsr223_preprocessor_element,
    thread_group_element,
)


# ---------------------------------------------------------------------------
# SQL state machine — single source of truth (design decision 16)
# ---------------------------------------------------------------------------

_SQLToken = namedtuple("_SQLToken", "kind start end text")

_KIND_PLACEHOLDER = "PLACEHOLDER"
_KIND_SQ_STRING = "SQ_STRING"
_KIND_DQ_STRING = "DQ_STRING"
_KIND_OTHER = "OTHER"

_STATE_NORMAL = "NORMAL"
_STATE_SQ_STRING = "SQ_STRING"
_STATE_DQ_STRING = "DQ_STRING"


def _scan_sql_tokens(sql: str) -> Tuple[List[_SQLToken], str]:
    """Tokenise an SQL template; raise ``QueryGenerationError`` on forbidden constructs.

    Recognised tokens:

    - ``PLACEHOLDER``: a single ``?``.
    - ``SQ_STRING``: a single-quoted string literal, including ``''`` escape.
    - ``DQ_STRING``: a double-quoted identifier, including ``""`` escape.
    - ``OTHER``: any other character (merged into one token per maximal run).

    Always rejects the SQL template with ``QueryGenerationError`` if it
    contains a ``--`` line comment or a ``/*`` block comment leader
    (design decision 11: SQL templates must not contain comments).

    Raises ``QueryGenerationError`` if the SQL ends inside an unclosed
    ``SQ_STRING`` or ``DQ_STRING`` (design decision 11: hard-fail on EOF).

    The state machine does **not** support:

    - Nested string literals (KaiwuDB / ANSI SQL do not allow them).
    - Nested block comments (PG / SQL standard forbid them).

    Returns the (tokens, final_state) pair; ``final_state`` is
    ``NORMAL`` on success.
    """
    tokens: List[_SQLToken] = []
    n = len(sql)
    i = 0
    final_state = _STATE_NORMAL
    other_start: Optional[int] = None
    other_chars: List[str] = []

    def _flush_other(end_pos: int) -> None:
        nonlocal other_start, other_chars
        if other_start is not None and other_chars:
            tokens.append(
                _SQLToken(_KIND_OTHER, other_start, end_pos, "".join(other_chars))
            )
        other_start = None
        other_chars = []

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if ch == "'":
            _flush_other(i)
            sq_start = i
            sq_buf = ["'"]
            i += 1
            closed = False
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        sq_buf.append("'")
                        sq_buf.append("'")
                        i += 2
                        continue
                    sq_buf.append("'")
                    i += 1
                    closed = True
                    break
                sq_buf.append(sql[i])
                i += 1
            tokens.append(
                _SQLToken(_KIND_SQ_STRING, sq_start, i, "".join(sq_buf))
            )
            if not closed:
                final_state = _STATE_SQ_STRING
                _flush_other(i)
                return tokens, final_state
            other_start = i
            continue

        if ch == '"':
            _flush_other(i)
            dq_start = i
            dq_buf = ['"']
            i += 1
            closed = False
            while i < n:
                if sql[i] == '"':
                    if i + 1 < n and sql[i + 1] == '"':
                        dq_buf.append('"')
                        dq_buf.append('"')
                        i += 2
                        continue
                    dq_buf.append('"')
                    i += 1
                    closed = True
                    break
                dq_buf.append(sql[i])
                i += 1
            tokens.append(
                _SQLToken(_KIND_DQ_STRING, dq_start, i, "".join(dq_buf))
            )
            if not closed:
                final_state = _STATE_DQ_STRING
                _flush_other(i)
                return tokens, final_state
            other_start = i
            continue

        if ch == "?":
            _flush_other(i)
            tokens.append(_SQLToken(_KIND_PLACEHOLDER, i, i + 1, "?"))
            i += 1
            other_start = i
            continue

        if ch == "-" and nxt == "-":
            raise QueryGenerationError(
                f"SQL template must not contain comments; -- at sql[{i}]: {sql[:60]}",
                sql=sql,
                position=i,
                kind="COMMENT_LINE",
            )

        if ch == "/" and nxt == "*":
            raise QueryGenerationError(
                f"SQL template must not contain comments; /* at sql[{i}]: {sql[:60]}",
                sql=sql,
                position=i,
                kind="COMMENT_BLOCK",
            )

        if other_start is None:
            other_start = i
        other_chars.append(ch)
        i += 1

    _flush_other(n)

    return tokens, final_state


def _extract_placeholders(sql: str) -> List[Tuple[int, int]]:
    """Return (start, end) positions of each ``?`` placeholder outside strings.

    Proxies :func:`_scan_sql_tokens` so the position list stays in sync
    with whatever the rewriter produces (design decision 16).
    Raises ``QueryGenerationError`` when the SQL ends inside an
    unterminated string (design decision 11).
    """
    tokens, final_state = _scan_sql_tokens(sql)
    if final_state != _STATE_NORMAL:
        raise QueryGenerationError(
            f"unterminated {final_state} at end of SQL: {sql[:60]}",
            sql=sql,
            position=len(sql),
            kind=f"UNTERMINATED_{final_state}",
        )
    return [(t.start, t.end) for t in tokens if t.kind == _KIND_PLACEHOLDER]


def _replace_placeholders_with_vars(sql: str) -> Tuple[str, int]:
    """Rewrite each ``?`` to ``${param_N}``; skip placeholders inside string literals.

    Returns the rewritten SQL and the placeholder count. Built on the
    same token stream as :func:`_extract_placeholders`; the two cannot
    drift (design decision 16).
    Raises ``QueryGenerationError`` when the SQL ends inside an
    unterminated string.
    """
    tokens, final_state = _scan_sql_tokens(sql)
    if final_state != _STATE_NORMAL:
        raise QueryGenerationError(
            f"unterminated {final_state} at end of SQL: {sql[:60]}",
            sql=sql,
            position=len(sql),
            kind=f"UNTERMINATED_{final_state}",
        )
    result: List[str] = []
    param_count = 0
    for tok in tokens:
        if tok.kind == _KIND_PLACEHOLDER:
            result.append(f"${{param_{param_count}}}")
            param_count += 1
        else:
            result.append(tok.text)
    return "".join(result), param_count


# ---------------------------------------------------------------------------
# Column binding + table path
# ---------------------------------------------------------------------------


def _extract_table_path(sql: str) -> Optional[str]:
    """Extract ``db.table`` from the FROM clause of a SQL query.

    Scans FROM clauses for patterns like ``db.table`` or ``table``.
    Returns the first match (single-table query assumption).
    Returns ``None`` if no table path could be resolved.
    """
    patterns = [
        r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b",
        r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, sql, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    return None


# Supported operators on placeholder column-context (design decision 2
# removed IN; explicit list to prevent drift).
_SUPPORTED_OPERATORS = (
    r"=|<>|!=|<=|<|>|>=|LIKE"
)
_COLUMN_BIND_RE = re.compile(
    r"([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\s*(?:"
    + _SUPPORTED_OPERATORS
    + r")\s*$",
    re.IGNORECASE,
)
_IS_NULL_RE = re.compile(r"\bIS(?:\s+NOT)?(?:\s+NULL)?\s*$", re.IGNORECASE)
_BETWEEN_AND_RE = re.compile(r"\bBETWEEN\b[^?]*\bAND\s*$", re.IGNORECASE)
_IN_SINGLE_RE = re.compile(
    r"([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\s+IN\s*\(\s*$",
    re.IGNORECASE,
)


def _extract_column_context(sql: str, pos: int) -> Optional[str]:
    """Return the column name just before the placeholder at ``pos``.

    Returns the bare column (``t.col`` → ``col``). Returns ``None``
    when the placeholder cannot be bound to a column; callers then
    raise ``QueryGenerationError`` (design decision 7).
    """
    prefix = sql[:pos].rstrip()
    match = _COLUMN_BIND_RE.search(prefix)
    if not match:
        return None
    col_ref = match.group(1)
    return col_ref.split(".")[-1] if "." in col_ref else col_ref


def _is_in_unsupported_clause(sql: str, pos: int) -> Optional[str]:
    """Return a reason string when the placeholder at ``pos`` sits in an
    unbindable clause (``LIMIT`` / ``IS NULL`` / ``BETWEEN ... AND``).

    Returns ``None`` when the placeholder sits in a column-bindable
    context (operator matched, IN handled separately).
    """
    prefix = sql[:pos].rstrip()
    if _IS_NULL_RE.search(prefix):
        return "IS NULL / IS NOT NULL placeholder is not bindable"
    if _BETWEEN_AND_RE.search(prefix):
        return "BETWEEN ... AND ? placeholder is not bindable"
    upper = prefix.upper()
    if upper.endswith("LIMIT"):
        return "LIMIT ? placeholder is not bindable"
    return None


def _in_clause_placeholder_count(sql: str, pos: int) -> int:
    """Count placeholders in the same ``IN (...)`` clause before ``pos``.

    Returns -1 if ``pos`` is not inside any ``IN (...)`` clause (caller
    treats the placeholder as a normal one). Returns 0 for the first
    placeholder inside ``IN (...)`` (allowed, behaves like ``=``).
    Returns >= 1 for the second-or-later placeholder (rejected;
    design decision 13).

    Walks the SQL between the last ``IN (`` opener before ``pos`` and
    ``pos`` itself, tracking string-literal state and parenthesis depth
    so it tolerates ``?`` and ``(...)`` inside strings.
    """
    in_open: Optional[int] = None
    for m in re.finditer(r"\bIN\s*\(", sql[:pos], re.IGNORECASE):
        in_open = m.end()  # position right after "("
    if in_open is None:
        return -1

    in_string = False
    string_char: Optional[str] = None
    depth = 1
    count = 0
    k = in_open
    while k < pos:
        ch = sql[k]
        if in_string:
            if ch == string_char:
                if k + 1 < pos and sql[k + 1] == string_char:
                    k += 2
                    continue
                in_string = False
                string_char = None
            k += 1
            continue
        if ch in ("'", '"'):
            in_string = True
            string_char = ch
        elif ch == "?":
            count += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return -1
        k += 1
    return count


# ---------------------------------------------------------------------------
# Groovy parameter-binding script
# ---------------------------------------------------------------------------


def generate_param_binding_script(
    sql: str,
    *,
    seed_dir: str = "${seed_dir}",
) -> str:
    """Build the Groovy JSR223PreProcessor script for a SQL query.

    Walks the SQL token stream (single source of truth), rejects per
    design decisions 7 / 11 / 13, and emits Groovy that samples the
    appropriate column seed file (or the ``"null"`` fallback). Seed
    file resolution follows design decision 17 (uniqueness hard-fail).

    Called by :func:`generate_query_thread_groups`; not directly by
    tests. The "rename from ``_build_query_param_script``" entry on
    tasks §4.7 is satisfied — there are no external callers of the
    old name.
    """
    tokens, _ = _scan_sql_tokens(sql)
    placeholders = [t for t in tokens if t.kind == _KIND_PLACEHOLDER]
    if not placeholders:
        return "// No placeholders in query"

    table_path = _extract_table_path(sql)
    if not table_path:
        raise QueryGenerationError(
            f"cannot resolve table path from SQL: {sql[:60]}",
            sql=sql,
            kind="UNRESOLVED_TABLE_PATH",
        )

    lines: List[str] = [
        "// JSR223PreProcessor (groovy): 查询参数绑定",
        f"// Table: {table_path}",
        f"def seedDir = vars.get('seed_dir') ?: 'seeds'",
        # ``table_path`` is the SQL-qualified ``db.table`` form, but the
        # seed-data-generator emits per-table CSVs under
        # ``seeds/<db>/<table>/`` (nested). Convert ``db.table`` →
        # ``db/table`` so the file lookup actually finds the seed dir.
        f"def tableDir = new File(seedDir + '/{table_path.replace('.', '/')}')",
        "",
    ]

    for param_idx, tok in enumerate(placeholders):
        # Order matters: reject IN multi-placeholder before column lookup,
        # otherwise an IN(?, ?) placeholder at position N+1 raises
        # UNRESOLVED_COLUMN (no binary operator follows it) instead of the
        # intended IN_MULTI_PLACEHOLDER.
        prior_in_count = _in_clause_placeholder_count(sql, tok.start)
        if prior_in_count >= 1:
            raise QueryGenerationError(
                f"placeholders in IN clauses are not supported (>= 2 placeholders); "
                f"see sql[{tok.start}]: {sql[:60]}",
                sql=sql,
                position=tok.start,
                kind="IN_MULTI_PLACEHOLDER",
            )

        bad = _is_in_unsupported_clause(sql, tok.start)
        if bad:
            raise QueryGenerationError(
                f"cannot bind placeholder at sql[{tok.start}]: {bad} ({sql[:60]})",
                sql=sql,
                position=tok.start,
                kind="UNSUPPORTED_OPERATOR",
            )

        col_name = _extract_column_context(sql, tok.start)
        if col_name is None and prior_in_count == 0:
            # IN-context fallback: ``col IN (?`` — column is the token
            # immediately preceding ``IN (``.
            m = _IN_SINGLE_RE.search(sql[: tok.start])
            if m:
                col_name = m.group(1).split(".")[-1]
        if col_name is None:
            raise QueryGenerationError(
                f"cannot bind placeholder at sql[{tok.start}]; "
                f"no column context resolvable in: {sql[:60]}",
                sql=sql,
                position=tok.start,
                kind="UNRESOLVED_COLUMN",
            )

        suffix = col_name.replace("'", "\\'")
        # Fallback value when no per-column seed file exists: a
        # device-id-shaped string derived from the test-plan UDV
        # ``device_start``. The most common case is the first ptag
        # (``ptag_varchar_1``), whose seed is virtualised at write
        # time and never written to disk. Without this fallback the
        # query's ``WHERE ptag_varchar_1 = ?`` is bound to an empty
        # string, producing ``at or near "EOF": syntax error``
        # (regression on 2026-07-20, F-4). The previous ``['null']``
        # fallback left ``param_N`` empty, silently corrupting the
        # query.
        lines.extend([
            f"// param_{param_idx}: {col_name}",
            f"def matched_{param_idx} = tableDir.listFiles()?.find {{ it.name.endsWith('_{suffix}.csv') }}",
            f"if (matched_{param_idx} != null) {{",
            f"    def allMatches_{param_idx} = tableDir.listFiles().findAll {{ it.name.endsWith('_{suffix}.csv') }}",
            f"    if (allMatches_{param_idx}.size() > 1) {{",
            f"        log.error('ambiguous seed files for column {col_name}: ' + allMatches_{param_idx})",
            f"        throw new RuntimeException('ambiguous seed files for column {col_name}')",
            f"    }}",
            f"}}",
            # The fallback list contains one synthetic value. The
            # device-id pattern is a safe default for ptag-like
            # columns; for non-ptag columns (e.g. rtag, data_cols)
            # the seed file is always present, so the fallback
            # path is never exercised in practice.
            f"def lines_{param_idx} = matched_{param_idx}?.readLines() ?: ['device_' + (vars.get('device_start') ?: '1')]",
            f"def raw_{param_idx} = lines_{param_idx}.get((int)(Math.random() * lines_{param_idx}.size()))",
            f'vars.put("param_{param_idx}", raw_{param_idx})',
            "",
        ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ThreadGroup assembly
# ---------------------------------------------------------------------------


def generate_query_thread_groups(
    query_config: List[QueryConfig],
    seed_dir: str = "${seed_dir}",
) -> List:
    """Generate query ThreadGroups for all query configuration entries.

    Each query ThreadGroup includes a JSR223PreProcessor that binds
    ``?`` placeholders by randomly sampling from column seed files.
    The ``ConstantThroughputTimer`` for each thread group embeds the
    per-query ``QueryConfig.throughput`` literal (no JMeter UDV).

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
        query_with_vars, param_count = _replace_placeholders_with_vars(qc.query)
        query_var_refs = ",".join(f"${{param_{i}}}" for i in range(param_count))

        if param_count > 0:
            param_script = generate_param_binding_script(qc.query, seed_dir=seed_dir)
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
            data_source="jdbcConfig",
            query_type="Prepared Select Statement",
            query_arguments=query_var_refs,
            # F-6 (2026-07-20): JMeter's JDBCSampler validates that
            # ``queryArguments`` and ``queryArgumentsTypes`` have the
            # same number of entries. The previous empty ``""`` made
            # the driver count it as 1 type while we passed 2-4 args
            # → ``number of arguments (N) and number of types (1) are
            # not equal``. Default every param to ``VARCHAR`` — the
            # KaiwuDB driver coerces numeric literals like ``'1'`` to
            # int8 on the wire, and string literals stay strings.
            query_arguments_types=",".join(["VARCHAR"] * param_count) if param_count > 0 else "",
            testname=f"[Query]",
        )

        timer, timer_hash = generate_query_timer(qc.throughput)

        # Rebuild ThreadGroup with children embedded in its paired
        # hashTree — JMeter treats timer/preprocessor/sampler as group
        # members instead of TestPlan siblings (the legacy flat-list
        # shape left them at TestPlan level, which made JMeter silently
        # skip the thread group's samplers).
        inner_children = [
            timer, timer_hash,
            preprocessor, preproc_hash,
            sampler, samp_hash,
        ]
        tg, tg_hash = thread_group_element(
            name=f"Query-{qc.query[:30]}",
            testname=f"[Query] {qc.query[:50]}",
            num_threads=qc.num_threads,
            ramp_time=1,
            duration="${test_duration}",
            loops="-1",
            scheduler=True,
            children=inner_children,
        )
        results.extend([tg, tg_hash])

    return results
