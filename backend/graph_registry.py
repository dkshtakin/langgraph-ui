"""Graph registry — auto-discovers graphs from tier folders.

A graph is a folder inside a tier (``backend/graphs/examples`` or
``backend/graphs/user``) containing a module named after the folder::

    backend/graphs/<tier>/<name>/<name>.py

That module is the graph's only entry point; it must export ``build()`` and may
export ``name`` (a human-readable label for the dropdown — the folder name is
the fallback).  The graph's ``id`` *is* the folder name; nothing else declares
it.  Other modules next to it (``nodes.py``, ``helpers.py``) are ordinary
imports, and sub-folders are assets, not graphs.

Discovery runs at import time, and again on demand via ``reload_graphs()``.
Anything broken is logged and the folder is skipped — a bad graph never stops
the server from starting.

Public API:
    - ``get_graph(graph_id)`` → compiled graph
    - ``list_graphs()`` → dict of {id: {"name": str}}
    - ``get_graph_name(graph_id)`` → graph display name
    - ``reload_graphs()`` → rescan disk and swap the registry in place
    - ``GRAPH_REGISTRY`` → dict of all registered graphs
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import pathlib
import sys
import traceback
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Tier folders, scanned in this order — earlier tiers win id collisions.
# Adding a tier is a deliberate one-line change here, not an oversight.
TIERS = ("examples", "user")

_GRAPHS_DIR = pathlib.Path(__file__).parent / "graphs"


def _generate_mermaid_png(compiled: Any, graph_id: str, graph_dir: pathlib.Path) -> None:
    """Generate a Mermaid PNG visualization next to the graph's entry point.

    The image is saved inside the graph folder as ``<graph_id>.mermaid.png``.
    Errors are logged but never raised — graph compilation must not fail.
    """
    output_path = graph_dir / f"{graph_id}.mermaid.png"

    try:
        graph = compiled.get_graph(xray=True)
        graph.draw_mermaid_png(output_file_path=str(output_path))
        logger.info("Generated mermaid PNG for %s → %s", graph_id, output_path)
    except Exception as exc:
        logger.warning("Failed to generate mermaid PNG for %s: %s", graph_id, exc)


def _load_graph(
    tier: str, graph_dir: pathlib.Path
) -> tuple[tuple[str, Any, str] | None, str | None]:
    """Import one graph folder and compile it.

    Returns
    tuple
        ``(loaded, error)``.  On success *loaded* is
        ``(graph_id, compiled, display_name)`` and *error* is ``None``; on
        failure *loaded* is ``None`` and *error* is a one-line
        ``"<ExcType>: <message>"`` summary.  The full traceback goes to the log
        either way — *error* is what callers may hand back to a client.
    """
    graph_id = graph_dir.name
    module_name = f"backend.graphs.{tier}.{graph_id}.{graph_id}"

    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:
        logger.error(
            "Failed to import graph %r from %s:\n%s",
            graph_id, module_name, traceback.format_exc(),
        )
        return None, f"{type(exc).__name__}: {exc}"

    build = getattr(mod, "build", None)
    if build is None:
        # The module path belongs in the log, not in a client-facing message.
        logger.error("Graph %r (%s) does not export build()", graph_id, module_name)
        return None, "does not export build()"

    try:
        compiled = build()
    except Exception as exc:
        logger.error(
            "Failed to build graph %r (%s):\n%s",
            graph_id, module_name, traceback.format_exc(),
        )
        return None, f"{type(exc).__name__}: {exc}"

    _generate_mermaid_png(compiled, graph_id, graph_dir)
    return (graph_id, compiled, getattr(mod, "name", None) or graph_id), None


def _discover() -> tuple[Dict[str, Any], Dict[str, str], list[Dict[str, str]]]:
    """Walk every tier folder and register each graph folder found.

    Returns
    tuple
        (registry, names, errors) where ``names`` maps id → display name and
        ``errors`` holds ``{"graph_id": ..., "error": ...}`` for every graph
        folder that failed to load.
    """
    registry: Dict[str, Any] = {}
    names: Dict[str, str] = {}
    errors: list[Dict[str, str]] = []

    for tier in TIERS:
        tier_dir = _GRAPHS_DIR / tier
        if not tier_dir.is_dir():
            continue  # a tier that is absent from disk is not an error

        for graph_dir in sorted(tier_dir.iterdir()):
            # Skip tier-root modules and Python's own directories — only
            # sub-folders are graph candidates.
            if not graph_dir.is_dir() or graph_dir.name.startswith((".", "__")):
                continue

            if not (graph_dir / f"{graph_dir.name}.py").is_file():
                logger.warning(
                    "Skipping %s/%s — a graph folder must contain %s.py.",
                    tier, graph_dir.name, graph_dir.name,
                )
                continue

            loaded, error = _load_graph(tier, graph_dir)
            if loaded is None:
                errors.append({"graph_id": graph_dir.name, "error": error or "unknown error"})
                continue
            graph_id, compiled, display_name = loaded

            if graph_id in registry:
                logger.error(
                    "Duplicate graph id %r in tier %r — keeping the one loaded "
                    "first (tiers are scanned in order: %s).",
                    graph_id, tier, ", ".join(TIERS),
                )
                continue

            registry[graph_id] = compiled
            names[graph_id] = display_name

    return registry, names, errors


GRAPH_REGISTRY, _GRAPH_NAMES, _ = _discover()


# Serialises rebuilds: two clicks must not interleave their purge-and-swap.
_RELOAD_LOCK = asyncio.Lock()


def _rebuild_registry() -> tuple[Dict[str, Any], Dict[str, str], list[Dict[str, str]]]:
    """Drop cached graph modules and rediscover every tier from disk.

    ``importlib.import_module()`` returns the cached module and never looks at
    the filesystem, so a stale entry means edits on disk stay invisible —
    including edits to shared modules such as ``examples/common.py``.  Only
    ``backend.graphs.*`` is purged; the ``backend.graphs`` package itself is
    left alone.
    """
    for name in [n for n in sys.modules if n.startswith("backend.graphs.")]:
        del sys.modules[name]
    return _discover()


async def reload_graphs(graph_id: str | None = None) -> list[Dict[str, str]]:
    """Rebuild the registry from disk and swap it in place, without restarting.

    The rebuild is synchronous and its Mermaid PNG generation goes out to the
    network, so it runs in a worker thread; only the swap back into
    ``GRAPH_REGISTRY`` happens on the event loop.  Sessions already holding a
    compiled graph are untouched — they keep running the code they started
    with, and a stream in flight is not interrupted.

    Returns
    list of dict
        One ``{"graph_id": ..., "error": ...}`` entry per graph that failed to
        load; empty when everything rebuilt.  Failed graphs are *absent* from
        the registry rather than silently kept at their last good version.

    Note:
        *graph_id* is reserved for a future single-graph rebuild and is
        currently ignored — every tier is always rescanned.
    """
    global _GRAPH_NAMES

    async with _RELOAD_LOCK:
        registry, names, errors = await asyncio.to_thread(_rebuild_registry)

        # ``routes`` and ``session_manager`` hold a direct reference to this
        # dict, so all the swap may do is mutate it.
        GRAPH_REGISTRY.clear()
        GRAPH_REGISTRY.update(registry)
        _GRAPH_NAMES = names

        return errors


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
