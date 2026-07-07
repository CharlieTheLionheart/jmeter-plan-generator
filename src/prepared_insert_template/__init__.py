"""Prepared Insert template generator for KaiwuDB SVT test plan generator.

Generates INSERT SQL templates with ``?`` placeholders for PreparedStatement
execution in ``single_prepared`` and ``batch_prepared`` write modes.

Public API
----------
``PreparedInsertTemplateGenerator``
    Main generator class; call ``.generate()`` to get the template dict.

``requires_prepared_insert_templates(write_config)``
    Predicate returning True when the config contains any prepared mode.

Template dictionary shape
------------------------
``{db.table: insert into db.table (col1, col2) values (?, ?)}``

Keys are fully qualified table names in lower-case.  Values are lower-case
INSERT templates with positional ``?`` placeholders.  Returns an empty dict
when no prepared modes are configured.
"""

from prepared_insert_template.generator import (
    PreparedInsertTemplateGenerator,
    build_template_dict,
    filter_timeseries_tables,
    generate_template,
    requires_prepared_insert_templates,
)

__all__ = [
    "PreparedInsertTemplateGenerator",
    "build_template_dict",
    "filter_timeseries_tables",
    "generate_template",
    "requires_prepared_insert_templates",
]
