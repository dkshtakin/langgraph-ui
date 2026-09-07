"""Tests for the FastAPI router endpoints.

Covers:
- GET /api/graphs — returns registered graph list
- POST /api/sessions — creates a session, returns session_id + thread_id
- POST /api/resume/{session_id} — sends a user message, handles not-found, interrupts
- DELETE /api/sessions/{session_id} — deletes a session, handles not-found
- Error cases: 404 for unknown session
"""

from __future__ import annotations

from typing_extensions import TypedDict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.api.routes import create_router
from tests._sse_helpers import parse_sse_events


# ---------------------------------------------------------------------------
# Minimal test graph — mirrors the book_planner interrupt behaviour.
# ---------------------------------------------------------------------------


class _MsgState(TypedDict):
    messages: list
    stage: str


def _interrupt_node(state: _MsgState) -> dict:
    if state.get("stage", "dialog") == "dialog":
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
# POST /api/resume/{session_id}
# ---------------------------------------------------------------------------


def test_post_resume_404_on_unknown_session(client):
    """POST /api/resume returns 404 for an unknown session."""
    resp = client.post("/api/resume/nonexistent", json={"text": "hello"})
    assert resp.status_code == 404


def test_post_resume_interrupt_signal(client):
    """POST /api/resume yields an interrupt event for a paused graph."""
    # Create a session.
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    session_id = session_resp.json()["session_id"]

    # Send a message — the graph should pause.
    resp = client.post(
        f"/api/resume/{session_id}",
        json={"text": "hello"},
    )
    assert resp.status_code == 200
    # Read SSE events.
    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events), "Should emit an interrupt event"


def test_integration_session_lifecycle(client):
    """End-to-end flow: create session → resume (pause) → resume → done via API only."""
    # 1. Create a session.
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # 2. First resume — graph should pause at interrupt (stage=dialog).
    resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    event_types = [e["event"] for e in events]
    assert "interrupt" in event_types, "Graph should pause at interrupt"

    # 3. Second resume — graph completes (stage=next → finish node).
    resp = client.post(f"/api/resume/{session_id}", json={"text": "user reply"})
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1, "Should emit exactly one done event"


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{session_id}
# ---------------------------------------------------------------------------


def test_delete_session_404_on_unknown_session(client):
    """DELETE /api/sessions returns 404 for an unknown session."""
    resp = client.delete("/api/sessions/nonexistent")
    assert resp.status_code == 404


def test_delete_session_succeeds(client):
    """DELETE /api/sessions removes the session and returns deleted=True."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    delete_resp = client.delete(f"/api/sessions/{session_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    from backend.session_manager import SessionManager

    mgr = SessionManager()
    assert mgr.get_session(session_id) is None


@pytest.fixture
def graphs(client):
    """Return the list of registered graphs."""
    resp = client.get("/api/graphs")
    return resp.json()["graphs"]
