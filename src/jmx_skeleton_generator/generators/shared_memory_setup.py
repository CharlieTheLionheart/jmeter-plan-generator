"""SharedMemory SetupThreadGroup generator.

Loads row seed data from CSV files into JMeter shared memory (props) by
embedding JSR223PreProcessor elements inside a single-threaded SetupThreadGroup.

Design: openspec/changes/shared-memory-initializer/design.md
Spec:    openspec/changes/shared-memory-initializer/specs/shared-memory-initialization/spec.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config_parser.models import WriteConfig
from shared_memory_initializer import SharedMemoryInitializerGenerator
from utils.preprocessor_helpers import all_groovy_decls
from utils.xml_helpers import (
    empty_hash_tree,
    hash_tree,
    jsr223_sampler_element,
    setup_thread_group_element,
)


def generate_shared_memory_setup_thread_group(
    seed_csv_paths: Dict[str, Dict[str, str]],
    *,
    name: str = "SharedMemory Setup",
    num_threads: int = 1,
) -> List:
    """Build a SetupThreadGroup that loads CSV seed files into JMeter props.

    Parameters
    ----------
    seed_csv_paths:
        Mapping of ``db_name → {table_name → csv_file_path}``.
        Example: ``{"tsdb": {"t_table": "/path/to/seeds/tsdb/t_table.csv"}}``
    name:
        Display name for the setup thread group.
    num_threads:
        Number of threads (default 1; loading should be single-threaded).

    Returns
    -------
    A flat list of elements forming the SetupThreadGroup and all its
    children: ``[SetupThreadGroup, hashTree, JSR223PreProcessor, hashTree, ...]``.
    Returns an empty list when ``seed_csv_paths`` is empty.

    Notes
    -----
    Each table gets its own JSR223PreProcessor that runs in the shared
    SetupThreadGroup. The Groovy script inside each PreProcessor reads the
    corresponding CSV file and stores:

    - ``__SHARED_MEM_{db}.{table}``   → List[List[Any]] (row-first data)
    - ``__SHARED_MEM_{db}.{table}_columns`` → List[String] (column names)
    """
    if not seed_csv_paths:
        return []

    stg, stg_hash = setup_thread_group_element(
        name=name,
        testname=name,
        num_threads=num_threads,
        ramp_time=1,
        # F-5 (2026-07-20): ``duration=1`` (1 second) was the cause of
        # the flaky ``null sharedRows.size()`` NPE in the Write
        # ThreadGroup. With 5+ tables the SetupThreadGroup's single
        # loop iteration did not finish loading every CSV before the
        # scheduler cut the thread, so the Write PreProcessor's
        # ``__SHARED_MEM_{db}_{table}`` lookup returned null. 60s is
        # comfortably above the worst-case loader time and short
        # enough to keep the smoke under a minute. ``loops=1`` keeps
        # the loaders single-shot (no duplicate writes to props).
        duration="60",
        delay=0,
        loops=1,
        scheduler=True,
    )

    generator = SharedMemoryInitializerGenerator()
    stg_children: List = []

    for db_name, tables in seed_csv_paths.items():
        for table_name, csv_path in tables.items():
            preprocessor, preproc_hash = generator.generate_for_table(
                db=db_name,
                table=table_name,
                csv_path=csv_path,
                testname=f"SharedMemoryLoader {db_name}.{table_name}",
            )
            stg_children.extend([preprocessor, preproc_hash])

    stg_hash = hash_tree(*stg_children)

    elements: List = [stg, stg_hash]
    return elements


# ---------------------------------------------------------------------------
# col-tag-bind-write (2026-08-05): Bind-mode SetupTG
# ---------------------------------------------------------------------------


def _build_bind_sampler_groovy(
    *,
    db: str,
    table: str,
    col_num_per_tag: int,
    seed_root: str,
    num_threads: int,
    device_per_thread: int = 1,
    ptag_names: Optional[List[str]] = None,
    # D-25 (2026-08-14): bake batch_lines rows per deviceCode so the
    # Write TG prep (D-24) can pick a different row per InfluxDB Line
    # within one batch_lines prep call (avoids duplicate-value reject).
    batch_lines: int = 1,
) -> str:
    """Render the JSR223 Sampler Groovy script that loads column seeds for
    a single col_tag_bind table and writes hash-grouped row memory.

    Runtime layout:

    - Reads column seed CSVs from ``{seed_root}/{db}/{table}/{idx}_{name}.csv``.
    - Builds ``ptag_tuple = [deviceCode, *other_ptags]`` per loop iteration,
      where ``deviceCode`` mirrors the Write TG's
      ``deviceIdentifier(calculateDeviceNumber(threadNum, start, dpt, 0))``
      so both sides land in the same ``group_id = hash(ptag_tuple) mod
      num_threads`` bucket.
    - The loop upper bound is ``num_threads`` (NOT ``seed_num``): the Write
      TG produces exactly ``num_threads`` distinct device codes per thread
      pass (``row_index=0`` constant), so the SetupTG only needs to seed
      that many — extra seed rows would orphan groups, fewer would let
      some threads hit ``SELECT 1`` fallback (commit 4 fix).
    - Each group stores ``{col_names: [...first col_num_per_tag data cols...],
      row_values: [[...one row per group...], ...]}``.
    - Writes the map to ``__SHARED_MEM_{db}_{table}_bind`` on the JMeter
      props singleton; the Write TG's Groovy PreProcessor consumes this
      namespace to assemble column-subset INSERTs.

    Notes:
    - ``col_num_per_tag`` / ``num_threads`` / ``device_per_thread`` /
      ``ptag_names`` are bound at generation time.
    - ``ptag_names`` is the full primary-tag list (including the first ptag);
      the first element is overwritten at runtime by ``deviceCode``, the
      rest are appended as ``'null'`` placeholders so the hash input
      matches the Write TG's ``ptagValues`` list exactly.
    - ``device_start`` is read at JMeter runtime from the ``${device_start}``
      UDV; defaults to ``1`` (matches ``ConnConfig.device_start`` default).
    """
    safe_db = db.replace("\\", "\\\\").replace("'", "\\'")
    safe_table = table.replace("\\", "\\\\").replace("'", "\\'")
    safe_seed_root = str(seed_root).replace("\\", "\\\\").replace("'", "\\'")
    rows_key = f"__SHARED_MEM_{db}_{table}_bind"
    # Groovy list literal of ptag names (used by the SetupTG script to
    # mirror the Write TG's ``ptagValues`` so ``hash(ptag_tuple)`` lines
    # up. ``device_id`` is the convention for bind-mode fixtures; pass
    # ``ptag_names=[...]`` to override when a table uses a different
    # first-ptag column name.
    ptag_names_groovy = "[" + ", ".join(f"'{n}'" for n in (ptag_names or ["device_id"])) + "]"

    return f"""\
{all_groovy_decls()}

