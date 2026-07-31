"""针对 RestConfigError 的单元测试。

覆盖 rest_api 配置的三种 fail-fast 场景（proposal §1.1）：
  1. https_mode=tls 但 ca_cert_path 缺失
  2. rest_api 配置段缺失（mode == "schemaless" 时；§5 锁定 enum 复用 `schemaless`，参见 task-5-brief.md §A）
  3. 字段类型错误（如 https_mode 不是 insecure|tls）
"""

from utils.rest_errors import RestConfigError


def test_rest_config_error_is_value_error_subclass():
    """RestConfigError 必须继承 ValueError，以便上游按 ValueError 捕获。"""
    assert issubclass(RestConfigError, ValueError)


def test_missing_ca_cert_message():
    """https_mode=tls 缺 ca_cert_path 时，message 指明缺失字段。"""
    err = RestConfigError.missing_ca_cert()
    assert isinstance(err, RestConfigError)
    msg = str(err)
    assert "ca_cert_path" in msg
    assert "tls" in msg


def test_missing_rest_api_message():
    """schemaless 模式缺 rest_api 配置段时，message 指明缺失配置段。"""
    err = RestConfigError.missing_rest_api()
    assert isinstance(err, RestConfigError)
    msg = str(err)
    assert "rest_api" in msg
    assert "schemaless" in msg


def test_invalid_field_message():
    """字段类型/取值错误时，message 携带字段名、实际值、期望取值。"""
    err = RestConfigError.invalid_field("https_mode", "foo", "insecure|tls")
    assert isinstance(err, RestConfigError)
    msg = str(err)
    assert "https_mode" in msg
    assert "foo" in msg
    assert "insecure|tls" in msg


def test_raisable_and_catchable_as_value_error():
    """构造出的异常可直接 raise 并被 ValueError 捕获。"""
    try:
        raise RestConfigError.missing_ca_cert()
    except ValueError as exc:
        assert "ca_cert_path" in str(exc)
    else:  # pragma: no cover - 分支不应触达
        raise AssertionError("RestConfigError 未按 ValueError 抛出")
