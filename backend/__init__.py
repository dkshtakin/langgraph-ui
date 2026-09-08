"""Backend package — auto-discovers and registers all graphs on import.

The ``_GRAPH_MODULES`` list declares every graph module. On import, this file
imports each one and populates ``GRAPH_REGISTRY`` with the compiled graphs.

Public API:
    - ``get_graph(graph_id)`` → compiled graph
    - ``list_graphs()`` → dict of {id: {"name": str}}
    - ``get_graph_name(graph_id)`` → graph display name
    - ``GRAPH_REGISTRY`` → dict of all registered graphs
"""

from __future__ import annotations

import inspect
import logging
import pathlib
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Declare every graph module here — __init__.py compiles them all at startup.
_GRAPH_MODULES = [
    "backend.graphs.book_planner",
    "backend.graphs.test_flow",
    "backend.graphs.llm_flow",
]


def _generate_mermaid_png(compiled: Any, mod) -> None:
    """Generate a Mermaid PNG visualization of *compiled* graph.

    The image is saved next to the source module as ``<graph_id>.mermaid.png``.
    Errors are logged but never raised — graph compilation must not fail.
    """
    graph_id = getattr(mod, "id", None)
    if graph_id is None:
        return

    try:
        source_file = inspect.getfile(mod)
    except (TypeError, OSError):
        logger.warning("Cannot determine source file for module %r; skipping PNG generation.", mod.__name__)
        return

    output_path = pathlib.Path(source_file).parent / f"{graph_id}.mermaid.png"

    try:
        graph = compiled.get_graph(xray=True)
        graph.draw_mermaid_png(output_file_path=str(output_path))
        logger.info("Generated mermaid PNG for %s → %s", graph_id, output_path)
    except Exception as exc:
        logger.warning("Failed to generate mermaid PNG for %s: %s", graph_id, exc)


def _compile_registry(modules: list[str]) -> tuple[Dict[str, Any], Dict[str, str]]:
    """Import each module and register its compiled graph.

    Returns
    -------
    tuple
        (registry, names) where ``names`` maps id → display name.
    """
    registry: Dict[str, Any] = {}
    names: Dict[str, str] = {}

    for mod_name in modules:
        mod = __import__(mod_name, fromlist=["id", "name", "build"])
        graph_id = getattr(mod, "id", None)
        graph_build = getattr(mod, "build", None)
        graph_name = getattr(mod, "name", None)

        if graph_id is None or graph_build is None:
            raise ValueError(
                f"Module {mod_name!r} must export ``id`` and ``build()``"
            )

        compiled = graph_build()
        _generate_mermaid_png(compiled, mod)
        registry[graph_id] = compiled
        if graph_name is not None:
            names[graph_id] = graph_name

    return registry, names


GRAPH_REGISTRY, _GRAPH_NAMES = _compile_registry(_GRAPH_MODULES)


def get_graph(graph_id: str) -> Any:
    """Retrieve a compiled graph by ID.

    Raises:
        ValueError: If the graph ID is not found in the registry.
    """
    if graph_id not in GRAPH_REGISTRY:
        available = ", ".join(GRAPH_REGISTRY.keys())
        raise ValueError(f"Unknown graph '{graph_id}'. Available: {available}")
    return GRAPH_REGISTRY[graph_id]


def get_graph_name(graph_id: str) -> str:
    """Return the display name for *graph_id*."""
    return _GRAPH_NAMES.get(graph_id, graph_id)


def list_graphs() -> Dict[str, Dict[str, str]]:
    """Return a dict mapping graph id → {name: display_name}.

    Iterates over ``GRAPH_REGISTRY`` so every registered graph appears,
    even if it lacks a ``name`` attribute (falls back to the id).
    """
    return {id_: {"name": get_graph_name(id_)} for id_ in GRAPH_REGISTRY}