// JSR223Sampler (groovy): col-tag-bind-write Bind-mode SetupTG loader.
// Reads column seeds for {safe_db}.{safe_table} and writes hash-grouped
// row memory to {rows_key}.
def dbName = '{safe_db}'
def tableName = '{safe_table}'
def seedRoot = '{safe_seed_root}'
def colNumPerTag = {col_num_per_tag}
def numThreads = {num_threads}
def devicePerThread = {device_per_thread}
def rowsKey = '{rows_key}'

// 1. Read column seed CSVs into a map of column-name -> list of values.
def tableDir = new File(seedRoot, dbName + File.separator + tableName)
if (!tableDir.isDirectory()) {{
    log.error("BindSetup: missing seed dir " + tableDir)
    return
}}
def colFiles = tableDir.listFiles() as List
log.info("BindSetup: " + rowsKey + " tableDir=" + tableDir + " fileCount=" + (colFiles == null ? "null" : colFiles.size()))
def colValues = [:]
(colFiles ?: []).findAll {{ f -> f.name.endsWith(".csv") }}.each {{ f ->
    def m = f.name =~ /(\d+)_(.+)\.csv/
    if (m.find()) {{
        def colName = m.group(2)
        colValues[colName] = f.readLines().collect {{ it.replaceAll('"', '') }}
    }}
}}
if (colValues.isEmpty()) {{
    log.warn("BindSetup: empty column seeds for " + rowsKey + " (fileCount=" + (colFiles == null ? "null" : colFiles.size()) + ")")
    return
}}

