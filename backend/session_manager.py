"""Session manager — creates and drives LangGraph sessions with checkpointing.

Each session gets a unique ``thread_id`` (UUID) and its own compiled graph
instance backed by a checkpointer (by default :class:`InMemorySaver`, or a
user-supplied :class:`SqliteSaver` for production).

Session metadata is persisted to SQLite when a SqliteSaver is configured.
On construction the manager restores any previously saved sessions from the
database; graphs are compiled lazily on first use.

Usage
>>> from backend.session_manager import SessionManager
>>> mgr = SessionManager()
>>> session = mgr.create_session("book_planner")
>>> result = mgr.resume(session["thread_id"], initial_state)   # pauses at interrupt
>>> result = mgr.resume(session["thread_id"], Command(resume="user reply"))  # continues
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from langchain.messages import AnyMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.graph_registry import GRAPH_REGISTRY, get_graph_name
from backend.persistence import (
    _create_tables as _ensure_sessions_table,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages LangGraph sessions with checkpoint-based interrupt/resume."""

    def __init__(self, checkpointer: Any | None = None) -> None:
        """Initialise the session manager.

        Parameters
        checkpointer : Checkpointer | None
            A LangGraph checkpointer instance.  If ``None``, an
            :class:`InMemorySaver` is created (intended for tests).
        """
        self._checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._restore_sessions()

    def _maybe_with_db(self) -> Any:
        """Return the underlying SQLite connection for sync CRUD operations.

        Returns ``None`` for in-memory checkers (e.g. InMemorySaver).
        For AsyncSqliteSaver we return the sync connection from get_db()
        because the persistence CRUD functions are synchronous — the
        async connection would produce unawaited-coroutine warnings.
        """
        if not hasattr(self._checkpointer, "conn"):
            return None
        # AsyncSqliteSaver.conn is an aiosqlite.Connection which cannot be
        # used with synchronous sqlite3 API; fall back to the sync conn.
        import sqlite3

        raw_conn = self._checkpointer.conn
        if isinstance(raw_conn, sqlite3.Connection):
            return raw_conn
        from backend.persistence import get_db

        return get_db()

    # session lifecycle

    def create_session(self, graph_id: str | None = None) -> dict[str, str]:
        """Create a new session for *graph_id*.

        Returns
        dict with keys ``session_id``, ``thread_id``, ``graph_id``, and
        ``graph_name``.
        """
        from backend.persistence import create_session, get_db, _format_title

        if not graph_id:
            # No id given (or an empty one): fall back to the first registered
            # graph — tiers load ``examples`` before ``user``.
            if not GRAPH_REGISTRY:
                raise ValueError(
                    "No graphs are registered — cannot create a session "
                    "without an explicit graph_id."
                )
            graph_id = next(iter(GRAPH_REGISTRY))

        thread_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        # Build a fresh compiled graph instance with the configured checkpointer.
        compiled_graph = GRAPH_REGISTRY[graph_id]
        graph_instance = compiled_graph.builder.compile(checkpointer=self._checkpointer)

        graph_name = get_graph_name(graph_id)
        now = time.time()
        title = _format_title(graph_name, now)

        session_record: dict[str, Any] = {
            "session_id": session_id,
            "thread_id": thread_id,
            "graph_id": graph_id,
            "graph": graph_instance,
            "title": title,
            "status": "running",
            "created_at": now,
            "updated_at": now,
        }
        self._sessions[session_id] = session_record

        # Persist metadata to SQLite when a persistent checkpointer is in use.
        conn = self._maybe_with_db()
        if conn is not None:
            try:
                _ensure_sessions_table(conn)
                create_session(conn, session_id, thread_id, graph_id, title)
            except Exception as exc:
                logger.warning("Failed to persist session %s: %s", session_id, exc)

        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "graph_id": graph_id,
            "graph_name": graph_name,
            "title": title,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return the session dict or ``None`` if not found."""
        return self._sessions.get(session_id)

    def rename_session(self, session_id: str, title: str) -> dict[str, Any] | None:
        """Rename a session. Updates in-memory state and persisted record.

        Returns the updated session metadata dict, or ``None`` if not found.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        session["title"] = title
        session["updated_at"] = time.time()

        conn = self._maybe_with_db()
        if conn is not None:
            try:
                from backend.persistence import update_session_title

                update_session_title(conn, session_id, title)
            except Exception as exc:
                logger.warning("Failed to persist rename of %s: %s", session_id, exc)

        return self._serialize_session(session)

    def delete_session(self, session_id: str) -> None:
        """Remove a session and its checkpoint data."""
        session = self._sessions.pop(session_id, None)
        if session is not None:
            try:
                session["graph"].checkpointer.delete_thread(session["thread_id"])
            except Exception:
                pass

        # Remove persistence record.
        conn = self._maybe_with_db()
        if conn is not None:
            try:
                from backend.persistence import delete_session

                delete_session(conn, session_id)
            except Exception as exc:
                logger.warning("Failed to delete session record %s: %s", session_id, exc)

    # restore on startup

    def _restore_sessions(self) -> None:
        """Load persisted session metadata from SQLite (production only)."""
        if not hasattr(self._checkpointer, "conn"):
            return

        from backend.persistence import list_sessions

        try:
            conn = self._maybe_with_db()
            if conn is None:
                return
            _ensure_sessions_table(conn)
            rows = list_sessions(conn)
        except Exception as exc:
            logger.warning("Failed to restore sessions from DB: %s", exc)
            return

        for row in rows:
            session_id = row["session_id"]
            # Build a stub entry — the graph will be compiled lazily on first use.
            self._sessions[session_id] = {
                "session_id": session_id,
                "thread_id": row["thread_id"],
                "graph_id": row["graph_id"],
                "title": row["title"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row.get("updated_at", row["created_at"]),
            }

        logger.info("Restored %d session(s) from persistence store.", len(rows))

    # resume / invoke

    def resume(self, thread_id: str, value: Any) -> dict[str, Any]:
        """Resume (or start) graph execution for *thread_id*.

        Parameters
        thread_id : str
            The thread ID returned by :py:meth:`create_session`.
        value : Any
            Initial state dict on first call, or a :class:`Command` / plain
            resume value on subsequent calls.

        Returns
        dict
            Graph output including any ``__interrupt__`` key if the graph
            paused.
        """
        # Find the session by thread_id — may need to compile the graph first.
        session = next(
            (s for s in self._sessions.values() if s["thread_id"] == thread_id),
            None,
        )
        if session is None:
            raise ValueError(f"Session not found for thread_id {thread_id!r}")

        # Lazy-compile the graph if it hasn't been created yet (restored session).
        if "graph" not in session:
            compiled_graph = GRAPH_REGISTRY[session["graph_id"]]
            session["graph"] = compiled_graph.builder.compile(
                checkpointer=self._checkpointer
            )

        config = {"configurable": {"thread_id": thread_id}}
        return session["graph"].invoke(value, config=config)

    # listing

    def _serialize_session(self, session: dict[str, Any]) -> dict[str, Any]:
        """Return a flat metadata dict for a session row.

        Includes ``graph_name`` (looked up from registry) and ``updated_at``
        (defaulting to ``created_at`` when the record was loaded before an
        update ever occurred).
        """
        graph_id = session.get("graph_id", "")
        return {
            "session_id": session["session_id"],
            "thread_id": session["thread_id"],
            "graph_id": graph_id,
            "graph_name": get_graph_name(graph_id),
            "title": session["title"],
            "status": session.get("status"),
            "created_at": session["created_at"],
            "updated_at": session.get("updated_at", session["created_at"]),
        }

    def list_all_sessions(self) -> list[dict[str, Any]]:
        """Return all session metadata dicts currently known to this manager.

        For managers backed by a :class:`SqliteSaver` the list is populated
        from the database on construction (see :py:meth:`_restore_sessions`).
        Returned ordered by ``created_at`` descending (newest first).
        """
        rows = [
            self._serialize_session(s)
            for s in self._sessions.values()
        ]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows

    # status helpers

    async def get_session_status(self, session_id: str) -> str | None:
        """Return the computed status for *session_id*, or ``None`` if not found.

        Uses :py:meth:`langgraph.checkpoint.base.BaseCheckpointSaver.aget_tuple`
        to verify checkpoint history, then queries the underlying SQLite
        ``writes`` table for ``__resume__`` entries to distinguish
        ``paused`` from ``completed``.  Read-only — does not modify graph state.

        Async because :class:`AsyncSqliteSaver` requires a running event loop
        for its query methods; calling the sync counterpart would dispatch
        through ``run_coroutine_threadsafe`` on whatever loop happens to be
        active at call time (which may already be closed in pytest).
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        graph = session.get("graph")
        if graph is None:
            # Restored session that hasn't been compiled yet — assume running.
            return "running"

        thread_id = session["thread_id"]
        config = {"configurable": {"thread_id": thread_id}}

        # Check if the checkpointer has any history for this thread.
        try:
            tuple_result = await graph.checkpointer.aget_tuple(config)
        except Exception:
            # Some checkpointer implementations (e.g. mock stubs in tests) may
            # lack aget_tuple / get_tuple; fall back to sync API if available,
            # otherwise assume running and move on.
            try:
                tuple_result = graph.checkpointer.get_tuple(config)
            except Exception:
                return "running"

        if tuple_result is None:
            return "running"

        # Determine status from pending_writes on the latest checkpoint.
        # When paused at an interrupt, pending_writes contains '__interrupt__';
        # when completed (or in-flight with no interrupt), it is empty or lacks it.
        pending = tuple_result.pending_writes
        if pending:
            # Normalize to a list of (task_id, channel, value) tuples — some
            # checkpointer implementations may return a dict instead.
            if isinstance(pending, dict):
                channels = set(pending.keys())
            else:
                channels = {w[1] for w in pending}
            if "__interrupt__" in channels and "__resume__" not in channels:
                return "paused"

        # In-memory or SQLite checkpointer — no pending writes means completed.
        return "completed"
