"""Tests for SQLite-backed session persistence.

Covers:
- Session metadata is persisted to SQLite when SqliteSaver is used
- Sessions are restored on SessionManager construction (lazy graph compilation)
- Status is computed lazily from checkpoint history (paused vs completed)
- Deleting a session removes both checkpoint data and DB record
- Title format is ``{graph_name} {6-char md5 of created_at}``
"""

from __future__ import annotations

import sqlite3
from typing import TypedDict

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from backend.persistence import (
    _create_tables,
    create_session as _create_session,
    delete_session as _delete_session,
    list_sessions,
)
from backend.session_manager import SessionManager


# ---------------------------------------------------------------------------
# Minimal test graph — mirrors the book_planner interrupt behaviour.
# ---------------------------------------------------------------------------


class _TestState(TypedDict):
    messages: list
    stage: str


def _pause_node(state: _TestState) -> dict:
    if state["stage"] == "dialog":
        interrupt({"reason": "waiting_for_input"})
    return {"messages": [], "stage": "next"}


def _finish_node(state: _TestState) -> dict:
    return {"messages": [], "stage": "done"}


_test_builder = StateGraph(_TestState)
_test_builder.add_node("pause", _pause_node)
_test_builder.add_node("finish", _finish_node)
_test_builder.add_edge(START, "pause")
_test_builder.add_edge("pause", "finish")
_test_builder.add_edge("finish", END)

_TEST_GRAPH_ID = "test_sqlite_graph"
_test_graph_compiled = _test_builder.compile()


@pytest.fixture(scope="module")
def sqlite_saver():
    """Return a SqliteSaver backed by an in-memory SQLite database."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    yield saver
    conn.close()


@pytest.fixture(scope="module")
def session_manager_with_sqlite(sqlite_saver):
    """SessionManager pre-populated with the test graph and SQLite checkpointer."""
    from backend.graph_registry import GRAPH_REGISTRY

    original = GRAPH_REGISTRY.get(_TEST_GRAPH_ID)
    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph_compiled
    mgr = SessionManager(checkpointer=sqlite_saver)
    yield mgr
    GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)
    if original is not None:
        GRAPH_REGISTRY[_TEST_GRAPH_ID] = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create the sessions table on *conn* if it doesn't exist."""
    _create_tables(conn)


# ---------------------------------------------------------------------------
# Session creation persists to SQLite
# ---------------------------------------------------------------------------


def test_create_session_persists_to_sqlite(session_manager_with_sqlite, sqlite_saver):
    """Creating a session writes a row to the sessions table."""
    session = session_manager_with_sqlite.create_session(_TEST_GRAPH_ID)
    session_id = session["session_id"]

    # The in-memory connection inside SqliteSaver should have the row.
    cur = sqlite_saver.conn.cursor()
    cur.execute(
        "SELECT session_id, thread_id, graph_id, title, status FROM sessions WHERE session_id = ?",
        (session_id,),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == session_id
    assert row[1] == session["thread_id"]
    assert row[2] == _TEST_GRAPH_ID
    assert row[3] == session["title"]
    assert row[4] == "running"


def test_session_title_format(session_manager_with_sqlite):
    """Title is ``{graph_name} {6-char md5 of created_at}``."""
    session = session_manager_with_sqlite.create_session(_TEST_GRAPH_ID)
    title = session["title"]
    parts = title.split()
    assert len(parts) == 2
    # get_graph_name falls back to graph_id for unknown graphs.
    assert parts[0] == _TEST_GRAPH_ID
    assert len(parts[1]) == 6, f"Expected 6-char hash, got {parts[1]!r}"


# ---------------------------------------------------------------------------
# Restore on startup
# ---------------------------------------------------------------------------


def test_restore_sessions_from_sqlite(sqlite_saver):
    """A fresh SessionManager with the same SqliteSaver restores persisted sessions."""
    from backend.graph_registry import GRAPH_REGISTRY

    original = GRAPH_REGISTRY.get(_TEST_GRAPH_ID)
    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph_compiled

    # First manager: create a session.
    mgr1 = SessionManager(checkpointer=sqlite_saver)
    session = mgr1.create_session(_TEST_GRAPH_ID)
    session_id = session["session_id"]

    # Second manager (simulates restart) should restore the session.
    mgr2 = SessionManager(checkpointer=sqlite_saver)
    restored = mgr2.get_session(session_id)
    assert restored is not None
    assert restored["session_id"] == session_id
    assert restored["thread_id"] == session["thread_id"]
    assert restored["graph_id"] == _TEST_GRAPH_ID
    assert restored["title"] == session["title"]

    GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)
    if original is not None:
        GRAPH_REGISTRY[_TEST_GRAPH_ID] = original


