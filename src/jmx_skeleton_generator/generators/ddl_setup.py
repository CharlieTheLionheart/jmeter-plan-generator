"""DDL SetupThreadGroup generator."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.xml_helpers import (
    bool_prop,
    element_prop,
    empty_hash_tree,
    hash_tree,
    jdbc_sampler_element,
    jsr223_preprocessor_element,
    make_element,
    setup_thread_group_element,
    string_prop,
)


# Default batch size for relational-table initialisation. Spec §3.6
# mandates ``total_rows % batch_lines == 0``; using a value that
# cleanly divides the largest common seed_num keeps the no-tail-batch
# invariant trivial (1 residue row causes a hard error).
_DEFAULT_REL_BATCH_LINES = 100


def generate_ddl_setup_thread_group(
    ddl_statements: List[str],
    *,
    name: str = "DDL Setup",
    num_threads: int = 1,
    rel_init_specs: Optional[Sequence[Dict[str, Any]]] = None,
) -> List:
    """Build a SetupThreadGroup that runs all DDL statements plus
    relational-table initialisation samplers.

    Parameters
    ----------
    ddl_statements:
        DDL SQL strings (CREATE DATABASE, CREATE TABLE, etc.).
        Each gets its own JDBCSampler.
    name:
        Display name for the setup thread group.
    num_threads:
        Number of threads (default 1).
    rel_init_specs:
        Optional iterable of spec dicts (one per relational table).
        Each dict must contain:

        - ``table_name`` (str, qualified ``db.table``)
        - ``columns`` (list[str], in DDL order)
        - ``total_rows`` (int, must be a positive multiple of
          ``batch_lines``)
        - ``batch_lines`` (int, default ``_DEFAULT_REL_BATCH_LINES``)
        - ``rel_col_seed_files`` (list[str], one entry per ``columns``)
        - ``column_types`` (list[str], aligned with ``columns``; defaults
          to all VARCHAR when omitted)

        When present, each spec produces a ``LoopController`` containing a
        :class:`JSR223PreProcessor` for batch parameter assembly and a
        ``Prepared Update Statement`` JDBCSampler, all placed in the
        SetupThreadGroup's paired hashTree right after the DDL samplers.

    Returns
    -------
    A 2-element list ``[SetupThreadGroup, hashTree]`` whose hashTree
    contains all DDL JDBCSampler + their paired hashTrees. Returns an
    empty list when neither DDL nor relational initialisation are
    requested.
    """
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
    for spec in rel_init_specs or []:
        children.extend(_build_rel_init_subtree(spec))

    if not children:
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
        children=children,
    )
    return [stg, stg_hash]


def _build_rel_init_subtree(spec: Dict[str, Any]) -> List:
    """Build the LoopController subtree (with sampler + preprocessor) for one
    relational-table initialisation spec.

    The returned flat list contains:

    - The ``<LoopController>`` element
    - Its paired ``<hashTree>`` containing the JDBCSampler + PreProcessor
      (each with their own paired hashTree)
    - The closing ``<hashTree>`` that pairs with the JDBCSampler
    """
    from direct_insert_write.sampler_generator import (
        DirectInsertGenerationError,
        generate_relational_table_init_sampler,
    )

    table_name = spec["table_name"]
    columns: List[str] = list(spec["columns"])
    total_rows: int = int(spec["total_rows"])
    batch_lines: int = int(spec.get("batch_lines") or _DEFAULT_REL_BATCH_LINES)
    rel_col_seed_files: List[str] = list(spec["rel_col_seed_files"])
    column_types: Optional[List[str]] = spec.get("column_types")

    cfg = generate_relational_table_init_sampler(
        table_name=table_name,
        columns=columns,
        total_rows=total_rows,
        batch_lines=batch_lines,
        rel_col_seed_files=rel_col_seed_files,
        column_types=column_types,
    )

    loop_count = int(cfg["loop_count"])
    pre_script = cfg["preprocessor_script"]
    sampler_name = cfg["name"]

    # LoopController element wrapping ``main_controller`` semantics.
    loop_props = [
        bool_prop("LoopController.continue_forever", "false"),
        string_prop("LoopController.loops", str(loop_count)),
    ]
    loop_main = element_prop(
        name="ThreadGroup.main_controller",
        element_type="LoopController",
        testname="Loop Controller",
        props=loop_props,
    )
    loop_ctrl = make_element(
        "GenericController",
        name=f"Loop Controller for {table_name}",
        testname=f"Loop Controller for {table_name}",
        attributes={"guiclass": "LoopControlPanel", "testclass": "LoopController"},
        children=[loop_main],
    )

    # PreProcessor that fills param_N from seed files.
    prep, prep_hash = jsr223_preprocessor_element(
        name=f"{sampler_name}_relprep",
        script=pre_script,
        script_language="groovy",
        testname=f"{sampler_name}_relprep",
        enabled=True,
    )

    # JDBCSampler that runs Prepared Update Statement per loop iteration.
    sampler, samp_hash = jdbc_sampler_element(
        name=sampler_name,
        query=cfg["sql"],
        data_source=cfg["data_source"],
        query_type=cfg["query_type"],
        query_arguments=cfg["query_arguments"],
        query_arguments_types=cfg["query_arguments_types"],
        testname=sampler_name,
    )

    inner = hash_tree(prep, prep_hash, sampler, samp_hash)
    return [loop_ctrl, inner]  # noqa: F841 — fence is implicit
