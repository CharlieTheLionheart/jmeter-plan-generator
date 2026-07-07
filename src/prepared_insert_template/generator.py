"""Core generator for Prepared Insert SQL templates."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from config_parser.models import (
    DatabaseConfig,
    TableConfig,
    TestModelConfig,
    TsDbConfig,
    TsTableConfig,
    WriteConfig,
)

logger = logging.getLogger(__name__)

# Valid prepared write modes that require template generation
_PREPARED_MODES = frozenset(("single_prepared", "batch_prepared"))


def requires_prepared_insert_templates(write_config: Optional[List[WriteConfig]]) -> bool:
    """Return True when any write config entry uses a prepared mode.

    A prepared mode is ``single_prepared`` or ``batch_prepared``.
    """
    if not write_config:
        return False
    return any(getattr(wc, "mode", None) in _PREPARED_MODES for wc in write_config)


def generate_template(table_name: str, columns: List[str]) -> Optional[str]:
    """Generate an INSERT template string for ``table_name``.

    Parameters
    ----------
    table_name:
        Fully qualified table name in ``db.table`` form (lower-case).
    columns:
        Ordered list of column names to include in the VALUES clause.

    Returns
    -------
    A lower-case INSERT template, e.g.
    ``insert into db.table (col1, col2) values (?, ?)``.
    Returns None when ``columns`` is empty to prevent illegal SQL.
    """
    if not columns:
        return None
    col_list = ", ".join(columns)
    return f"insert into {table_name} ({col_list}) values ({', '.join('?' * len(columns))})"


def filter_timeseries_tables(
    ts_dbs: List[TsDbConfig],
) -> List[tuple[str, TsTableConfig]]:
    """Return (db_name, table) pairs for all time-series tables.

    Relational tables are excluded because they use batch_insert in
    SetupThreadGroup and do not use PreparedStatement (see design §3.5.2).

    Parameters
    ----------
    ts_dbs:
        List of time-series database configurations.
    """
    result: List[tuple[str, TsTableConfig]] = []
    for db in ts_dbs:
        for table in db.tables:
            result.append((db.name, table))
    return result


def build_template_dict(
    tables: List[tuple[str, TsTableConfig]],
    columns_by_table: Dict[str, List[str]],
) -> Dict[str, str]:
    """Build a template dictionary keyed by fully qualified table name.

    Parameters
    ----------
    tables:
        List of ``(db_name, table)`` pairs for time-series tables.
    columns_by_table:
        Mapping from lower-case ``db.table`` key to the ordered list of
        column names to include in the INSERT template.

    Returns
    -------
    Dictionary mapping ``db.table`` (lower-case) to the INSERT SQL template.
    Tables with an empty or missing column list are skipped and a warning is logged.
    """
    result: Dict[str, str] = {}
    for db_name, table in tables:
        fqn = f"{db_name}.{table.name}".lower()
        columns = columns_by_table.get(fqn)
        if not columns:
            logger.warning(
                "skipping template for table '%s': no columns available", fqn
            )
            continue
        template = generate_template(fqn, columns)
        if template:
            result[fqn] = template
    return result


class PreparedInsertTemplateGenerator:
    """Generate PreparedStatement INSERT templates for time-series tables."""

    def __init__(
        self,
        model: TestModelConfig,
        write_config: Optional[List[WriteConfig]],
        columns_by_table: Dict[str, List[str]],
    ):
        """Initialize the generator.

        Parameters
        ----------
        model:
            The parsed test model configuration.
        write_config:
            List of write configuration entries. Generation is skipped when
            no entry uses a prepared mode.
        columns_by_table:
            Mapping from lower-case ``db.table`` to the ordered list of
            column names for the VALUES clause.
        """
        self.model = model
        self.write_config = write_config
        self.columns_by_table = columns_by_table

    def generate(self) -> Dict[str, str]:
        """Return the template dictionary.

        Returns an empty dict when no prepared modes are configured or when
        no valid templates can be built.
        """
        if not requires_prepared_insert_templates(self.write_config):
            return {}

        tables = filter_timeseries_tables(self.model.ts_dbs)
        if not tables:
            return {}

        return build_template_dict(tables, self.columns_by_table)
