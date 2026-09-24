"""Tests for session management with interrupt/resume pattern.

Covers the full session lifecycle:
- Creation with unique thread_id
- Graph pausing via interrupt()
- Resuming with client messages
- Cleanup / deletion
- Uniqueness of thread_ids across sessions
"""

from __future__ import annotations

from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from backend.session_manager import SessionManager


# ---------------------------------------------------------------------------
# Minimal test graph — mirrors the interrupt behaviour of book_planner
# without requiring a real LLM.
# ---------------------------------------------------------------------------


class _SessionState(TypedDict):
    """Minimal graph state for session lifecycle tests."""

    messages: list
    stage: str


def _pause_node(state: _SessionState) -> dict:
    """Node that interrupts when stage is 'dialog' (no tool calls yet)."""
    if state["stage"] == "dialog":
        interrupt({"reason": "waiting_for_input"})
    return {"messages": [], "stage": "next"}


def _finish_node(state: _SessionState) -> dict:
    """Terminal node."""
    return {"messages": [], "stage": "done"}


_test_graph_builder = StateGraph(_SessionState)
_test_graph_builder.add_node("pause", _pause_node)
_test_graph_builder.add_node("finish", _finish_node)
_test_graph_builder.add_edge(START, "pause")
_test_graph_builder.add_conditional_edges(
    "pause",
    lambda s: "finish" if s["stage"] == "next" else "pause",
    {"pause": "pause", "finish": "finish"},
)
_test_graph_builder.add_edge("finish", END)

# Compiled once and registered under a fake graph_id for testing.
_TEST_GRAPH_ID = "test_graph"
_test_graph_compiled = _test_graph_builder.compile()


@pytest.fixture(scope="module")
def session_manager():
    """Return a fresh SessionManager pre-populated with the test graph."""
    # Inject the test graph into GRAPH_REGISTRY so create_session can find it.
    from backend.graph_registry import GRAPH_REGISTRY

    original = GRAPH_REGISTRY.get(_TEST_GRAPH_ID)
    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph_compiled
    mgr = SessionManager()

    yield mgr

    if original is None:
        GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)
    else:
        GRAPH_REGISTRY[_TEST_GRAPH_ID] = original


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------


def test_create_session_returns_id(session_manager):
    """Creating a session returns a non-empty session_id."""
    result = session_manager.create_session(_TEST_GRAPH_ID)
    assert isinstance(result, dict)
    assert "session_id" in result
    assert "thread_id" in result
    assert result["session_id"]
    assert result["thread_id"]


def test_create_session_defaults_to_registered_graph(session_manager):
    """create_session uses the default graph_id."""
    result = session_manager.create_session(_TEST_GRAPH_ID)
    assert result["graph_id"] == _TEST_GRAPH_ID


def test_create_session_returns_thread_id(session_manager):
    """The returned thread_id matches the one stored internally."""
    result = session_manager.create_session(_TEST_GRAPH_ID)
    session_id = result["session_id"]
    stored = session_manager.get_session(session_id)
    assert stored is not None
    assert stored["thread_id"] == result["thread_id"]


# ---------------------------------------------------------------------------
# Thread ID uniqueness
# ---------------------------------------------------------------------------


def test_unique_thread_ids(session_manager):
    """Each created session gets a unique thread_id."""
    ids = {session_manager.create_session(_TEST_GRAPH_ID)["thread_id"] for _ in range(10)}
    assert len(ids) == 10, "All thread_ids must be unique"


def test_no_duplicate_sessions_same_thread_id(session_manager):
    """Two sessions cannot share the same thread_id."""
    s1 = session_manager.create_session(_TEST_GRAPH_ID)
    s2 = session_manager.create_session(_TEST_GRAPH_ID)
    assert s1["thread_id"] != s2["thread_id"]


# ---------------------------------------------------------------------------
# Interrupt / pause
# ---------------------------------------------------------------------------


def test_graph_pauses_on_interrupt(session_manager):
    """A newly created graph pauses at interrupt() when stage == 'dialog'."""
    session = session_manager.create_session(_TEST_GRAPH_ID)
    thread_id = session["thread_id"]

    result = session_manager.resume(thread_id, {"messages": [], "stage": "dialog"})
    # The graph should be in a paused state (interrupted).
    assert "__interrupt__" in result


# ---------------------------------------------------------------------------
# Resume pattern
# ---------------------------------------------------------------------------


def test_resume_continues_graph(session_manager):
    """Resuming with Command pushes the graph forward from interrupt."""
    session = session_manager.create_session(_TEST_GRAPH_ID)
    thread_id = session["thread_id"]

    # First invoke — pauses at interrupt.
    result = session_manager.resume(thread_id, {"messages": [], "stage": "dialog"})
    assert "__interrupt__" in result

    # Resume — should continue past the interrupt and reach the finish node.
    resume_result = session_manager.resume(
        thread_id,
        Command(resume="user reply"),
    )
    # After resume the graph is no longer interrupted.
    assert "__interrupt__" not in resume_result


# ---------------------------------------------------------------------------
# Cleanup / deletion
# ---------------------------------------------------------------------------


def test_delete_session_removes_state(session_manager):
    """Deleting a session removes it from the manager."""
    session = session_manager.create_session(_TEST_GRAPH_ID)
    session_id = session["session_id"]

    session_manager.delete_session(session_id)
    assert session_manager.get_session(session_id) is None


def test_delete_nonexistent_session_is_safe(session_manager):
    """Deleting a non-existent session does not raise."""
    session_manager.delete_session("nonexistent-id")  # should not raise


def test_deleted_session_cannot_resume(session_manager):
    """Resuming a deleted session raises an error."""
    session = session_manager.create_session(_TEST_GRAPH_ID)
    session_id = session["session_id"]
    session_manager.delete_session(session_id)

    with pytest.raises(ValueError):
        session_manager.resume(session_id, Command(resume="should fail"))


# ---------------------------------------------------------------------------
# Session lookup
# ---------------------------------------------------------------------------


def test_get_session_returns_none_for_unknown(session_manager):
    """get_session returns None for unknown session IDs."""
    assert session_manager.get_session("unknown") is None


# ---------------------------------------------------------------------------
# Rename / title update
# ---------------------------------------------------------------------------


def test_rename_session_updates_title(session_manager):
    """rename_session updates the in-memory title."""
    session = session_manager.create_session(_TEST_GRAPH_ID)
    sid = session["session_id"]

    result = session_manager.rename_session(sid, "Custom Name")
    assert result is not None
    assert result["title"] == "Custom Name"


def test_rename_session_returns_none_for_unknown(session_manager):
    """rename_session returns None for a non-existent session."""
    assert session_manager.rename_session("nonexistent", "Name") is None


def test_rename_session_updates_updated_at(session_manager):
    """rename_session updates updated_at to the current time."""
    import time

    session = session_manager.create_session(_TEST_GRAPH_ID)
    sid = session["session_id"]
    before = session_manager._sessions[sid]["updated_at"]

    time.sleep(0.01)
    result = session_manager.rename_session(sid, "New Title")
    assert result is not None
    assert result["updated_at"] > before


def test_list_sessions_includes_updated_at(session_manager):
    """list_all_sessions returns rows that include updated_at."""
    session = session_manager.create_session(_TEST_GRAPH_ID)
    sid = session["session_id"]

    row = next(r for r in session_manager.list_all_sessions() if r["session_id"] == sid)
    assert "updated_at" in row
