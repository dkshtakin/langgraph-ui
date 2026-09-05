"""E2E tests for the test_flow and llm_flow graphs with interrupt/resume lifecycle.

Covers the full session flow via the API:
- Create a session for ``test_flow``
- POST messages → graph pauses at ``pause`` node (interrupt)
- Resume with ``Command(resume=...)`` → fake_llm_node runs, returns ``{"ok": "message received", "result": "ok"}``
- Verify SSE events contain the expected interrupt and result events

For ``llm_flow``, the same lifecycle is tested with a real LLM model call.
"""

from __future__ import annotations

import pytest
import urllib.request
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from backend.api.routes import create_router


_TEST_GRAPH_ID = "test_flow"
_LLM_GRAPH_ID = "llm_flow"


@pytest.fixture(scope="module")
def client():
    """Return a TestClient with the router and graphs pre-loaded."""
    app = FastAPI()
    app.include_router(create_router())
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_available() -> bool:
    """Return True if the local LLM server at 127.0.0.1:8081 is reachable."""
    try:
        urllib.request.urlopen("http://127.0.0.1:8081/v1/models", timeout=3)
        return True
    except Exception:
        return False


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


def test_create_llm_flow_session(client):
    """POST /api/sessions for llm_flow returns session_id, thread_id, graph_id, graph_name."""
    resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert resp.status_code == 200
    data = resp.json()
    assert data["graph_id"] == _LLM_GRAPH_ID
    assert data["graph_name"] == "LLM Flow"
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
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert resp.status_code == 200

    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events), "Expected an interrupt SSE event"


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_post_messages_llm_flow_emits_interrupt_event(client):
    """Sending a message to llm_flow when stage==dialog emits an interrupt SSE event."""
    session_resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert resp.status_code == 200

    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events), "Expected an interrupt SSE event"


# ---------------------------------------------------------------------------
# Resume → fake_llm / real_llm response
# ---------------------------------------------------------------------------


def test_resume_emits_result_event(client):
    """After resume with Command, the fake_llm_node runs and emits a result SSE event."""
    from langgraph.types import Command
    from backend.session_manager import SessionManager

    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert resp.status_code == 200
    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events)

    mgr = SessionManager()
    result = mgr.resume(
        thread_id,
        Command(
            resume="user reply",
            update={"messages": [HumanMessage(content="user reply")]},
        ),
    )

    assert "__interrupt__" not in result
    assert result["result"] == "ok", f"Expected result='ok', got {result}"
    last_msg = result["messages"][-1]
    assert isinstance(last_msg, AIMessage), "fake_llm should return an AIMessage"
    assert last_msg.content == "message received", "fake_llm content must match spec"


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_resume_llm_flow_emits_real_llm_response(client):
    """After resume with Command, the real_llm_node runs and returns a real LLM AIMessage."""
    from langgraph.types import Command
    from backend.session_manager import SessionManager

    session_resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert resp.status_code == 200
    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events)

    mgr = SessionManager()
    result = mgr.resume(
        thread_id,
        Command(
            resume="user reply",
            update={"messages": [HumanMessage(content="user reply")]},
        ),
    )

    assert "__interrupt__" not in result
    assert result["result"] == "ok", f"Expected result='ok', got {result}"
    assert result["stage"] == "done", f"Expected stage='done', got {result}"
    last_msg = result["messages"][-1]
    assert isinstance(last_msg, AIMessage), "real_llm should return an AIMessage"
    assert last_msg.content, "real LLM response must have non-empty content"


# ---------------------------------------------------------------------------
# Integration: full lifecycle via API + direct resume
# ---------------------------------------------------------------------------


def test_full_lifecycle_create_pause_resume(client):
    """End-to-end: create session → POST (pause) → resume → assert fake_llm response."""
    from langgraph.types import Command

    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    pause_resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert pause_resp.status_code == 200
    lines = pause_resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events)

    from backend.session_manager import SessionManager

    mgr = SessionManager()
    resume_result = mgr.resume(
        thread_id,
        Command(
            resume="user reply",
            update={"messages": [HumanMessage(content="user reply")]},
        ),
    )
    assert "__interrupt__" not in resume_result
    assert resume_result["result"] == "ok"
    last_msg = resume_result["messages"][-1]
    assert isinstance(last_msg, AIMessage), "fake_llm should return an AIMessage"
    assert last_msg.content == "message received", "fake_llm content must match spec"


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_full_lifecycle_llm_flow(client):
    """End-to-end: create session → POST (pause) → resume → assert real LLM response."""
    from langgraph.types import Command

    session_resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    pause_resp = client.post(
        f"/api/messages/{session_id}",
        json={"messages": [], "stage": "dialog"},
    )
    assert pause_resp.status_code == 200
    lines = pause_resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events)

    from backend.session_manager import SessionManager

    mgr = SessionManager()
    resume_result = mgr.resume(
        thread_id,
        Command(
            resume="user reply",
            update={"messages": [HumanMessage(content="user reply")]},
        ),
    )
    assert "__interrupt__" not in resume_result
    assert resume_result["result"] == "ok"
    assert resume_result["stage"] == "done"
    last_msg = resume_result["messages"][-1]
    assert isinstance(last_msg, AIMessage), "real_llm should return an AIMessage"
    assert last_msg.content, "real LLM response must have non-empty content"


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

    client.post(f"/api/messages/{session_id}", json={"messages": [], "stage": "dialog"})
    mgr.resume(
        thread_id,
        Command(
            resume="reply",
            update={"messages": [HumanMessage(content="reply")]},
        ),
    )

    mgr.delete_session(session_id)
    assert mgr.get_session(session_id) is None


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_delete_llm_flow_session_after_resume(client):
    """Deleting a session after resume removes its checkpoint data."""
    from langgraph.types import Command
    from backend.session_manager import SessionManager

    session_resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    thread_id = session_resp.json()["thread_id"]

    mgr = SessionManager()

    client.post(f"/api/messages/{session_id}", json={"messages": [], "stage": "dialog"})
    mgr.resume(
        thread_id,
        Command(
            resume="reply",
            update={"messages": [HumanMessage(content="reply")]},
        ),
    )

    mgr.delete_session(session_id)
    assert mgr.get_session(session_id) is None
