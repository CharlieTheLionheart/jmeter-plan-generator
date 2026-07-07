"""JDBC DataSource generator for JMeter test plans.

This module generates the JDBCDataSource XML element that configures the
database connection pool. All JDBCSamplers and JSR223Samplers access the
database through this data source.

Data Source Name
----------------
The generated data source is fixed at ``jdbcConfig`` - all samplers must
reference it via ``dataSource="jdbcConfig"``.

Variable Dependencies
---------------------
This module expects the following JMeter variables to be defined by
UserDefinedVariablesGenerator:
- ``${db_url}`` - JDBC connection URL
- ``${db_username}`` - Database username
- ``${db_password}`` - Database password
- ``${conn_pool_size}`` - Maximum connection pool size

If ``conn_pool_size`` is not a positive integer, generation fails fast
with JmxGenerationError rather than producing an incomplete JMX.
"""

from jdbc_datasource.jdbc_data_source_generator import (
    JDBCDataSourceGenerator,
    JmxGenerationError,
)

__all__ = [
    "JDBCDataSourceGenerator",
    "JmxGenerationError",
]
