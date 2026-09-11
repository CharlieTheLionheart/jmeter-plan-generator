from __future__ import annotations

import pytest
from pydantic import ValidationError

from config_parser.models import (
    ConnConfig,
    RestApiConfig,
    TestConfig,
    TsDbConfig,
    TestModelConfig,
    TsTableConfig,
    WriteConfig,
)
from jmx_skeleton_generator.generators.skeleton import JMXSkeletonGenerator
from utils.rest_errors import RestConfigError


def _cfg(mode, rest=None):
    return TestConfig(
        conn_config=ConnConfig(db_url="jdbc:kaiwudb://localhost:26257/defaultdb"),
        write_config=[WriteConfig(tbl_name="defaultdb.meters", mode=mode)],
        rest_api_config=rest,
    )


@pytest.fixture
def ts_dbs_model():
    """Minimal TestModelConfig with one ts_db/table for generator routing.

    The model needs at least one TsTableConfig so the generator iterates
    at least once. Field shapes mirror test_model_schemaless.yaml §6.1.
    `data_col_count=0` because the §6 schema validation runs but we
    only need routing to enter the HTTP path (data columns are irrelevant
    for mode dispatch).
    """
    return TestModelConfig(
        ts_dbs=[
            TsDbConfig(
                name="defaultdb",
                tables=[
                    TsTableConfig(
                        name="meters",
                        data_col_count=0,
                        primary_tags=[],
                        regular_tags=[],
                        data_cols=[],
                    ),
                ],
            ),
        ],
    )


def test_schemaless_mode_with_valid_rest_api_generates_jmx(tmp_path, ts_dbs_model):
    """Positive assertion: mode=schemaless + valid rest_api (TLS + ca_cert_path)
    → JMXSkeletonGenerator produces a JMX file containing HTTPSamplerProxy (HTTP path),
    NOT JDBCSampler.

    Pydantic v2 wraps `RestConfigError` from @model_validator as `ValidationError`,
    so the model construction may raise ValidationError if the model_validator
    fires (e.g., when ca_cert_path is missing).

    2026-07-27 行为变更：schemaless Login 强制 TLS（insecure 路径移除），
    ``https_mode='insecure'`` 已不接受。
    """
    cfg = _cfg("schemaless", RestApiConfig(
        https_mode="tls", login_user="root", ca_cert_path="/etc/kaiwudb/certs/ca.crt",
    ))
    path = JMXSkeletonGenerator(cfg, output_dir=str(tmp_path), model=ts_dbs_model).generate()
    assert path.exists()
    xml = path.read_text(encoding="utf-8")
    # HTTP path produces HTTPSamplerProxy; JDBC path produces JDBCSampler.
    # Assert at least one HTTPSamplerProxy is present.
    assert "HTTPSamplerProxy" in xml, "schemaless mode must produce HTTPSamplerProxy"
    # SetupTG HTTP Login sampler should appear (per §9.1 P0 SetupTG flow).
    assert "Login" in xml or "DDL Login" in xml or "REST_Login" in xml, (
        "schemaless SetupTG must include a Login HTTPSamplerProxy"
    )


def test_schemaless_mode_missing_rest_api_raises_error():
    cfg = _cfg("schemaless")
    with pytest.raises(RestConfigError, match="mode=schemaless"):
        JMXSkeletonGenerator(cfg).generate()


def test_jdbc_mode_missing_rest_api_no_error():
    """mode=batch_prepared + missing rest_api → JDBC path runs without error."""
    cfg = _cfg("prepare")
    # Should NOT raise RestConfigError; may raise other generator errors
    # (e.g., missing ddl_statements / model) but those are not the gate.
    try:
        JMXSkeletonGenerator(cfg).generate()
    except RestConfigError as exc:
        pytest.fail(f"JDBC path should not raise RestConfigError, got: {exc}")


def test_schemaless_missing_ca_cert_raises_error(ts_dbs_model):
    """ca_cert_path 缺失（2026-07-27 起 always TLS）→ RestConfigError 抛出。

    Pydantic v2 wraps the model_validator raise as ValidationError; we accept
    either type, then verify the wrapped error message.
    """
    with pytest.raises((ValidationError, RestConfigError)) as exc_info:
        JMXSkeletonGenerator(
            _cfg("schemaless", RestApiConfig(https_mode="tls", login_user="root")),
            model=ts_dbs_model,
        ).generate()
    msg = str(exc_info.value)
    assert "ca_cert_path" in msg
