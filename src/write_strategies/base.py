"""WriteStrategy abstract base class.

Design: openspec/changes/write-strategies/design.md
Spec:    openspec/changes/write-strategies/specs/write-strategies/spec.md

Defines the contract every write strategy implements. Concrete strategies
are organized by write mode (``single_insert``, ``batch_insert``,
``single_prepared``, ``batch_prepared``, ``schemaless``) and registered
through :mod:`write_strategies.registry`.

Public surface
--------------

- :class:`WriteStrategy` — abstract base. Subclasses must implement the
  eight interface methods; the ``get_config`` helper is provided.
- :class:`WriteStrategyError` — raised when a strategy receives invalid
  inputs or cannot complete generation.

The base class keeps no instance state. Strategies are intentionally
stateless so :func:`write_strategies.registry.get_strategy` can hand out
fresh instances per call without coordinating global singletons.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from write_strategies.models import ResolvedTable, WriteRuntime


class WriteStrategyError(Exception):
    """Raised when a write strategy cannot produce a valid artifact."""


class WriteStrategy(ABC):
    """Abstract base for all write strategies.

    Subclasses describe one ``mode`` value, one JMeter sampler flavor
    (``JDBCSampler`` or ``JSR223Sampler``), and how to render the SQL /
    PreProcessor / sampler-script pieces that the JMX skeleton consumes.

    Strategies are stateless: every call reads inputs and returns
    outputs. Concurrency note — because there is no mutable state,
    sharing one instance across threads is safe.
    """

    # ---- metadata ----------------------------------------------------

    @property
    @abstractmethod
    def mode_name(self) -> str:
        """Return the write mode identifier (e.g. ``"single_insert"``)."""

    @abstractmethod
    def requires_prepared_insert_template(self) -> bool:
        """Return ``True`` when the strategy needs a Prepared Insert template.

        Single-row and batch direct INSERT strategies (``usePrepared`` =
        ``False``) do not need a template; the prepared variants do.
        """

    # ---- SQL / sampler config ---------------------------------------

    @abstractmethod
    def generate_query(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
        insert_template: Optional[str] = None,
    ) -> str:
        """Render the SQL the sampler feeds to the JDBC driver.

        Parameters
        ----------
        table:
            Structural view of the target table.
        batch_lines:
            Rows per sampler execution (``1`` for single-row modes).
        insert_template:
            Prepared INSERT template supplied by the caller for prepared
            modes; ``None`` for direct-INSERT modes that build their own
            SQL. Strategies that defer SQL to the sampler script (e.g.
            ``schemaless``) return an empty string here.
        """

    @abstractmethod
    def get_sampler_type(self) -> str:
        """Return the JMeter sampler tag, e.g. ``"JDBCSampler"`` / ``"JSR223Sampler"``."""

    @abstractmethod
    def get_sampler_config(self) -> Dict[str, Any]:
        """Return the sampler-specific config dict (e.g. ``usePrepared``).

        Returned dicts are read-only inputs to the JMX builder; missing
        keys fall back via :meth:`get_config`.
        """

    # ---- preamble wiring --------------------------------------------

    @abstractmethod
    def requires_param_setup(self) -> bool:
        """Return ``True`` when a JSR223PreProcessor must populate params first."""

    @abstractmethod
    def get_preprocessor_code(
        self,
        table: ResolvedTable,
        batch_lines: int,
        runtime: WriteRuntime,
    ) -> Optional[str]:
        """Return Groovy for a JSR223PreProcessor, or ``None`` when unused.

        Parameters
        ----------
        table:
            Structural view of the target table.
        batch_lines:
            Rows the PreProcessor must stage per sampler execution.
        runtime:
            Device-numbering / timestamp knobs for the workload.
        """

    @abstractmethod
    def get_sampler_script(
        self,
        table: ResolvedTable,
        batch_lines: int = 1,
    ) -> Optional[str]:
        """Return Groovy for a JSR223Sampler's body, or ``None``.

        Only ``JSR223Sampler``-flavored strategies supply a value;
        ``JDBCSampler`` strategies return ``None``.
        """

    # ---- shared helpers ---------------------------------------------

    def get_config(self, key: str, default: Any = None) -> Any:
        """Look up ``key`` in :meth:`get_sampler_config` with a default.

        Closes review.md Boundary §1 — callers never ``KeyError`` on a
        missing sampler-config entry. Empty / wrong-type configs are
        tolerated by returning ``default``.
        """
        config = self.get_sampler_config()
        if not isinstance(config, dict):
            return default
        return config.get(key, default)
