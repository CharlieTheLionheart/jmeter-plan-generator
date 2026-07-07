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
    A flat list of elements forming the SetupThreadGroup and all its
    children: ``[SetupThreadGroup, hashTree, JDBCSampler, hashTree, ...]``.
    Returns an empty list when ``ddl_statements`` is empty.
    """
    if not ddl_statements:
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

    # Build the content of stg_hash (children of the SetupThreadGroup)
    stg_children: List = []
    for i, ddl in enumerate(ddl_statements):
        sampler, samp_hash = jdbc_sampler_element(
            name=f"DDL-{i + 1}",
            query=ddl,
            data_source="${db_url}",
            query_type="Update Statement",
            testname=f"DDL-{i + 1}",
        )
        stg_children.extend([sampler, samp_hash])

    # Replace the empty stg_hash with one containing the samplers
    stg_hash = hash_tree(*stg_children)

    # Flat list per docstring: hashTree 保留 XML 嵌套结构,sampler 同步平铺到顶层,
    # 使调用方可以单层遍历同时定位 SetupThreadGroup 和 JDBCSampler
    elements: List = [stg, stg_hash, *stg_children]
    return elements
