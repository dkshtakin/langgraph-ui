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
# GET /api/sessions
# ---------------------------------------------------------------------------


def test_get_sessions_returns_list(client):
    """GET /api/sessions returns a dict with a 'sessions' list."""
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


def test_get_sessions_fields(client):
    """GET /api/sessions returns rows with all required metadata fields."""
    # Create a session so we have something to inspect.
    create_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert create_resp.status_code == 200
    sid = create_resp.json()["session_id"]

    resp = client.get("/api/sessions")
    data = resp.json()
    row = next(r for r in data["sessions"] if r["session_id"] == sid)
    required = {"session_id", "thread_id", "graph_id", "graph_name", "title",
                "status", "created_at", "updated_at"}
    assert required.issubset(row.keys()), f"Missing fields: {required - row.keys()}"


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


def test_resume_emits_tool_call_event(client, monkeypatch):
    """POST /api/resume emits a tool_call SSE event when the graph produces one."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    async def _empty_alist():
        """Return an empty async generator — mirrors InMemorySaver.alist() for mock checkpointer."""
        return
        yield  # turn this into an async generator function

    # Fake async event stream that yields a content-block-finish with tool_call.
    # Must return a coroutine (not an async generator) so `await graph.astream_events()` works.
    async def _make_fake_iter(events):
        class FakeAsyncIter:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise StopAsyncIteration
        for evt in events:
            yield evt
        raise StopAsyncIteration

    async def fake_astream_events(*args, **kwargs):
        events = [
            {
                "method": "messages",
                "params": {
                    "data": [
                        {
                            "event": "content-block-finish",
                            "content": {
                                "type": "tool_call",
                                "name": "today_tool",
                                "args": {"date": "2026-09-08"},
                            },
                        }
                    ]
                },
            },
        ]
        return _make_fake_iter(events)

    from backend.session_manager import SessionManager
    mock_graph = type("MockGraph", (), {
        "checkpointer": type("Checkpointer", (), {
            "list": lambda self, c: [],
            "alist": lambda self, c: _empty_alist(),  # async generator mock
        })(),
        "astream_events": fake_astream_events,
    })()

    # Patch the method on the class so the route's fresh instance picks it up.
    original_get_session = SessionManager.get_session
    def patched_get_session(self, sid):
        sess = original_get_session(self, sid)
        if sid == session_id:
            sess["graph"] = mock_graph
        return sess
    monkeypatch.setattr(SessionManager, "get_session", patched_get_session)

    resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert resp.status_code == 200

    events = parse_sse_events(resp.text)
    tool_call_events = [e for e in events if e["event"] == "tool_call"]
    assert len(tool_call_events) == 1, "Should emit exactly one tool_call event"
    tc = tool_call_events[0]["data"]
    assert tc["name"] == "today_tool"
    assert tc["args"] == '{"date": "2026-09-08"}'


# ---------------------------------------------------------------------------
# PATCH /api/sessions/{session_id} — rename
# ---------------------------------------------------------------------------


def test_patch_rename_session_404_on_unknown(client):
    """PATCH /api/sessions returns 404 for an unknown session."""
    resp = client.patch("/api/sessions/nonexistent", json={"title": "New Title"})
    assert resp.status_code == 404


def test_patch_rename_session_succeeds(client):
    """PATCH /api/sessions/{id} updates title and returns the full object."""
    create_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert create_resp.status_code == 200
    sid = create_resp.json()["session_id"]

    resp = client.patch(f"/api/sessions/{sid}", json={"title": "My Custom Title"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "My Custom Title"
    assert data["session_id"] == sid
    required = {"session_id", "thread_id", "graph_id", "graph_name",
                "title", "status", "created_at", "updated_at"}
    assert required.issubset(data.keys())


def test_patch_rename_session_updates_created_and_updated(client):
    """PATCH /api/sessions updates updated_at after rename."""
    create_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert create_resp.status_code == 200
    sid = create_resp.json()["session_id"]

    # The created session should have updated_at == created_at initially.
    get_before = client.get("/api/sessions").json()["sessions"]
    before_row = next(r for r in get_before if r["session_id"] == sid)
    before_updated = before_row["updated_at"]
    assert before_updated == before_row["created_at"]

    import time as _time

    _time.sleep(0.05)  # small gap to detect updated_at change

    rename_resp = client.patch(f"/api/sessions/{sid}", json={"title": "Updated"})
    assert rename_resp.status_code == 200
    after_data = rename_resp.json()
    assert after_data["updated_at"] > before_updated, "updated_at must increase after rename"


@pytest.fixture
def graphs(client):
    """Return the list of registered graphs."""
    resp = client.get("/api/graphs")
    return resp.json()["graphs"]
