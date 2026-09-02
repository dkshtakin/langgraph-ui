"""Backend package — auto-discovers and registers all graphs on import.

The ``_GRAPH_MODULES`` list declares every graph module. On import, this file
imports each one and populates ``GRAPH_REGISTRY`` with the compiled graphs.

Public API:
    - ``get_graph(graph_id)`` → compiled graph
    - ``list_graphs()`` → dict of {id: id}
    - ``GRAPH_REGISTRY`` → dict of all registered graphs
"""

from __future__ import annotations

from typing import Dict, Any

# Declare every graph module here — __init__.py compiles them all at startup.
_GRAPH_MODULES = [
    "backend.graphs.book_planner",
]


def _compile_registry(modules: list[str]) -> Dict[str, Any]:
    """Import each module and register its compiled graph."""
    registry: Dict[str, Any] = {}

    for mod_name in modules:
        mod = __import__(mod_name, fromlist=["id", "name", "build"])
        graph_id = getattr(mod, "id", None)
        graph_build = getattr(mod, "build", None)

        if graph_id is None or graph_build is None:
            raise ValueError(
                f"Module {mod_name!r} must export ``id`` and ``build()``"
            )

        compiled = graph_build()
        registry[graph_id] = compiled

    return registry


GRAPH_REGISTRY: Dict[str, Any] = _compile_registry(_GRAPH_MODULES)


def get_graph(graph_id: str) -> Any:
    """Retrieve a compiled graph by ID.

    Raises:
        ValueError: If the graph ID is not found in the registry.
    """
    if graph_id not in GRAPH_REGISTRY:
        available = ", ".join(GRAPH_REGISTRY.keys())
        raise ValueError(f"Unknown graph '{graph_id}'. Available: {available}")
    return GRAPH_REGISTRY[graph_id]


def list_graphs() -> list[str]:
    """Return a list of registered graph IDs for introspection."""
    return list(GRAPH_REGISTRY.keys())
