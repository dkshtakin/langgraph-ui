"""Session manager — creates and drives LangGraph sessions with checkpointing.

Each session gets a unique ``thread_id`` (UUID) and its own compiled graph
instance backed by an :class:`langgraph.checkpoint.memory.InMemorySaver`.
The graph pauses at :py:func:`langgraph.types.interrupt` until the client
calls :py:meth:`SessionManager.resume`.

Usage
-----
>>> from backend.session_manager import SessionManager
>>> mgr = SessionManager()
>>> session = mgr.create_session("book_planner")
>>> result = mgr.resume(session["thread_id"], initial_state)   # pauses at interrupt
>>> result = mgr.resume(session["thread_id"], Command(resume="user reply"))  # continues
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain.messages import AnyMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend import GRAPH_REGISTRY, get_graph_name


# Module-level singleton — shared across all requests.
_instance: SessionManager | None = None


class SessionManager:
    """Manages LangGraph sessions with checkpoint-based interrupt/resume."""

    def __new__(cls) -> "SessionManager":
        global _instance
        if _instance is None:
            _instance = super().__new__(cls)
            _instance._sessions: dict[str, dict[str, Any]] = {}
        return _instance

    def __init__(self) -> None:
        # Singleton ensures this runs only once; guard for safety.
        if not hasattr(self, "_sessions"):
            self._sessions = {}

    # ── session lifecycle ────────────────────────────────────────────────

    def create_session(self, graph_id: str = "book_planner") -> dict[str, str]:
        """Create a new session for *graph_id*.

        Returns
        -------
        dict with keys ``session_id``, ``thread_id``, and ``graph_id``.
        """
        thread_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        # Build a fresh compiled graph instance with InMemorySaver for this session.
        checkpointer = InMemorySaver()
        compiled_graph = GRAPH_REGISTRY[graph_id]
        graph_instance = compiled_graph.builder.compile(checkpointer=checkpointer)

        self._sessions[session_id] = {
            "session_id": session_id,
            "thread_id": thread_id,
            "graph_id": graph_id,
            "graph": graph_instance,
        }

        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "graph_id": graph_id,
            "graph_name": get_graph_name(graph_id),
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return the session dict or ``None`` if not found."""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> None:
        """Remove a session and its checkpoint data."""
        session = self._sessions.pop(session_id, None)
        if session is not None:
            try:
                session["graph"].checkpointer.delete_thread(session["thread_id"])
            except Exception:
                pass

    # ── resume / invoke ──────────────────────────────────────────────────

    def resume(self, thread_id: str, value: Any) -> dict[str, Any]:
        """Resume (or start) graph execution for *thread_id*.

        Parameters
        ----------
        thread_id : str
            The thread ID returned by :py:meth:`create_session`.
        value : Any
            Initial state dict on first call, or a :class:`Command` / plain
            resume value on subsequent calls.

        Returns
        -------
        dict
            Graph output including any ``__interrupt__`` key if the graph
            paused.
        """
        # Find the session by thread_id.
        session = next(
            (s for s in self._sessions.values() if s["thread_id"] == thread_id),
            None,
        )
        if session is None:
            raise ValueError(f"Session not found for thread_id {thread_id!r}")

        config = {"configurable": {"thread_id": thread_id}}
        return session["graph"].invoke(value, config=config)
