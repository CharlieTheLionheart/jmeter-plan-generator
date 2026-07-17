"""JDBCDataSource generator."""

from __future__ import annotations

from typing import List, Optional

from xml.etree import ElementTree as ET

from utils.xml_helpers import (
    bool_prop,
    empty_hash_tree,
    jdbc_data_source_element,
    string_prop,
)


class JmxGenerationError(Exception):
    """Raised when JMX generation or serialisation fails."""


# Fixed data source name - all samplers reference this
DATASOURCE_NAME = "jdbcConfig"
DRIVER_CLASS = "com.kaiwudb.Driver"


class JDBCDataSourceGenerator:
    """Generate a JDBCDataSource XML element for JMeter test plans.

    Parameters
    ----------
    conn_config : dict, optional
        Connection configuration dictionary. Expected keys:
        - ``db_url`` (str): JDBC connection URL (may include ``${...}`` variables)
        - ``db_username`` (str): Database username (may include ``${...}`` variables)
        - ``db_password`` (str): Database password (may include ``${...}`` variables)
        - ``conn_pool_size`` (str | int): Maximum pool size (must be positive integer)

        If ``conn_pool_size`` is not a positive integer, raises ``JmxGenerationError``.
        Empty username/password strings are valid configurations.
    """

    def __init__(self, conn_config: Optional[dict] = None) -> None:
        self._conn_config = conn_config or {}

    def _validate(self) -> None:
        """Validate configuration and fail fast if invalid.

        Raises
        ------
        JmxGenerationError
            When conn_pool_size is not a positive integer.
        """
        conn_pool_size = self._conn_config.get("conn_pool_size", 0)
        # Accept string or int
        try:
            size = int(conn_pool_size)
        except (ValueError, TypeError):
            raise JmxGenerationError(
                f"conn_pool_size must be a valid integer, got: {conn_pool_size!r}"
            ) from None
        if size <= 0:
            raise JmxGenerationError(
                f"conn_pool_size must be positive, got: {size}"
            )

    def generate(self) -> List[ET.Element]:
        """Generate the JDBCDataSource element.

        Returns
        -------
        A flat list ``[JDBCDataSource element, hashTree/ element]``.

        Raises
        ------
        JmxGenerationError
            When conn_pool_size is not a positive integer.
        """
        self._validate()

        # Always render as ``${db_url}`` reference so operators can override
        # per JMeter instance with ``-Jdb_url=...`` (e.g. local smoke against
        # an unreachable port, or per-end deployment against a different
        # host/port). The UDV carries the default value defined by
        # ``ConnConfig.db_url`` in test_cfg.yaml — typically
        # ``jdbc:kaiwudb://127.0.0.1:26257/defaultdb`` for local debugging.
        # Pre-2026-07-17 the generator emitted the literal URL into
        # JDBCDataSource.dbUrl which made ``-Jdb_url`` overrides no-op.
        db_url = "${db_url}"
        db_username = "${db_username}"
        db_password = "${db_password}"
        # poolMax rendered as a literal integer string: JMeter 5.6.3
        # DataSourceElement.initPool runs Integer.parseInt on the raw
        # text BEFORE UDV function evaluation, so a literal ``${var}``
        # placeholder would crash with ``NumberFormatException``. Use
        # the validated integer directly; UDV still carries the
        # ``conn_pool_size`` field for downstream visibility.
        pool_max = str(int(self._conn_config.get("conn_pool_size", 10)))

        ds, ds_hash = jdbc_data_source_element(
            name=DATASOURCE_NAME,
            db_url=db_url,
            driver=DRIVER_CLASS,
            pool_max=pool_max,
            autocommit="true",
            keep_alive=True,
            connection_age="5000",
            timeout="10000",
            trim_interval="60000",
            transaction_isolation="DEFAULT",
            check_query="",
            username=db_username,
            password=db_password,
            preinit=True,
            init_query="",
            connection_properties="",
            testname=DATASOURCE_NAME,
            enabled=True,
        )

        return [ds, ds_hash]

    @staticmethod
    def position_hint() -> str:
        """Return positioning hint for JMX assembler.

        Returns
        -------
        ``"after_user_defined_variables"`` - the JDBCDataSource should be
        placed after UserDefinedVariables and before all ThreadGroups.
        """
        return "after_user_defined_variables"
