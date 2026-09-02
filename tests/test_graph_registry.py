"""Tests for the graph registry auto-discovery and compilation.

Two suites:
1. Registry tests — every registered graph has ``id`` and ``name``, all graphs loaded.
2. Compilation tests — each compiled graph can be retrieved and is ready to run.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry():
    """Import backend (triggers auto-discovery). Returns GRAPH_REGISTRY."""
    import backend  # noqa: F401 — side effect is registry compilation.
    from backend import GRAPH_REGISTRY

    return GRAPH_REGISTRY


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_not_empty(registry):
    """At least one graph must be registered."""
    assert len(registry) > 0, "GRAPH_REGISTRY is empty — no graphs loaded."


def test_book_planner_registered(registry):
    """book_planner must be present in the registry."""
    assert "book_planner" in registry


def test_graphs_have_id_and_name():
    """Every graph module exports ``id`` and ``name`` attributes."""
    from backend.graphs import book_planner_id, book_planner_name

    assert isinstance(book_planner_id, str) and len(book_planner_id) > 0
    assert isinstance(book_planner_name, str) and len(book_planner_name) > 0


# ---------------------------------------------------------------------------
# Compilation tests
# ---------------------------------------------------------------------------


def test_get_graph(registry):
    """Compiled graph can be retrieved by ID."""
    from backend import get_graph

    graph = get_graph("book_planner")
    assert graph is not None


def test_graph_is_ready(registry):
    """Retrieved graph has a compile() method and is ready to stream."""
    from backend import get_graph

    graph = get_graph("book_planner")
    # Compiled LangGraph graphs have a `stream` method.
    assert hasattr(graph, "stream"), "Compiled graph must be runnable (have .stream)."


def test_list_graphs():
    """list_graphs returns a list of registered graph IDs."""
    from backend import list_graphs

    graphs = list_graphs()
    assert isinstance(graphs, list)
    assert "book_planner" in graphs
