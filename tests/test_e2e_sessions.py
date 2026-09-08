"""E2E tests for the test_flow and llm_flow graphs with interrupt/resume lifecycle.

Covers the full session flow via the API only — no direct SessionManager calls:
- Create a session for ``test_flow``
- POST /api/resume → graph pauses at ``pause`` node (interrupt)
- POST /api/resume again → fake_llm_node runs, returns ``{"ok": "message received", "result": "ok"}``
- DELETE /api/sessions → removes session and checkpoint data

For ``llm_flow``, the same lifecycle is tested with a real LLM model call.
"""

from __future__ import annotations

import pytest
import urllib.request
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import create_router
from tests._sse_helpers import parse_sse_events


_TEST_GRAPH_ID = "test_flow"
_LLM_GRAPH_ID = "llm_flow"
_TOOL_CALL_GRAPH_ID = "tool_call_flow"


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
# Interrupt (pause) via POST /api/resume
# ---------------------------------------------------------------------------


def test_resume_raises_404_for_unknown_session(client):
    """POST /api/resume returns 404 for a non-existent session."""
    resp = client.post("/api/resume/nonexistent", json={"text": "hello"})
    assert resp.status_code == 404


def test_resume_pause_emits_interrupt_event(client):
    """Sending a message to test_flow when stage==dialog emits an interrupt SSE event."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert resp.status_code == 200

    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events), "Expected an interrupt SSE event"


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_resume_llm_flow_emits_interrupt_event(client):
    """Sending a message to llm_flow when stage==dialog emits an interrupt SSE event."""
    session_resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert resp.status_code == 200

    lines = resp.text.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    assert any("interrupt" in e for e in events), "Expected an interrupt SSE event"


# ---------------------------------------------------------------------------
# Resume → fake_llm / real_llm response (full API cycle)
# ---------------------------------------------------------------------------


def test_resume_test_flow_done_event(client):
    """After first resume (pause) and second resume, test_flow emits a done SSE event."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # First call: starts graph, pauses at interrupt.
    resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    event_types = [e["event"] for e in events]
    assert "interrupt" in event_types

    # Second call: resumes with user reply, graph completes.
    resp = client.post(f"/api/resume/{session_id}", json={"text": "user reply"})
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1, "Should emit exactly one done event"


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_resume_llm_flow_streaming_and_done(client):
    """After first resume (pause) and second resume, llm_flow streams answer/reasoning chunks then emits done."""
    session_resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # First call: starts graph, pauses at interrupt.
    resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    event_types = [e["event"] for e in events]
    assert "interrupt" in event_types

    # Second call: resumes with user reply, graph completes.
    resp = client.post(f"/api/resume/{session_id}", json={"text": "user reply"})
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1, "Should emit exactly one done event"

    # Check that we received at least one streaming chunk (answer or reasoning).
    streaming_chunks = [e for e in events if e["event"] in ("answer", "reasoning")]
    assert len(streaming_chunks) > 0, "Should emit at least one answer/reasoning chunk"


# ---------------------------------------------------------------------------
# Integration: full lifecycle via API only (no direct SessionManager calls)
# ---------------------------------------------------------------------------