// 2. Determine seed_num (max rows across all columns) and data columns.
//    D-18 (2026-08-13): colNamesSubset is computed per-group below
//    (each hash group writes a DIFFERENT column subset, not all sharing
//    the first N columns). Earlier commit-3 "all groups share first N"
//    was a simplification (see col-tag-bind-per-group-subsets DCR).
def seedNum = colValues.values()*.size().max() ?: 0
def dataColumns = colValues.keySet().toList().sort()

// 3. Hash ptag_tuple -> group_id, build per-group row memory.
//    Loop bound is ``numThreads`` (NOT ``seedNum``): the Write TG produces
//    exactly ``numThreads`` distinct device codes per thread pass
//    (``calculateDeviceNumber(threadNum, ...)`` with ``row_index=0``),
//    so the SetupTG only seeds that many. Mirroring the Write TG's
//    ``ptagValues = [deviceCode, *other_ptags]`` keeps the hash input
//    identical between Setup and Write (commit 4 fix).
//    D-13 (2026-08-12): also bake ptag_values per row so the Write TG
//    bind-mode PreProcessor can write all ptag columns into the
//    InfluxDB Line tag_set (per ref §5.5 — tag_set must keep all ptag).
//    D-18 (2026-08-13): each group_id picks a different starting offset
//    into dataColumns so that groups write complementary (non-overlapping)
//    column subsets. ``colStart = (deviceIndex - 1) * colNumPerTag``
//    modulo size handles wrap-around when ``colNumPerTag * numThreads <
//    dataColumns.size()``.
def deviceStart = (vars.get('device_start') != null ?
    (vars.get('device_start') as Integer) : 1)
def otherPtagNames = ({ptag_names_groovy}) - ['device_id']
def ptagNamesOrdered = ({ptag_names_groovy})
def groups = [:]
for (int t = 0; t < numThreads; t++) {{
    long deviceNumber = calculateDeviceNumber(
        t as long, deviceStart as long, devicePerThread as long, 0)
    def deviceCode = deviceIdentifier(deviceNumber)
    // D-21 (2026-08-14): per-deviceCode key in SharedMemory. No
    // List/Object hash call anywhere — Groovy default Object.hash on
    // a List of short strings is degenerate for short numeric-suffixed
    // values (measured: device_1/device_3 both land in same group).
    // Use deviceCode as the literal key so each device's subset is
    // independent of any hash distribution.
    // col_names offset: use the SetupTG loop index ``t`` directly
    // (monotonically 0..numThreads-1 across iterations) rather than
    // parsing the deviceCode suffix — the suffix parse fails for
    // device_per_thread > 1 (thread 1 = device_3, not device_2, so
    // (deviceIndex-1)*colNumPerTag wrap-arounds back to 0).
    int colStart = (t * colNumPerTag) % dataColumns.size()
    def colNamesSubset = (1..colNumPerTag).collect {{ idx ->
        dataColumns[(colStart + idx - 1) % dataColumns.size()]
    }}
    def rowVals = colNamesSubset.collect {{ colName ->
        def vals = colValues[colName]
        vals ? vals[t % vals.size()] : "null"
    }}
    def ptagVals = ptagNamesOrdered.collect {{ ptagName ->
        // D-14 (2026-08-13): first ptag is deviceCode (injected at runtime).
        def isFirst = (ptagName == ptagNamesOrdered[0])
        if (isFirst) return deviceCode
        def vals = colValues[ptagName]
        vals ? vals[t % vals.size()] : "null"
    }}
    // D-25 (2026-08-14): bake batchLines rows per deviceCode so the Write
    // TG prep (D-24) can pick a different row per InfluxDB Line within
    // one batch_lines prep call. Each row is a fresh sample of the
    // seed pool using a stable hash(deviceCode + b) → reproducible and
    // avoids the duplicate-key / duplicate-value reject server-side.
    int batchLines = {batch_lines}
    def allRowVals = []
    def allPtagVals = []
    for (int b = 0; b < batchLines; b++) {{
        def rv = colNamesSubset.collect {{ colName ->
            def v = colValues[colName]
            // Use a deterministic per-(deviceCode, batchLine) sample index.
            // Hash deviceCode + b to spread across the pool without RNG
            // (keeps the baked script deterministic).
            int idx = Math.abs((deviceCode.hashCode() + b + colName.hashCode()) as int) % (v ? v.size() : 1)
            v ? v[idx] : "null"
        }}
        def pv = ptagNamesOrdered.collect {{ ptagName ->
            def isFirst = (ptagName == ptagNamesOrdered[0])
            if (isFirst) return deviceCode
            def v = colValues[ptagName]
            int idx = Math.abs((deviceCode.hashCode() + b + ptagName.hashCode()) as int) % (v ? v.size() : 1)
            v ? v[idx] : "null"
        }}
        allRowVals.add(rv)
        allPtagVals.add(pv)
    }}
    // D-21: key is deviceCode (String), not group_id (int). Each device
    // gets exactly one row dict entry — no aggregation, no hash collision.
    groups[deviceCode] = [col_names: colNamesSubset, row_values: allRowVals, ptag_values: allPtagVals, ptag_names: ptagNamesOrdered]
}}

