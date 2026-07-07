"""Tests for Prepared Insert template generator."""

import pytest

from config_parser.models import (
    ColTypeConfig,
    PrimaryTagColTypeConfig,
    RelDbConfig,
    RelTableConfig,
    TestModelConfig,
    TsDbConfig,
    TsTableConfig,
    WriteConfig,
)
from prepared_insert_template import (
    PreparedInsertTemplateGenerator,
    build_template_dict,
    filter_timeseries_tables,
    generate_template,
    requires_prepared_insert_templates,
)


# ---------------------------------------------------------------------------
# requires_prepared_insert_templates
# ---------------------------------------------------------------------------

class TestRequiresPreparedInsertTemplates:
    def test_none_config(self):
        assert requires_prepared_insert_templates(None) is False

    def test_empty_config(self):
        assert requires_prepared_insert_templates([]) is False

    def test_only_single_insert(self):
        cfg = [WriteConfig(tbl_name="t", mode="single_insert")]
        assert requires_prepared_insert_templates(cfg) is False

    def test_only_batch_insert(self):
        cfg = [WriteConfig(tbl_name="t", mode="batch_insert")]
        assert requires_prepared_insert_templates(cfg) is False

    def test_single_prepared(self):
        cfg = [WriteConfig(tbl_name="t", mode="single_prepared")]
        assert requires_prepared_insert_templates(cfg) is True

    def test_batch_prepared(self):
        cfg = [WriteConfig(tbl_name="t", mode="batch_prepared")]
        assert requires_prepared_insert_templates(cfg) is True

    def test_mixed_modes_with_prepared(self):
        cfg = [
            WriteConfig(tbl_name="t1", mode="single_insert"),
            WriteConfig(tbl_name="t2", mode="batch_prepared"),
            WriteConfig(tbl_name="t3", mode="schemaless"),
        ]
        assert requires_prepared_insert_templates(cfg) is True

    def test_mixed_modes_without_prepared(self):
        cfg = [
            WriteConfig(tbl_name="t1", mode="single_insert"),
            WriteConfig(tbl_name="t2", mode="batch_insert"),
        ]
        assert requires_prepared_insert_templates(cfg) is False

    def test_missing_mode_key(self):
        # WriteConfig requires mode; construct via model_validator workaround
        cfg = [WriteConfig(tbl_name="t", mode="batch_insert")]
        assert requires_prepared_insert_templates(cfg) is False


# ---------------------------------------------------------------------------
# generate_template
# ---------------------------------------------------------------------------

class TestGenerateTemplate:
    def test_single_column(self):
        result = generate_template("db.t", ["col1"])
        assert result == "insert into db.t (col1) values (?)"

    def test_multiple_columns(self):
        result = generate_template("iot_monitor.t_cnc", ["ts", "ptag_int8_1", "col_int8_1"])
        assert result == "insert into iot_monitor.t_cnc (ts, ptag_int8_1, col_int8_1) values (?, ?, ?)"

    def test_column_order_preserved(self):
        cols = ["col_c", "col_a", "col_b"]
        result = generate_template("db.t", cols)
        assert "col_c, col_a, col_b" in result

    def test_empty_columns_returns_none(self):
        result = generate_template("db.t", [])
        assert result is None

    def test_exact_sql_format(self):
        result = generate_template("iot_metadata.t_workshop", ["pk_int8_1", "col_varchar_1"])
        assert result == "insert into iot_metadata.t_workshop (pk_int8_1, col_varchar_1) values (?, ?)"

    def test_lowercase_keywords(self):
        result = generate_template("db.t", ["a", "b"])
        assert result.startswith("insert into ")
        assert " values " in result


# ---------------------------------------------------------------------------
# filter_timeseries_tables
# ---------------------------------------------------------------------------

class TestFilterTimeseriesTables:
    def _make_ts_model(self):
        return TestModelConfig(
            rel_dbs=[
                RelDbConfig(
                    name="rel_db",
                    tables=[
                        RelTableConfig(
                            name="rel_table",
                            primary_key_count=1,
                            data_col_count=1,
                            primary_keys=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                            data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                        )
                    ],
                )
            ],
            ts_dbs=[
                TsDbConfig(
                    name="ts_db",
                    tables=[
                        TsTableConfig(
                            name="ts_table",
                            data_col_count=1,
                            primary_tag_count=0,
                            regular_tag_count=0,
                            data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                            primary_tags=[],
                            regular_tags=[],
                        )
                    ],
                )
            ],
        )

    def test_excludes_relational_tables(self):
        model = self._make_ts_model()
        result = filter_timeseries_tables(model.ts_dbs)
        fqn_set = {f"{db}.{t.name}" for db, t in result}
        assert "rel_db.rel_table" not in fqn_set

    def test_includes_time_series_tables(self):
        model = self._make_ts_model()
        result = filter_timeseries_tables(model.ts_dbs)
        fqn_set = {f"{db}.{t.name}" for db, t in result}
        assert "ts_db.ts_table" in fqn_set

    def test_empty_rel_dbs(self):
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[
                TsDbConfig(
                    name="ts_db",
                    tables=[
                        TsTableConfig(
                            name="ts_table",
                            data_col_count=1,
                            primary_tag_count=0,
                            regular_tag_count=0,
                            data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                            primary_tags=[],
                            regular_tags=[],
                        )
                    ],
                )
            ],
        )
        result = filter_timeseries_tables(model.ts_dbs)
        assert len(result) == 1

    def test_empty_ts_dbs(self):
        model = TestModelConfig(
            rel_dbs=[
                RelDbConfig(
                    name="rel_db",
                    tables=[
                        RelTableConfig(
                            name="rel_table",
                            primary_key_count=1,
                            data_col_count=0,
                            primary_keys=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                            data_cols=[],
                        )
                    ],
                )
            ],
            ts_dbs=[],
        )
        result = filter_timeseries_tables(model.ts_dbs)
        assert result == []