def test_full_lifecycle_create_pause_resume(client):
    """End-to-end: create session → resume (pause) → resume → assert done event."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # First call: starts graph, pauses at interrupt.
    pause_resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert pause_resp.status_code == 200
    events = parse_sse_events(pause_resp.text)
    event_types = [e["event"] for e in events]
    assert "interrupt" in event_types

    # Second call: resumes with user reply, graph completes.
    resume_resp = client.post(f"/api/resume/{session_id}", json={"text": "user reply"})
    assert resume_resp.status_code == 200
    events = parse_sse_events(resume_resp.text)
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1, "Should emit exactly one done event"


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_full_lifecycle_llm_flow(client):
    """End-to-end: create session → resume (pause) → resume → assert streaming chunks + done."""
    session_resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # First call: starts graph, pauses at interrupt.
    pause_resp = client.post(f"/api/resume/{session_id}", json={"text": "hello"})
    assert pause_resp.status_code == 200
    events = parse_sse_events(pause_resp.text)
    event_types = [e["event"] for e in events]
    assert "interrupt" in event_types

    # Second call: resumes with user reply, graph completes.
    resume_resp = client.post(f"/api/resume/{session_id}", json={"text": "user reply"})
    assert resume_resp.status_code == 200
    events = parse_sse_events(resume_resp.text)
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1, "Should emit exactly one done event"

    # Check that we received at least one streaming chunk (answer or reasoning).
    streaming_chunks = [e for e in events if e["event"] in ("answer", "reasoning")]
    assert len(streaming_chunks) > 0, "Should emit at least one answer/reasoning chunk"


# ---------------------------------------------------------------------------
# Cleanup: delete session removes state via API
# ---------------------------------------------------------------------------


def test_delete_session_after_resume(client):
    """Deleting a session after resume via API removes its checkpoint data."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TEST_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # First call: pauses at interrupt.
    client.post(f"/api/resume/{session_id}", json={"text": "hello"})

    # Second call: resumes, graph completes.
    client.post(f"/api/resume/{session_id}", json={"text": "reply"})

    # Delete via API.
    delete_resp = client.delete(f"/api/sessions/{session_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    from backend.session_manager import SessionManager

    mgr = SessionManager()
    assert mgr.get_session(session_id) is None


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_delete_llm_flow_session_after_resume(client):
    """Deleting a session after resume via API removes its checkpoint data."""
    session_resp = client.post("/api/sessions", json={"graph_id": _LLM_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # First call: pauses at interrupt.
    client.post(f"/api/resume/{session_id}", json={"text": "hello"})

    # Second call: resumes, graph completes.
    client.post(f"/api/resume/{session_id}", json={"text": "reply"})

    # Delete via API.
    delete_resp = client.delete(f"/api/sessions/{session_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    from backend.session_manager import SessionManager

    mgr = SessionManager()
    assert mgr.get_session(session_id) is None


# ---------------------------------------------------------------------------
# tool_call_flow — real LLM + ToolNode → emits tool_call SSE event
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_tool_call_flow_session(client):
    """POST /api/sessions for tool_call_flow returns session_id, thread_id, graph_id, graph_name."""
    resp = client.post("/api/sessions", json={"graph_id": _TOOL_CALL_GRAPH_ID})
    assert resp.status_code == 200
    data = resp.json()
    assert data["graph_id"] == _TOOL_CALL_GRAPH_ID
    assert data["graph_name"] == "Tool Call Flow"
    assert data["session_id"]
    assert data["thread_id"]


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_tool_call_flow_emits_tool_call_event(client):
    """tool_call_flow emits a tool_call SSE event when the LLM calls today_tool."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TOOL_CALL_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    resp = client.post(f"/api/resume/{session_id}", json={"text": ""})
    assert resp.status_code == 200

    events = parse_sse_events(resp.text)
    # Both valid ("tool_call") and invalid ("invalid_tool_call") calls are emitted as distinct SSE events.
    call_events = [e for e in events if e["event"] in ("tool_call", "invalid_tool_call")]
    assert len(call_events) >= 1, "Should emit at least one tool_call or invalid_tool_call event"

    # At least one of the calls must be today_tool (the graph's real tool).
    names = {e["data"]["name"] for e in call_events}
    assert "today_tool" in names, f"Expected 'today_tool' among {names}"


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_tool_call_flow_emits_done_event(client):
    """tool_call_flow emits a done SSE event after completing."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TOOL_CALL_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    resp = client.post(f"/api/resume/{session_id}", json={"text": ""})
    assert resp.status_code == 200

    events = parse_sse_events(resp.text)
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) >= 1, "Should emit at least one done event"


@pytest.mark.skipif(not _llm_available(), reason="LLM server not available at 127.0.0.1:8081")
def test_delete_tool_call_flow_session(client):
    """Deleting a tool_call_flow session removes its checkpoint data."""
    session_resp = client.post("/api/sessions", json={"graph_id": _TOOL_CALL_GRAPH_ID})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    client.post(f"/api/resume/{session_id}", json={"text": ""})

    delete_resp = client.delete(f"/api/sessions/{session_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    from backend.session_manager import SessionManager

    mgr = SessionManager()
    assert mgr.get_session(session_id) is None