// 4. Persist to JMeter props singleton (Write TG reads this namespace).
org.apache.jmeter.util.JMeterUtils.getJMeterProperties().put(rowsKey, groups)
log.info("BindSetup: " + rowsKey + " groups=" + groups.size() + " seedNum=" + seedNum)
"""


def generate_bind_setup_thread_group(
    write_configs: List[WriteConfig],
    seed_root: Path | str,
    *,
    num_threads: int = 1,
    name: str = "Bind Setup",
    ptag_names_by_table: Optional[Dict[str, List[str]]] = None,
) -> List:
    """Build a SetupThreadGroup that wires col_tag_bind tables into JMeter props.

    col-tag-bind-write (2026-08-05): for every ``WriteConfig`` with
    ``col_tag_bind_mode=True``, this emits one JSR223 Sampler that loads
    column seeds from ``{seed_root}/{db}/{table}/*.csv`` and writes a
    hash-grouped row-memory map to ``__SHARED_MEM_{db}_{table}_bind``.
    Mixed test plans (some tables bind, some full-row) emit this SetupTG
    alongside the existing SharedMemory SetupTG (each writes to its own
    ``__SHARED_MEM_*`` namespace).

    Parameters
    ----------
    write_configs:
        All ``WriteConfig`` entries; only those with
        ``col_tag_bind_mode=True`` contribute a sampler.
    seed_root:
        Directory that contains per-table column-seed subdirectories,
        typically the orchestrator's ``output_dir / "seeds"`` root.
    num_threads:
        Number of write threads; passed into the Groovy script as the
        hash modulo base. Defaults to 1.
    name:
        Display name for the SetupThreadGroup.

    Returns
    -------
    A flat list of elements forming the SetupThreadGroup + per-table
    sampler + hashTree pairs. Returns an empty list when no write_config
    has ``col_tag_bind_mode=True`` (callers can skip the bind branch
    entirely without an empty SetupTG).
    """
    bind_cfgs = [wc for wc in write_configs if wc.col_tag_bind_mode]
    if not bind_cfgs:
        return []

    stg, _stg_hash_inner = setup_thread_group_element(
        name=name,
        testname=name,
        num_threads=1,
        ramp_time=1,
        duration="60",
        delay=0,
        loops=1,
        scheduler=True,
    )

    children: List = []
    for wc in bind_cfgs:
        # ``partition(".")`` returns ``(before, separator, after)``; for
        # ``"iot_monitor.t_cnc"`` → ``("iot_monitor", ".", "t_cnc")``.
        db, _sep, table = wc.tbl_name.partition(".")
        ptag_names = (ptag_names_by_table or {}).get(wc.tbl_name)
        script = _build_bind_sampler_groovy(
            db=db,
            table=table,
            col_num_per_tag=wc.col_num_per_tag,
            seed_root=seed_root,
            num_threads=num_threads,
            device_per_thread=wc.device_per_thread,
            ptag_names=ptag_names,
            batch_lines=int(wc.batch_lines) if wc.batch_lines else 1,
        )
        sampler, sampler_hash = jsr223_sampler_element(
            name=f"BindSetup_{db}_{table}",
            script=script,
            script_language="groovy",
            cache_key="true",
            testname=f"BindSetup {db}.{table}",
        )
        children.extend([sampler, sampler_hash])

    stg_hash = hash_tree(*children)
    return [stg, stg_hash]
