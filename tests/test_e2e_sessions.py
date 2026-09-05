"""E2E tests for the test_flow graph with interrupt/resume lifecycle.

Covers the full session flow via the API:
- Create a session for ``test_flow``
- POST messages → graph pauses at ``pause`` node (interrupt)
- Resume with ``Command(resume=...)`` → fake_llm_node runs, returns ``{"ok": "message received", "result": "ok"}``
- Verify SSE events contain the expected interrupt and result events
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from backend.api.routes import create_router


_TEST_GRAPH_ID = "test_flow"


@pytest.fixture(scope="module")
def client():
    """Return a TestClient with the router and test_flow graph pre-loaded."""
    app = FastAPI()
    app.include_router(create_router())
    return TestClient(app)


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------


def test_create_test_flow_session(client):
    """POST /api/sessions for test_flow returns session_id, thread_id, graph_id, graph_name."""
    resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert resp.status_code == 200
    data = resp.json()
    assert data["graph_id"] == _TEST_GRAPH_ID
    assert data["graph_name"] == "Test Flow"
    assert data["session_id"]
    assert data["thread_id"]


# ---------------------------------------------------------------------------
# Interrupt (pause) via POST /api/messages
# ---------------------------------------------------------------------------


def test_post_messages_raises_404_for_unknown_session(client):
    """POST /api/messages returns 404 for a non-existent session."""
    resp = client.post("/api/messages/nonexistent", json={"messages": [], "stage": "dialog"})
    assert resp.status_code == 404


def test_post_messages_pause_emits_interrupt_event(client):
    """Sending a message to test_flow when stage==dialog emits an interrupt SSE event."""
    # 1. Create session.
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # 2. Send initial message — graph should pause at the interrupt node.
    resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert resp.status_code == 200

    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events), "Expected an interrupt SSE event"


# ---------------------------------------------------------------------------
# Resume → fake_llm response
# ---------------------------------------------------------------------------


def test_resume_emits_result_event(client):
    """After resume with Command, the fake_llm_node runs and emits a result SSE event."""
    from langgraph.types import Command
    from backend.session_manager import SessionManager

    # 1. Create session.
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    # 2. Pause the graph via the API.
    resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert resp.status_code == 200
    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events)

    # 3. Resume — graph completes and fake_llm returns {"result": "ok"}.
    mgr = SessionManager()
    result = mgr.resume(thread_id, Command(resume="user reply"))

    assert "__interrupt__" not in result
    assert result["result"] == "ok", f"Expected result='ok', got {result}"
    last_msg = result["messages"][-1]
    assert isinstance(last_msg, AIMessage), "fake_llm should return an AIMessage"
    assert last_msg.content == "message received", "fake_llm content must match spec"


# ---------------------------------------------------------------------------
# Integration: full lifecycle via API + direct resume
# ---------------------------------------------------------------------------


def test_full_lifecycle_create_pause_resume(client):
    """End-to-end: create session → POST (pause) → resume → assert fake_llm response."""
    from langgraph.types import Command

    # 1. Create session.
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    # 2. POST message — graph pauses at interrupt.
    pause_resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert pause_resp.status_code == 200
    lines = pause_resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events)

    # 3. Resume — graph completes and fake_llm returns the spec response.
    from backend.session_manager import SessionManager

    mgr = SessionManager()
    resume_result = mgr.resume(thread_id, Command(resume="user reply"))
    assert "__interrupt__" not in resume_result
    assert resume_result["result"] == "ok"
    last_msg = resume_result["messages"][-1]
    assert isinstance(last_msg, AIMessage), "fake_llm should return an AIMessage"
    assert last_msg.content == "message received", "fake_llm content must match spec"


# ---------------------------------------------------------------------------
# Cleanup: delete session removes state
# ---------------------------------------------------------------------------


def test_delete_session_after_resume(client):
    """Deleting a session after resume removes its checkpoint data."""
    from langgraph.types import Command
    from backend.session_manager import SessionManager

    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    mgr = SessionManager()

    # Pause then resume.
    client.post(f"/api/messages/{session_id}", json={"messages": [], "stage": "dialog"})
    mgr.resume(thread_id, Command(resume="reply"))

    # Delete and verify it's gone.
    mgr.delete_session(session_id)
    assert mgr.get_session(session_id) is None
