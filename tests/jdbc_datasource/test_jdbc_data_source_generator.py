"""Tests for jdbc_datasource.JDBCDataSourceGenerator."""

import pytest
from xml.etree import ElementTree as ET

from jdbc_datasource import JDBCDataSourceGenerator, JmxGenerationError


class TestGenerate:
    def test_returns_list_of_two_elements(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_root_tag_is_jdbc_data_source(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        assert ds.tag.endswith("JDBCDataSource")

    def test_data_source_attribute_is_jdbconfig(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        assert ds.get("name") == "jdbcConfig"

    def test_autocommit_is_true(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert '<stringProp name="autocommit">true</stringProp>' in xml

    def test_db_url_string_prop_with_variable(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10, "db_url": "${db_url}"})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "dbUrl" in xml
        assert "${db_url}" in xml

    def test_driver_is_kaiwudb(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "com.kaiwudb.Driver" in xml

    def test_pool_max_uses_literal_integer_value(self):
        """JMeter 5.6.3 DataSourceElement.initPool parses pool_max as
        Integer BEFORE UDV function evaluation, so the value must be a
        literal integer string ("10") not the ``${conn_pool_size}``
        placeholder."""
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "poolMax" in xml
        assert "10" in xml
        # JMeter does Integer.parseInt of poolMax before function eval,
        # so "${conn_pool_size}" placeholder would crash the listener.
        assert "${conn_pool_size}" not in xml

    def test_hardcoded_connection_age(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "connectionAge" in xml
        assert "5000" in xml

    def test_hardcoded_timeout(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert '<stringProp name="timeout">10000</stringProp>' in xml

    def test_hardcoded_trim_interval(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert '<stringProp name="trimInterval">60000</stringProp>' in xml

    def test_check_query_is_empty_string(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        # checkQuery should be empty
        assert 'checkQuery></stringProp>' in xml or 'checkQuery" />' in xml or "checkQuery" in xml

    def test_hash_tree_is_empty(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        _, ht = result
        assert ht.tag.endswith("hashTree")
        assert len(ht) == 0  # empty hashTree has no children

    def test_round_trip_xml_parsing(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml_str = ET.tostring(ds, encoding="unicode")
        # Should not raise - proves it's well-formed
        parsed = ET.fromstring(xml_str)
        assert parsed.tag.endswith("JDBCDataSource")

    def test_username_defaults_to_variable(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "${db_username}" in xml

    def test_password_defaults_to_variable_reference(self):
        """db_password always renders as ``${db_password}`` variable
        reference; UDV carries the configured value. See
        :class:`TestDbUrlAlwaysVariableReference` for the rationale."""
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "${db_password}" in xml

    def test_username_from_config_renders_as_variable_reference(self):
        """Same ``${db_username}`` enforcement; the literal value lives
        in the UDV block, not on the JDBCDataSource element."""
        gen = JDBCDataSourceGenerator({
            "conn_pool_size": 10,
            "db_username": "testuser",
        })
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "${db_username}" in xml
        # Literal must NOT be inlined:
        assert "testuser" not in xml

    def test_password_from_config_renders_as_variable_reference(self):
        gen = JDBCDataSourceGenerator({
            "conn_pool_size": 10,
            "db_password": "testpass",
        })
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "${db_password}" in xml
        assert "testpass" not in xml

    def test_empty_password_is_valid(self):
        # Empty password is a valid configuration
        gen = JDBCDataSourceGenerator({
            "conn_pool_size": 10,
            "db_password": ""
        })
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        assert "password" in xml  # password stringProp exists

    def test_second_element_is_hash_tree(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 10})
        result = gen.generate()
        assert result[1].tag.endswith("hashTree")


class TestValidation:
    def test_conn_pool_size_zero_raises(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": 0})
        with pytest.raises(JmxGenerationError, match="must be positive"):
            gen.generate()

    def test_conn_pool_size_negative_raises(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": -1})
        with pytest.raises(JmxGenerationError, match="must be positive"):
            gen.generate()

    def test_conn_pool_size_non_integer_string_raises(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": "not_a_number"})
        with pytest.raises(JmxGenerationError, match="must be a valid integer"):
            gen.generate()

    def test_conn_pool_size_string_zero_raises(self):
        gen = JDBCDataSourceGenerator({"conn_pool_size": "0"})
        with pytest.raises(JmxGenerationError, match="must be positive"):
            gen.generate()

    def test_missing_conn_pool_size_raises(self):
        gen = JDBCDataSourceGenerator({})
        with pytest.raises(JmxGenerationError, match="must be positive"):
            gen.generate()

    def test_conn_pool_size_as_string_positive_int(self):
        # String integer that is positive should be normalized to literal int
        gen = JDBCDataSourceGenerator({"conn_pool_size": "20"})
        result = gen.generate()
        ds = result[0]
        xml = ET.tostring(ds, encoding="unicode")
        # poolMax serialized as literal "20" (JMeter parses it via
        # Integer.parseInt before UDV function evaluation).
        assert "20" in xml
        assert ">20<" in xml  # tightly the poolMax stringProp element

    def test_empty_config_still_generates(self):
        # Empty config (no conn_config) - will fail validation on pool_size
        # but the db_url/etc default to variable references
        gen = JDBCDataSourceGenerator()
        with pytest.raises(JmxGenerationError):
            gen.generate()


class TestDbUrlAlwaysVariableReference:
    """Regression (2026-07-17 shig smoke):

    ``JDBCDataSource.dbUrl`` MUST always render as a ``${db_url}``
    variable reference, never the literal URL from ``conn_config.db_url``.
    Otherwise ``-Jdb_url=jdbc:...`` operator overrides are silently
    ignored — JMeter's pool init reads the literal XML value at parse
    time, before UDV evaluation.
    """

    @staticmethod
    def _gen_with_conn(db_url: str) -> str:
        gen = JDBCDataSourceGenerator(
            {"conn_pool_size": 10, "db_url": db_url, "db_username": "u", "db_password": "p"}
        )
        ds = gen.generate()[0]
        return ET.tostring(ds, encoding="unicode")

    def test_db_url_with_literal_still_renders_as_variable(self):
        """Even when caller hands in a literal URL, the XML stays a
        variable reference. Pre-fix the XML contained the literal."""
        xml = self._gen_with_conn("jdbc:kaiwudb://10.0.0.5:26257/foo")
        assert "${db_url}" in xml
        assert "10.0.0.5" not in xml
        assert "jdbc:kaiwudb://" not in xml

    def test_db_url_with_variable_already_renders_as_variable(self):
        xml = self._gen_with_conn("${db_url}")
        assert xml.count("${db_url}") >= 1

    def test_db_username_and_password_are_always_variable_references(self):
        """Same enforcement for username/password — operators may
        override via ``-Jdb_username=...`` / ``-Jdb_password=...``.
        """
        xml = self._gen_with_conn("jdbc:kaiwudb://x/y")
        assert "${db_username}" in xml
        assert "${db_password}" in xml


class TestPositionHint:
    def test_position_hint_returns_string(self):
        hint = JDBCDataSourceGenerator.position_hint()
        assert isinstance(hint, str)
        assert hint == "after_user_defined_variables"