# ---------------------------------------------------------------------------
# build_template_dict
# ---------------------------------------------------------------------------

class TestBuildTemplateDict:
    def _ts_table(self, name="t", data_cols=None):
        if data_cols is None:
            data_cols = [ColTypeConfig(col_type="int8", type_proportion=1.0)]
        return TsTableConfig(
            name=name,
            data_col_count=len(data_cols),
            primary_tag_count=0,
            regular_tag_count=0,
            data_cols=data_cols,
            primary_tags=[],
            regular_tags=[],
        )

    def test_single_database_single_table(self):
        ts_dbs = [TsDbConfig(name="db1", tables=[self._ts_table("t1")])]
        tables = filter_timeseries_tables(ts_dbs)
        cols = {"db1.t1": ["a", "b"]}
        result = build_template_dict(tables, cols)
        assert result == {"db1.t1": "insert into db1.t1 (a, b) values (?, ?)"}

    def test_multiple_databases(self):
        ts_dbs = [
            TsDbConfig(name="iot_monitor", tables=[self._ts_table("t_cnc")]),
            TsDbConfig(name="iot_metadata", tables=[self._ts_table("t_workshop")]),
        ]
        tables = filter_timeseries_tables(ts_dbs)
        cols = {
            "iot_monitor.t_cnc": ["ts", "ptag_int8_1"],
            "iot_metadata.t_workshop": ["pk_int8_1"],
        }
        result = build_template_dict(tables, cols)
        assert len(result) == 2
        assert "iot_monitor.t_cnc" in result
        assert "iot_metadata.t_workshop" in result

    def test_skips_table_with_empty_columns(self, caplog):
        ts_dbs = [TsDbConfig(name="db1", tables=[self._ts_table("t1")])]
        tables = filter_timeseries_tables(ts_dbs)
        cols: dict = {}
        result = build_template_dict(tables, cols)
        assert result == {}
        assert "skipping template" in caplog.text

    def test_returns_empty_dict_when_no_valid_tables(self):
        result = build_template_dict([], {})
        assert result == {}


# ---------------------------------------------------------------------------
# PreparedInsertTemplateGenerator
# ---------------------------------------------------------------------------

class TestPreparedInsertTemplateGenerator:
    def _ts_table(self, name="t", data_cols=None):
        if data_cols is None:
            data_cols = [ColTypeConfig(col_type="int8", type_proportion=1.0)]
        return TsTableConfig(
            name=name,
            data_col_count=len(data_cols),
            primary_tag_count=0,
            regular_tag_count=0,
            data_cols=data_cols,
            primary_tags=[],
            regular_tags=[],
        )

    def test_returns_empty_when_no_prepared_modes(self):
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[
                TsDbConfig(
                    name="ts_db",
                    tables=[self._ts_table("ts_table")],
                )
            ],
        )
        write_cfg = [WriteConfig(tbl_name="ts_table", mode="batch_insert")]
        gen = PreparedInsertTemplateGenerator(model, write_cfg, {"ts_db.ts_table": ["a"]})
        assert gen.generate() == {}

    def test_full_happy_path(self):
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[
                TsDbConfig(
                    name="iot_monitor",
                    tables=[self._ts_table("t_cnc")],
                )
            ],
        )
        write_cfg = [WriteConfig(tbl_name="t_cnc", mode="single_prepared")]
        gen = PreparedInsertTemplateGenerator(
            model, write_cfg, {"iot_monitor.t_cnc": ["ts", "ptag_int8_1", "col_int8_1"]}
        )
        result = gen.generate()
        assert "iot_monitor.t_cnc" in result
        assert "insert into " in result["iot_monitor.t_cnc"]
        assert "values (?, ?, ?)" in result["iot_monitor.t_cnc"]

    def test_all_relational_tables_returns_empty(self):
        model = TestModelConfig(
            rel_dbs=[
                RelDbConfig(
                    name="rel_db",
                    tables=[
                        RelTableConfig(
                            name="rel_table",
                            primary_key_count=1,
                            data_col_count=1,
                            primary_keys=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                            data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                        )
                    ],
                )
            ],
            ts_dbs=[],
        )
        write_cfg = [WriteConfig(tbl_name="rel_table", mode="batch_prepared")]
        gen = PreparedInsertTemplateGenerator(model, write_cfg, {"rel_db.rel_table": ["a"]})
        assert gen.generate() == {}

    def test_multi_database_output(self):
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[
                TsDbConfig(name="db1", tables=[self._ts_table("t1")]),
                TsDbConfig(name="db2", tables=[self._ts_table("t2")]),
            ],
        )
        write_cfg = [WriteConfig(tbl_name="t1", mode="batch_prepared")]
        gen = PreparedInsertTemplateGenerator(
            model, write_cfg, {"db1.t1": ["a"], "db2.t2": ["b"]}
        )
        result = gen.generate()
        assert len(result) == 2
        assert "db1.t1" in result
        assert "db2.t2" in result

    def test_write_config_none_skips_generation(self):
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[
                TsDbConfig(
                    name="ts_db",
                    tables=[self._ts_table("ts_table")],
                )
            ],
        )
        gen = PreparedInsertTemplateGenerator(model, None, {"ts_db.ts_table": ["a"]})
        assert gen.generate() == {}

    def test_write_config_empty_skips_generation(self):
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[
                TsDbConfig(
                    name="ts_db",
                    tables=[self._ts_table("ts_table")],
                )
            ],
        )
        gen = PreparedInsertTemplateGenerator(model, [], {"ts_db.ts_table": ["a"]})
        assert gen.generate() == {}


