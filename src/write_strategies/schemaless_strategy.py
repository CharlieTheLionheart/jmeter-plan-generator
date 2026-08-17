"""Schemaless write strategy — DEAD CODE since 2026-07-31 (d461e40).

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

历史背景：
2026-07-10 commit ``040e555`` 引入本 strategy 作为 T2 占位（彼时
schemaless 未实现）。2026-07-31 commit ``d461e40`` `feat(rest-schemaless-write):
§6.4.2 full fix` 落地后，`mode: schemaless` 实际走
``src/jmx_skeleton_generator/generators/skeleton.py`` 的 REST/InfluxDB
Line 分支（_is_schemaless 检测后调 generate_rest_write_thread_groups），
**不再经过 strategy 层**。

本文件仍保留仅为防御性目的：
1. ``register_strategy("schemaless", SchemalessWriteStrategy)`` 注册
   （src/write_strategies/registry.py:78）保证未来回退 strategy 架构时
   不抛 KeyError。
2. ``get_sampler_script`` 抛 ``NotImplementedError`` 防止意外误用 — 如
   未来有人直接 ``get_strategy("schemaless")`` 拿到本类并尝试渲染
   sampler，会立即失败而非生成错误 JMX。

如需彻底清理：另起 DCR 删本文件 + 删 registry.py:78 + 删
config_parser/models.py:309 Literal 项 + 改主 spec §7。参见
docs/specs/kwdb-svt-test-plan-generator-spec.md §7 完整讨论。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from write_strategies.base import WriteStrategy
from write_strategies.models import ResolvedTable, WriteRuntime


class SchemalessWriteStrategy(WriteStrategy):
    """``mode="schemaless"`` — DEAD CODE since d461e40 (2026-07-31).

    本 strategy 不再被实际生成器调用。``mode: schemaless`` 走
    ``skeleton.py`` REST/InfluxDB Line 分支。详见 module docstring。
    """

    @property
    def mode_name(self) -> str:
        return "schemaless"

    def requires_prepared_insert_template(self) -> bool:
        return False

    def generate_query(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
        insert_template: Optional[str] = None,
    ) -> str:
        return ""

    def get_sampler_type(self) -> str:
        return "JSR223Sampler"

    def get_sampler_config(self) -> Dict[str, Any]:
        return {"scriptLanguage": "groovy"}

    def requires_param_setup(self) -> bool:
        return False

    def get_preprocessor_code(
        self,
        table: ResolvedTable,
        batch_lines: int,
        runtime: WriteRuntime,
    ) -> Optional[str]:
        return None

    def get_sampler_script(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
    ) -> Optional[str]:
        raise NotImplementedError(
            "Schemaless write strategy is not yet implemented (T2)"
        )
