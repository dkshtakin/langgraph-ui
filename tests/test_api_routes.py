"""Tests for the FastAPI router endpoints.

Covers:
- GET /api/graphs — returns registered graph list
- POST /api/sessions — creates a session, returns session_id + thread_id
- POST /api/messages/{session_id} — sends a message, handles not-found
- Error cases: 404 for unknown session
"""

from __future__ import annotations

from typing import TypedDict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.api.routes import create_router


# ---------------------------------------------------------------------------
# Minimal test graph — mirrors the book_planner interrupt behaviour.
# ---------------------------------------------------------------------------


class _MsgState(TypedDict):
    messages: list
    stage: str


def _interrupt_node(state: _MsgState) -> dict:
    if state["stage"] == "dialog":
        interrupt({"reason": "waiting"})
    return {"messages": [], "stage": "next"}


def _finish_node(state: _MsgState) -> dict:
    return {"messages": [], "stage": "done"}


_test_builder = StateGraph(_MsgState)
_test_builder.add_node("interrupt", _interrupt_node)
_test_builder.add_node("finish", _finish_node)
_test_builder.add_edge(START, "interrupt")
_test_builder.add_edge("interrupt", "finish")

_test_graph = _test_builder.compile()

_TEST_GRAPH_ID = "test_api_graph"


@pytest.fixture(scope="module")
def client():
    """Return a TestClient with the router and test graph pre-loaded."""
    from backend import GRAPH_REGISTRY

    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph

    app = FastAPI()
    app.include_router(create_router())
    test_client = TestClient(app)

    yield test_client

    GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)


# ---------------------------------------------------------------------------
# GET /api/graphs
# ---------------------------------------------------------------------------


def test_get_graphs_returns_dict(client):
    """GET /api/graphs returns a dict with a 'graphs' key."""
    resp = client.get("/api/graphs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "graphs" in data


def test_get_graphs_has_name_per_entry(graphs):
    """Each entry in graphs[id] is a dict with a 'name' key."""
    for meta in graphs.values():
        assert isinstance(meta, dict)
        assert "name" in meta


def test_get_graphs_contains_registered(graphs):
    """The graphs dict includes at least book_planner."""
    assert "book_planner" in graphs
    assert graphs["book_planner"]["name"] == "Book Planner"


# ---------------------------------------------------------------------------
# POST /api/sessions
# ---------------------------------------------------------------------------


def test_post_sessions_creates_session(client):
    """POST /api/sessions returns session_id, thread_id, graph_id, and graph_name."""
    resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "thread_id" in data
    assert "graph_id" in data
    assert "graph_name" in data


def test_post_sessions_default_graph(client):
    """POST /api/sessions defaults to 'book_planner' and includes graph_name."""
    resp = client.post("/api/sessions", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["graph_id"] == "book_planner"
    assert data["graph_name"] == "Book Planner"


# ---------------------------------------------------------------------------
# POST /api/messages/{session_id}
# ---------------------------------------------------------------------------


def test_post_messages_404_on_unknown_session(client):
    """POST /api/messages returns 404 for an unknown session."""
    resp = client.post("/api/messages/nonexistent", json={"messages": [], "stage": "dialog"})
    assert resp.status_code == 404


def test_post_messages_interrupt_signal(client):
    """POST /api/messages yields an interrupt event for a paused graph."""
    # Create a session.
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    session_id = session_resp.json()["session_id"]

    # Send a message — the graph should pause.
    resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert resp.status_code == 200
    # Read SSE events.
    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events), "Should emit an interrupt event"


def test_integration_session_lifecycle(client):
    """End-to-end flow: create session → send message (pause) → resume → result."""
    from langgraph.types import Command

    # 1. Create a session.
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    # 2. Send a message — graph should pause at interrupt (stage=dialog).
    resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert resp.status_code == 200
    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events), "Graph should pause at interrupt"

    # 3. Resume with Command — graph should complete (stage=next → finish node).
    # The session manager is a singleton, so we can call resume() directly here.
    from backend.session_manager import SessionManager

    mgr = SessionManager()
    result = mgr.resume(thread_id, Command(resume="user reply"))
    assert "__interrupt__" not in result, "After resume graph should not be interrupted"


@pytest.fixture
def graphs(client):
    """Return the list of registered graphs."""
    resp = client.get("/api/graphs")
    return resp.json()["graphs"]