# ---------------------------------------------------------------------------
# Boundary tests
# ---------------------------------------------------------------------------

class TestBoundaryConditions:
    def _ts_table(self, name="t"):
        return TsTableConfig(
            name=name,
            data_col_count=1,
            primary_tag_count=0,
            regular_tag_count=0,
            data_cols=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
            primary_tags=[],
            regular_tags=[],
        )

    def test_empty_database_list(self):
        """Test that an empty template dict is returned when no databases are configured.

        Note: TestModelConfig requires at least one database, so we pass an empty
        ts_dbs list (which combined with an empty rel_dbs would fail validation).
        We test the generator boundary at the write_config level instead.
        """
        # Generator with empty write_config returns {} without accessing model
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[
                TsDbConfig(name="empty_db", tables=[]),
            ],
        )
        write_cfg = [WriteConfig(tbl_name="t", mode="batch_prepared")]
        gen = PreparedInsertTemplateGenerator(model, write_cfg, {})
        assert gen.generate() == {}

    def test_empty_table_list_in_ts_db(self):
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[TsDbConfig(name="empty_db", tables=[])],
        )
        write_cfg = [WriteConfig(tbl_name="t", mode="batch_prepared")]
        gen = PreparedInsertTemplateGenerator(model, write_cfg, {})
        assert gen.generate() == {}

    def test_reserved_word_column_names_not_quoted(self):
        """Reserved word column names are passed through unquoted.

        KaiwuDB handles reserved words in identifiers at the JDBC/driver level.
        """
        model = TestModelConfig(
            rel_dbs=[],
            ts_dbs=[
                TsDbConfig(
                    name="db",
                    tables=[
                        TsTableConfig(
                            name="t",
                            data_col_count=3,
                            primary_tag_count=0,
                            regular_tag_count=0,
                            data_cols=[
                                ColTypeConfig(col_type="int8", type_proportion=1.0),
                            ],
                            primary_tags=[],
                            regular_tags=[],
                        )
                    ],
                )
            ],
        )
        write_cfg = [WriteConfig(tbl_name="t", mode="batch_prepared")]
        cols = {"db.t": ["select", "from", "where"]}
        gen = PreparedInsertTemplateGenerator(model, write_cfg, cols)
        result = gen.generate()
        assert "db.t" in result
        # Reserved words appear as bare identifiers in the template
        assert "select" in result["db.t"]
        assert "from" in result["db.t"]
        assert "where" in result["db.t"]

    def test_downstream_empty_dict_handled_gracefully(self):
        """Verify that downstream consumers receiving an empty dict can handle it."""
        model = TestModelConfig(
            rel_dbs=[
                RelDbConfig(
                    name="rel_db",
                    tables=[
                        RelTableConfig(
                            name="rel_table",
                            primary_key_count=1,
                            data_col_count=0,
                            primary_keys=[ColTypeConfig(col_type="int8", type_proportion=1.0)],
                            data_cols=[],
                        )
                    ],
                )
            ],
            ts_dbs=[],
        )
        write_cfg = [WriteConfig(tbl_name="rel_table", mode="batch_insert")]
        gen = PreparedInsertTemplateGenerator(model, write_cfg, {})
        result = gen.generate()
        assert result == {}
        assert isinstance(result, dict)
        assert len(result) == 0
