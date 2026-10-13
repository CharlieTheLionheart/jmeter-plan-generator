"""Tests for ``src/pub_sub/__init__.py`` public API surface (§3.7).

Per design.md line 281-285 + tasks.md §3.7.1, the 5 public APIs that
``from pub_sub import X`` should expose are:

- ``build_publication_sql``
- ``build_subscribe_dest_schemas``
- ``build_create_subscription_sql``
- ``append_pub_sub_to_setup_tg``
- ``generate_pub_sub_verify_tg``

The private helpers (``_build_show_subscription_status_sampler`` /
``_build_count_sampler``) are **not** part of the public surface and
remain accessible only via ``from pub_sub.pub_sub_verify_tg import ...``.
"""

from __future__ import annotations


def test_build_publication_sql_importable() -> None:
    """``build_publication_sql`` 应能从 ``pub_sub`` 顶层 import."""
    from pub_sub import build_publication_sql  # noqa: F401

    assert callable(build_publication_sql)


def test_build_subscribe_dest_schemas_importable() -> None:
    """``build_subscribe_dest_schemas`` 应能从 ``pub_sub`` 顶层 import."""
    from pub_sub import build_subscribe_dest_schemas  # noqa: F401

    assert callable(build_subscribe_dest_schemas)


def test_build_create_subscription_sql_importable() -> None:
    """``build_create_subscription_sql`` 应能从 ``pub_sub`` 顶层 import."""
    from pub_sub import build_create_subscription_sql  # noqa: F401

    assert callable(build_create_subscription_sql)


def test_append_pub_sub_to_setup_tg_importable() -> None:
    """``append_pub_sub_to_setup_tg`` 应能从 ``pub_sub`` 顶层 import."""
    from pub_sub import append_pub_sub_to_setup_tg  # noqa: F401

    assert callable(append_pub_sub_to_setup_tg)


def test_generate_pub_sub_verify_tg_importable() -> None:
    """``generate_pub_sub_verify_tg`` 应能从 ``pub_sub`` 顶层 import."""
    from pub_sub import generate_pub_sub_verify_tg  # noqa: F401

    assert callable(generate_pub_sub_verify_tg)


def test_public_api_wildcard_import() -> None:
    """``from pub_sub import *`` 至少暴露 5 个公开 API (``__all__`` 锁定).

    设计文档明确列出 5 个公开 API, 应通过 ``__all__`` 锁定暴露范围,
    避免 caller 误用私有 helper (e.g. ``_build_count_sampler``).
    """
    import pub_sub

    public_api = getattr(pub_sub, "__all__", None)
    assert public_api is not None, "pub_sub.__all__ not defined"
    expected = {
        "build_publication_sql",
        "build_subscribe_dest_schemas",
        "build_create_subscription_sql",
        "append_pub_sub_to_setup_tg",
        "generate_pub_sub_verify_tg",
    }
    assert set(public_api) == expected


def test_private_helpers_not_exposed() -> None:
    """私有 helper (``_build_count_sampler`` / ``_build_show_subscription_status_sampler``)
    不在 ``__all__`` 中 (per design.md line 281-285 仅列 5 个公开 API).

    防止 caller 误用 module-private helper, 强制走 ``pub_sub.pub_sub_verify_tg`` 路径.
    """
    import pub_sub

    public_api = set(getattr(pub_sub, "__all__", ()))
    assert "_build_count_sampler" not in public_api
    assert "_build_show_subscription_status_sampler" not in public_api