def test_restored_session_can_resume(sqlite_saver):
    """A restored session can continue graph execution via resume()."""
    from backend.graph_registry import GRAPH_REGISTRY

    original = GRAPH_REGISTRY.get(_TEST_GRAPH_ID)
    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph_compiled

    # First manager: create and pause.
    mgr1 = SessionManager(checkpointer=sqlite_saver)
    session = mgr1.create_session(_TEST_GRAPH_ID)
    thread_id = session["thread_id"]
    result = mgr1.resume(thread_id, {"messages": [], "stage": "dialog"})
    assert "__interrupt__" in result

    # Second manager: restore and resume.
    mgr2 = SessionManager(checkpointer=sqlite_saver)
    resumed = mgr2.resume(thread_id, Command(resume="user reply"))
    assert "__interrupt__" not in resumed

    GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)
    if original is not None:
        GRAPH_REGISTRY[_TEST_GRAPH_ID] = original


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_paused_when_no_resume_write(sqlite_saver):
    """A freshly created session that has not been resumed reports 'paused'."""
    from backend.graph_registry import GRAPH_REGISTRY

    original = GRAPH_REGISTRY.get(_TEST_GRAPH_ID)
    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph_compiled

    mgr = SessionManager(checkpointer=sqlite_saver)
    session = mgr.create_session(_TEST_GRAPH_ID)
    thread_id = session["thread_id"]

    # First invoke — graph pauses at interrupt.
    result = mgr.resume(thread_id, {"messages": [], "stage": "dialog"})
    assert "__interrupt__" in result

    # Status should be 'paused' because no __resume__ write exists yet.
    status = await mgr.get_session_status(session["session_id"])
    assert status == "paused"

    GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)
    if original is not None:
        GRAPH_REGISTRY[_TEST_GRAPH_ID] = original


@pytest.mark.asyncio
async def test_status_completed_after_resume(sqlite_saver):
    """After a successful resume the session reports 'completed'."""
    from backend.graph_registry import GRAPH_REGISTRY

    original = GRAPH_REGISTRY.get(_TEST_GRAPH_ID)
    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph_compiled

    mgr = SessionManager(checkpointer=sqlite_saver)
    session = mgr.create_session(_TEST_GRAPH_ID)
    thread_id = session["thread_id"]

    # Pause.
    result = mgr.resume(thread_id, {"messages": [], "stage": "dialog"})
    assert "__interrupt__" in result

    # Resume — graph completes.
    mgr.resume(thread_id, Command(resume="user reply"))

    status = await mgr.get_session_status(session["session_id"])
    assert status == "completed"

    GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)
    if original is not None:
        GRAPH_REGISTRY[_TEST_GRAPH_ID] = original


@pytest.mark.asyncio
async def test_get_session_status_returns_none_for_unknown(session_manager_with_sqlite):
    """get_session_status returns None for a session that doesn't exist."""
    assert await session_manager_with_sqlite.get_session_status("nonexistent") is None


