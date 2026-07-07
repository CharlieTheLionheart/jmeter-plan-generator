"""SharedMemory SetupThreadGroup generator.

Loads row seed data from CSV files into JMeter shared memory (props) by
embedding JSR223PreProcessor elements inside a single-threaded SetupThreadGroup.

Design: openspec/changes/shared-memory-initializer/design.md
Spec:    openspec/changes/shared-memory-initializer/specs/shared-memory-initialization/spec.md
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from shared_memory_initializer import SharedMemoryInitializerGenerator
from utils.xml_helpers import (
    empty_hash_tree,
    hash_tree,
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
        duration="1",
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
