from __future__ import annotations

import pytest
from pydantic import ValidationError

from config_parser.models import RestApiConfig
from utils.rest_errors import RestConfigError


# 注意（2026-07-27）：schemaless Login 强制非空密码用户，非空密码用户只能
# 通过安全模式（TLS）创建，因此 ``https_mode='insecure'`` 已移除。所有 fixture
# 用 ``https_mode='tls'`` + ``ca_cert_path`` 必填。


_CA = "/etc/kaiwudb/certs/ca.crt"


def test_required_fields_present():
    cfg = RestApiConfig(https_mode="tls", login_user="root", ca_cert_path=_CA)
    assert cfg.http_port == 8080


def test_missing_https_mode_defaults_to_tls():
    """``https_mode`` 缺省时默认 ``"tls"``（2026-07-27 行为变更：insecure 移除）。"""
    cfg = RestApiConfig(login_user="root", ca_cert_path=_CA)
    assert cfg.https_mode == "tls"


def test_invalid_https_mode_value():
    """``https_mode='insecure'`` 现为非法值（Pydantic Literal 收紧）。"""
    with pytest.raises(ValidationError):
        RestApiConfig(https_mode="insecure", login_user="root", ca_cert_path=_CA)


def test_tls_requires_ca_cert_path():
    """Pydantic v2 wraps `RestConfigError` raised in `@model_validator` as
    `ValidationError`. Verify the wrapped error message contains the
    factory message ("ca_cert_path") and the type field is `value_error`.
    """
    with pytest.raises(ValidationError) as exc_info:
        RestApiConfig(https_mode="tls", login_user="root")
    msg = str(exc_info.value)
    assert "ca_cert_path" in msg
    # ValidationError carries the original type; `value_error` is what
    # Pydantic uses for ValueError subclasses including RestConfigError.
    err_types = {e["type"] for e in exc_info.value.errors()}
    assert "value_error" in err_types


def test_ca_cert_path_required_when_omitted():
    """ca_cert_path 缺省即报 RestConfigError（fail-fast，proposal §1.1 场景 1）。"""
    with pytest.raises(ValidationError) as exc_info:
        RestApiConfig(login_user="root")
    assert "ca_cert_path" in str(exc_info.value)


def test_http_port_range():
    with pytest.raises(ValidationError):
        RestApiConfig(https_mode="tls", login_user="root", ca_cert_path=_CA, http_port=99999)


def test_default_db_required():
    with pytest.raises(ValidationError):
        RestApiConfig(https_mode="tls", login_user="root", ca_cert_path=_CA, default_db=None)


def test_pre_create_tables_default_true():
    assert RestApiConfig(https_mode="tls", login_user="root", ca_cert_path=_CA).pre_create_tables is True