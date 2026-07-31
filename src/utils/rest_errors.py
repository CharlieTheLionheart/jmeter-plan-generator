"""rest_api 配置的 fail-fast 异常。

生成器在遇到无法继续的 rest_api 配置时，应立即抛出 ``RestConfigError``
并携带可操作的中文错误信息，而不是产出不可运行的 JMX。

覆盖三种 fail-fast 场景（proposal §1.1）：
  1. ``https_mode=tls`` 但 ``ca_cert_path`` 缺失
  2. ``rest_api`` 配置段缺失（``mode == "schemaless"`` 时；§5 锁定 enum 复用 `schemaless`，参见 brief §A）
  3. 字段类型/取值错误（如 ``https_mode`` 不是 ``insecure|tls``）
"""

from __future__ import annotations


class RestConfigError(ValueError):
    """针对 rest_api 配置的 fail-fast 异常，携带可操作的中文错误信息。

    继承 ``ValueError``，使上游既可精确捕获 ``RestConfigError``，也可按
    ``ValueError`` 统一处理配置类错误。三个 classmethod 工厂封装了固定的
    message 模板，供下游 Task 在校验失败时直接抛出。
    """

    @classmethod
    def missing_ca_cert(cls) -> "RestConfigError":
        """场景 1：``https_mode=tls`` 但未提供 ``ca_cert_path``。"""
        return cls("https_mode=tls 需要提供 ca_cert_path，但 rest_api 配置中缺失该字段")

    @classmethod
    def missing_rest_api(cls) -> "RestConfigError":
        """场景 2：``mode=schemaless`` 但缺少 ``rest_api`` 配置段。"""
        return cls("mode=schemaless 需要 rest_api 配置段，但未在配置中找到")

    @classmethod
    def invalid_field(cls, field: str, value: object, expected: str) -> "RestConfigError":
        """场景 3：字段类型或取值非法。

        Parameters
        ----------
        field:
            出错的配置字段名。
        value:
            实际读取到的非法值。
        expected:
            期望的取值说明（如 ``"insecure|tls"``）。
        """
        return cls(f"rest_api 字段 {field} 取值非法：期望 {expected}，实际得到 {value!r}")
