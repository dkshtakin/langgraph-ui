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
    # Return empty dict so the add_messages reducer preserves existing messages.
    return {"stage": "next"}


def _finish_node(state: _MsgState) -> dict:
    return {"stage": "done"}


_test_builder = StateGraph(_MsgState)
_test_builder.add_node("interrupt", _interrupt_node)
_test_builder.add_node("finish", _finish_node)
_test_builder.add_edge(START, "interrupt")
_test_builder.add_edge("interrupt", "finish")

_test_graph = _test_builder.compile()

_TEST_GRAPH_ID = "test_api_graph"


# Module-level holder for the shared SessionManager so tests can reach in.
_shared_mgr = None  # type: ignore[assignment]


@pytest.fixture(scope="module")
def client():
    """Return a TestClient with the router and test graph pre-loaded."""
    global _shared_mgr

    from backend import GRAPH_REGISTRY
    from backend.session_manager import SessionManager

    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph

    # Shared manager: both the router and test functions use the same instance
    # so checkpoint state is visible from both sides.
    _shared_mgr = SessionManager()
    app = FastAPI()
    app.include_router(create_router(session_manager_factory=_shared_mgr))
    test_client = TestClient(app)

    yield test_client

    GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)


@pytest.fixture(scope="module")
def shared_session_manager():
    """Return the SessionManager instance shared with the test client's router."""
    return _shared_mgr


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


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}/messages
# ---------------------------------------------------------------------------


def test_get_session_messages_404_on_unknown_session(client):
    """GET /api/sessions/{id}/messages returns 404 for an unknown session."""
    resp = client.get("/api/sessions/nonexistent/messages")
    assert resp.status_code == 404


def test_get_session_messages_completed_session(client):
    """Completed session returns normalised messages from the latest checkpoint."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # First resume — graph pauses at interrupt (empty input for fresh session).
    resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert resp.status_code == 200

    # Second resume — injects user message, graph completes.
    resp = client.post(f"/api/resume/{session_id}", json={"text": "reply"})
    assert resp.status_code == 200

    # Load messages via the new endpoint.
    msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
    assert msgs_resp.status_code == 200
    data = msgs_resp.json()
    assert "messages" in data
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) >= 1, "Should contain the user message from second resume"


def test_get_session_messages_interrupted_session(client):
    """Interrupted session returns a valid message list from its checkpoint."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # First resume — graph pauses at interrupt (empty input for fresh session).
    resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert resp.status_code == 200

    # Load messages without resuming further.
    msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
    assert msgs_resp.status_code == 200
    data = msgs_resp.json()
    assert "messages" in data
    assert isinstance(data["messages"], list)


def test_get_session_messages_includes_system_message(client, shared_session_manager):
    """SystemMessage appears in the response with role 'system'."""
    from backend import GRAPH_REGISTRY
    from langchain.messages import SystemMessage
    from langchain_core.messages import HumanMessage

    class _SysState(TypedDict):
        messages: list
        stage: str

    def _sys_interrupt_node(state: _SysState) -> dict:
        if state.get("stage", "dialog") == "dialog":
            interrupt({"reason": "waiting"})
        return {"stage": "next"}

    def _sys_finish_node(state: _SysState) -> dict:
        return {"stage": "done"}

    sys_builder = StateGraph(_SysState)
    sys_builder.add_node("interrupt", _sys_interrupt_node)
    sys_builder.add_node("finish", _sys_finish_node)
    sys_builder.add_edge(START, "interrupt")
    sys_builder.add_edge("interrupt", "finish")
    sys_graph = sys_builder.compile()

    SYS_GRAPH_ID = "test_sys_graph"
    GRAPH_REGISTRY[SYS_GRAPH_ID] = sys_graph

    try:
        resp = client.post("/api/sessions", json={"graph_id": SYS_GRAPH_ID})
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]
        thread_id = resp.json()["thread_id"]

        # Use the shared manager's compiled graph (which has the checkpointer).
        session = shared_session_manager.get_session(session_id)
        assert session is not None
        session_graph = session["graph"]
        session_graph.invoke(
            {
                "messages": [SystemMessage(content="You are helpful"), HumanMessage(content="hi")],
                "stage": "dialog",
            },
            config={"configurable": {"thread_id": thread_id}},
        )

        msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
        assert msgs_resp.status_code == 200
        data = msgs_resp.json()
        roles = [m["role"] for m in data["messages"]]
        assert "system" in roles, "SystemMessage should be present with role 'system'"
    finally:
        GRAPH_REGISTRY.pop(SYS_GRAPH_ID, None)


def test_get_session_messages_serializes_tool_calls(client, shared_session_manager):
    """ToolCalls are serialised as {name, args} without truncation."""
    import asyncio

    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    # Two resumes — first pauses, second completes the graph and builds message history.
    client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    client.post(f"/api/resume/{session_id}", json={"text": "reply"})

    # Inject an AIMessage with tool_calls directly into the checkpoint.
    from langchain_core.messages import AIMessage

    session = shared_session_manager.get_session(session_id)
    assert session is not None
    graph = session["graph"]
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    async def _inject():
        latest = await graph.checkpointer.aget_tuple(config)
        if latest is not None:
            channel_values = latest.checkpoint.get("channel_values", {})
            msgs = list(channel_values.get("messages", []))
            msgs.append(
                AIMessage(
                    content="calling tool",
                    tool_calls=[{"name": "today_tool", "args": {"date": "2026-09-16"}, "id": "call_1"}],
                )
            )
            updated = {
                **latest.checkpoint,
                "channel_values": {**channel_values, "messages": msgs},
            }
            await graph.checkpointer.aput(
                config, updated, {}, latest.checkpoint.get("channel_versions", {})
            )

    asyncio.run(_inject())

    msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
    assert msgs_resp.status_code == 200
    data = msgs_resp.json()
    assistant_msgs = [m for m in data["messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
    tool_call_msg = next(m for m in assistant_msgs if m.get("toolCalls"))
    assert len(tool_call_msg["toolCalls"]) == 1
    tc = tool_call_msg["toolCalls"][0]
    assert tc["name"] == "today_tool"
    assert tc["args"] == {"date": "2026-09-16"}


@pytest.fixture
def graphs(client):
    """Return the list of registered graphs."""
    resp = client.get("/api/graphs")
    return resp.json()["graphs"]
