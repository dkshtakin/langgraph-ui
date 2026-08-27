"""Graph registry — discovers and stores compiled graphs.

Scans ``backend.graphs`` submodules for modules that export ``id``,
``name``, and ``build()``.  Call :py:meth:`register_all` to populate the
registry, then use :py:meth:`get` or :py:meth:`list`.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator
from typing import Any


class GraphRegistry:
    """Stores compiled LangGraph graphs keyed by their ``id``."""

    def __init__(self) -> None:
        self._graphs: dict[str, Any] = {}

    # ── registration ───────────────────────────────────────────────

    def register(self, graph_module: str) -> None:
        """Import *graph_module* and register its compiled graph.

        The module must export ``id``, ``name``, and ``build()`` (see
        :mod:`backend.graphs.book_planner` for an example).
        """
        mod = importlib.import_module(graph_module)
        if not hasattr(mod, "id") or not hasattr(mod, "build"):
            return  # pragma: no cover
        compiled = mod.build()
        self._graphs[mod.id] = compiled

    def register_all(self, package_name: str = "backend.graphs") -> None:
        """Auto-discover all graph modules inside *package_name*."""
        pkg = importlib.import_module(package_name)
        for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
            if ispkg:
                continue  # only register module-level graphs (not subpackages)
            self.register(modname)

    def get(self, graph_id: str) -> Any:
        """Return the compiled graph for *graph_id*."""
        if graph_id not in self._graphs:
            raise KeyError(graph_id)
        return self._graphs[graph_id]

    def list(self) -> Iterator[str]:
        """Yield all registered graph IDs."""
        yield from self._graphs


# Singleton instance — imported by the API route.
registry = GraphRegistry()
