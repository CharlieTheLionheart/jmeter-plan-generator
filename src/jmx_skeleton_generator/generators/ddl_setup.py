"""DDL SetupThreadGroup generator."""

from __future__ import annotations

from typing import List, Optional, Tuple

from utils.xml_helpers import (
    empty_hash_tree,
    hash_tree,
    jdbc_sampler_element,
    setup_thread_group_element,
)


def generate_ddl_setup_thread_group(
    ddl_statements: List[str],
    *,
    name: str = "DDL Setup",
    num_threads: int = 1,
) -> List:
    """Build a SetupThreadGroup that runs all DDL statements.

    Parameters
    ----------
    ddl_statements:
        DDL SQL strings (CREATE DATABASE, CREATE TABLE, etc.).
        Each gets its own JDBCSampler.
    name:
        Display name for the setup thread group.
    num_threads:
        Number of threads (default 1).

    Returns
    -------
    A 2-element list ``[SetupThreadGroup, hashTree]`` whose hashTree
    contains all DDL JDBCSampler + their paired hashTrees. Returns an
    empty list when ``ddl_statements`` is empty.
    """
    if not ddl_statements:
        return []

    # Build children into the setup-thread-group's paired hashTree via
    # the new ``children=`` argument. Each DDL becomes one JDBCSampler
    # paired with its empty hashTree, so JMeter treats the sampler as
    # belonging to the setup thread group instead of as a TestPlan-level
    # sibling (the legacy ``[stg, hash_tree, *samplers]`` flat-list
    # shape emitted them both inside AND outside the group, which made
    # JMeter silently skip them).
    children: List = []
    for i, ddl in enumerate(ddl_statements):
        sampler, samp_hash = jdbc_sampler_element(
            name=f"DDL-{i + 1}",
            query=ddl,
            data_source="jdbcConfig",
            query_type="Update Statement",
            testname=f"DDL-{i + 1}",
        )
        children.extend([sampler, samp_hash])

    stg, stg_hash = setup_thread_group_element(
        name=name,
        testname=name,
        num_threads=num_threads,
        ramp_time=1,
        duration="1",
        delay=0,
        loops=1,
        scheduler=True,
        children=children,
    )
    return [stg, stg_hash]  # placeholder; replaced below
