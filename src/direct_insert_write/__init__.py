"""Direct INSERT write helpers — single & batch INSERT samplers with Groovy
data preparation.

Design: openspec/changes/direct-insert-write/design.md
Spec:    openspec/changes/direct-insert-write/specs/direct-insert-write/spec.md

Public surface
--------------

- :func:`generate_single_insert_sql`
- :func:`generate_batch_insert_sql`
- :func:`generate_preprocessor_script` and
  :func:`generate_relational_init_preprocessor_script`
- :func:`generate_jdbc_sampler_config` / :func:`create_jdbc_sampler`
- :func:`create_jsr223_preprocessor_for_write`
- :func:`generate_relational_table_init_sampler`
- :class:`DirectInsertGenerationError`

Conventions enforced (see design.md §"表名使用限定名" and §"SQL 标识符..."):

- Table names are qualified ``database.table``.
- All identifiers and SQL keywords are lower-case.
- Validation failures raise :class:`DirectInsertGenerationError`, which
  subclasses :class:`ddl_generator.generator.DdlGenerationError` so
  callers using a project-wide ``except DdlGenerationError`` continue to
  catch write-side failures.

Sampler binding model (closes review.md C3 / C4):

- Write path: ``queryType=Update Statement`` with one ``?`` per cell;
  the PreProcessor sets ``param_0..param_{N*batch_lines-1}`` (row-major)
  and the sampler references them via ``queryArguments=${param_N}``.
- Relational init: ``queryType=Prepared Update Statement`` with the
  same ``param_N`` binding; preprocessor reads column seed files
  directly (no shared-memory row aggregate).
"""

from direct_insert_write.errors import DirectInsertGenerationError
from direct_insert_write.preprocessor_generator import (
    generate_preprocessor_script,
    generate_relational_init_preprocessor_script,
)
from direct_insert_write.sampler_generator import (
    create_jdbc_sampler,
    create_jsr223_preprocessor_for_write,
    generate_jdbc_sampler_config,
    generate_relational_table_init_sampler,
)
from direct_insert_write.sql_generator import (
    generate_batch_insert_sql,
    generate_single_insert_sql,
)

__all__ = [
    "DirectInsertGenerationError",
    "generate_single_insert_sql",
    "generate_batch_insert_sql",
    "generate_preprocessor_script",
    "generate_relational_init_preprocessor_script",
    "generate_jdbc_sampler_config",
    "create_jdbc_sampler",
    "create_jsr223_preprocessor_for_write",
    "generate_relational_table_init_sampler",
]
