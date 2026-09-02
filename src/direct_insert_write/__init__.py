"""Direct INSERT write helpers — relational-table init batch INSERT samplers.

Design: openspec/changes/direct-insert-write/design.md
Spec:    openspec/changes/direct-insert-write/specs/direct-insert-write/spec.md

The write TG path (``single_insert`` / ``batch_insert``) is wired
through
:func:`jmx_skeleton_generator.generators.write_groups._build_inline_sql_preprocessor_script`;
this module only serves the relational init sampler.

Public surface
--------------

- :func:`generate_batch_insert_sql` — multi-row INSERT template for
  the relational init sampler
- :func:`generate_relational_init_preprocessor_script` — Groovy
  PreProcessor that reads column seed files and emits
  ``param_N`` cells for the sampler to bind
- :func:`generate_relational_table_init_sampler` — config dict
  consumed by :mod:`jmx_skeleton_generator.generators.ddl_setup`
- :class:`DirectInsertGenerationError`

Conventions enforced (see design.md §"表名使用限定名" and §"SQL 标识符..."):

- Table names are qualified ``database.table``.
- All identifiers and SQL keywords are lower-case.
- Validation failures raise :class:`DirectInsertGenerationError`, which
  subclasses :class:`ddl_generator.generator.DdlGenerationError` so
  callers using a project-wide ``except DdlGenerationError`` continue
  to catch write-side failures.
"""

from direct_insert_write.errors import DirectInsertGenerationError
from direct_insert_write.preprocessor_generator import (
    generate_relational_init_preprocessor_script,
)
from direct_insert_write.sampler_generator import (
    generate_relational_table_init_sampler,
)
from direct_insert_write.sql_generator import (
    generate_batch_insert_sql,
)

__all__ = [
    "DirectInsertGenerationError",
    "generate_batch_insert_sql",
    "generate_relational_init_preprocessor_script",
    "generate_relational_table_init_sampler",
]