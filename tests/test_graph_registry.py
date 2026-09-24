"""Tests for the graph registry auto-discovery and compilation.

Two suites:
1. Registry tests — every graph folder in ``examples/`` is discovered under its
   folder name, and every registered graph carries a display name.
2. Compilation tests — each compiled graph can be retrieved and is ready to run.

The expected ids are read from the filesystem rather than hardcoded, so adding
a graph folder to ``examples/`` needs no edit here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "backend" / "graphs" / "examples"


def _example_graph_ids() -> list[str]:
    """Graph folder names in ``examples/`` — the folder name *is* the graph id."""
    return sorted(p.name for p in EXAMPLES_DIR.iterdir() if (p / f"{p.name}.py").is_file())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry():
    """Import the registry module (triggers auto-discovery). Returns GRAPH_REGISTRY."""
    from backend.graph_registry import GRAPH_REGISTRY

    return GRAPH_REGISTRY


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_not_empty(registry):
    """At least one graph must be registered."""
    assert len(registry) > 0, "GRAPH_REGISTRY is empty — no graphs loaded."


def test_examples_graphs_registered_under_folder_names(registry):
    """Every graph folder in examples/ is registered under its folder name."""
    expected = _example_graph_ids()
    assert expected, f"No graph folders found in {EXAMPLES_DIR}"

    missing = [graph_id for graph_id in expected if graph_id not in registry]
    assert not missing, f"Graphs in examples/ were not discovered: {missing}"


def test_every_registered_graph_has_a_name():
    """list_graphs() gives every graph a non-empty display name."""
    from backend.graph_registry import list_graphs

    graphs = list_graphs()
    for graph_id, meta in graphs.items():
        assert isinstance(meta, dict), f"{graph_id} metadata is not a dict"
        assert isinstance(meta.get("name"), str) and meta["name"], (
            f"{graph_id} has no display name"
        )


# ---------------------------------------------------------------------------
# Compilation tests
# ---------------------------------------------------------------------------


def test_get_graph(registry):
    """A compiled graph can be retrieved by its id."""
    from backend.graph_registry import get_graph

    graph = get_graph(_example_graph_ids()[0])
    assert graph is not None


def test_graph_is_ready(registry):
    """Retrieved graph has a stream method and is ready to run."""
    from backend.graph_registry import get_graph

    graph = get_graph(_example_graph_ids()[0])
    assert hasattr(graph, "stream"), "Compiled graph must be runnable (have .stream)."


def test_list_graphs():
    """list_graphs returns a dict mapping id to {name: ...} for every graph."""
    from backend.graph_registry import GRAPH_REGISTRY, list_graphs

    graphs = list_graphs()
    assert isinstance(graphs, dict)
    assert set(graphs) == set(GRAPH_REGISTRY)
    for meta in graphs.values():
        assert isinstance(meta, dict) and "name" in meta