@pytest.mark.asyncio
async def test_status_paused_independent_of_other_sessions(sqlite_saver):
    """Completing one session must not affect the status of a paused sibling."""
    from backend.graph_registry import GRAPH_REGISTRY

    original = GRAPH_REGISTRY.get(_TEST_GRAPH_ID)
    GRAPH_REGISTRY[_TEST_GRAPH_ID] = _test_graph_compiled

    mgr = SessionManager(checkpointer=sqlite_saver)

    # Create two sessions.
    s1 = mgr.create_session(_TEST_GRAPH_ID)
    s2 = mgr.create_session(_TEST_GRAPH_ID)

    # Pause both.
    result1 = mgr.resume(s1["thread_id"], {"messages": [], "stage": "dialog"})
    result2 = mgr.resume(s2["thread_id"], {"messages": [], "stage": "dialog"})
    assert "__interrupt__" in result1
    assert "__interrupt__" in result2

    # Both should be paused.
    status1 = await mgr.get_session_status(s1["session_id"])
    status2 = await mgr.get_session_status(s2["session_id"])
    assert status1 == "paused"
    assert status2 == "paused"

    # Complete s1 only.
    mgr.resume(s1["thread_id"], Command(resume="user reply"))

    # s1 should be completed, s2 must stay paused.
    status1 = await mgr.get_session_status(s1["session_id"])
    status2 = await mgr.get_session_status(s2["session_id"])
    assert status1 == "completed"
    assert status2 == "paused"

    GRAPH_REGISTRY.pop(_TEST_GRAPH_ID, None)
    if original is not None:
        GRAPH_REGISTRY[_TEST_GRAPH_ID] = original


# ---------------------------------------------------------------------------
# Delete removes both checkpoint and DB record
# ---------------------------------------------------------------------------


def test_delete_session_removes_db_record(session_manager_with_sqlite, sqlite_saver):
    """Deleting a session removes its row from the sessions table."""
    session = session_manager_with_sqlite.create_session(_TEST_GRAPH_ID)
    session_id = session["session_id"]

    session_manager_with_sqlite.delete_session(session_id)

    # No row in the DB anymore.
    cur = sqlite_saver.conn.cursor()
    cur.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
    assert cur.fetchone() is None

    # Also not in the manager.
    assert session_manager_with_sqlite.get_session(session_id) is None


def test_list_sessions_includes_all(session_manager_with_sqlite):
    """list_sessions returns all persisted session rows."""
    s1 = session_manager_with_sqlite.create_session(_TEST_GRAPH_ID)
    s2 = session_manager_with_sqlite.create_session(_TEST_GRAPH_ID)

    rows = session_manager_with_sqlite.list_all_sessions()
    ids = {r["session_id"] for r in rows}
    assert s1["session_id"] in ids
    assert s2["session_id"] in ids


# ---------------------------------------------------------------------------
# Direct persistence CRUD helpers
# ---------------------------------------------------------------------------


def test_format_title():
    """Title is formatted as ``{graph_name} {6-char hash}``."""
    from backend.persistence import _format_title

    title = _format_title("Book Planner", 1_000_000.0)
    # Split on last space to separate the hash from the name.
    idx = title.rfind(" ")
    assert idx > 0
    assert title[:idx] == "Book Planner"
    assert len(title[idx + 1 :]) == 6


def test_create_and_delete_session_via_persistence():
    """CRUD via the persistence module directly."""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(":memory:", check_same_thread=False)
    _ensure_tables(conn)
    from backend.persistence import create_session, delete_session, get_session, list_sessions

    sid = "test-session-id"
    tid = "test-thread-id"
    create_session(conn, sid, tid, "book_planner", "Book Planner abc123")

    row = get_session(conn, sid)
    assert row is not None
    assert row["session_id"] == sid
    assert row["graph_id"] == "book_planner"
    assert row["status"] == "running"

    rows = list_sessions(conn)
    assert len(rows) == 1

    deleted = delete_session(conn, sid)
    assert deleted is True
    assert get_session(conn, sid) is None

    # Double-delete is safe.
    assert delete_session(conn, sid) is False


def test_update_session_title_via_persistence():
    """update_session_title writes a new title and updated_at to the DB."""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(":memory:", check_same_thread=False)
    _ensure_tables(conn)
    from backend.persistence import create_session, get_session, update_session_title

    sid = "test-sid"
    tid = "test-tid"
    create_session(conn, sid, tid, "book_planner", "Original Title")

    import time

    time.sleep(0.01)
    updated = update_session_title(conn, sid, "New Title")
    assert updated is True

    row = get_session(conn, sid)
    assert row["title"] == "New Title"
    assert row["updated_at"] > row["created_at"]

    # Update to a non-existent session returns False.
    assert update_session_title(conn, "missing", "X") is False
