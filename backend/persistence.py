"""SQLite persistence layer for session metadata.

Provides a lazy-initialized SQLite connection and CRUD helpers for the
``sessions`` table.  The database file lives next to the backend package
as ``backend/sessions.db``.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parent / "sessions.db"
_db_conn: sqlite3.Connection | None = None
_async_db_conn: Any = None  # aiosqlite.Connection


def get_db() -> sqlite3.Connection:
    """Return a lazy-initialized sync connection to the sessions database.

    The connection is created on first call and reused thereafter.
    ``check_same_thread=False`` allows the connection to be used from
    thread pools (e.g. LangGraph's checkpointer executor).
    """
    global _db_conn
    if _db_conn is None:
        _db_conn = sqlite3.connect(
            str(_DB_PATH),
            check_same_thread=False,
        )
        _db_conn.execute("PRAGMA journal_mode=WAL")
        _create_tables(_db_conn)
    return _db_conn


def get_async_db() -> Any:
    """Return a lazy-initialized async connection for AsyncSqliteSaver.

    Returns an ``aiosqlite.Connection`` bound to the same database file as
    :py:func:`get_db`.  Created on first call and reused thereafter.
    """
    global _async_db_conn
    if _async_db_conn is None:
        import aiosqlite

        _async_db_conn = aiosqlite.connect(str(_DB_PATH))
    return _async_db_conn


def _create_tables(conn: sqlite3.Connection) -> None:
    """Ensure the sessions table exists."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            thread_id  TEXT NOT NULL UNIQUE,
            graph_id   TEXT NOT NULL,
            title      TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'running',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.commit()


def _format_title(graph_name: str, created_at: float) -> str:
    """Format a session title as ``{graph_name} {short_hash}``."""
    short_hash = hashlib.md5(str(created_at).encode()).hexdigest()[:6]
    return f"{graph_name} {short_hash}"


# CRUD


def create_session(
    conn: sqlite3.Connection,
    session_id: str,
    thread_id: str,
    graph_id: str,
    title: str,
) -> None:
    """Insert a new session row."""
    now = time.time()
    conn.execute(
        """
        INSERT OR REPLACE INTO sessions
            (session_id, thread_id, graph_id, title, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'running', ?, ?)
        """,
        (session_id, thread_id, graph_id, title, now, now),
    )
    conn.commit()


def get_session(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    """Return session metadata or ``None``."""
    cur = conn.execute(
        "SELECT session_id, thread_id, graph_id, title, status, created_at, updated_at FROM sessions WHERE session_id = ?",
        (session_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "session_id": row[0],
        "thread_id": row[1],
        "graph_id": row[2],
        "title": row[3],
        "status": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


def list_sessions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all session rows ordered by created_at descending."""
    cur = conn.execute(
        "SELECT session_id, thread_id, graph_id, title, status, created_at, updated_at FROM sessions ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    return [
        {
            "session_id": r[0],
            "thread_id": r[1],
            "graph_id": r[2],
            "title": r[3],
            "status": r[4],
            "created_at": r[5],
            "updated_at": r[6],
        }
        for r in rows
    ]


def update_session_status(
    conn: sqlite3.Connection, session_id: str, status: str
) -> None:
    """Update the status and updated_at for a session."""
    conn.execute(
        """
        UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ?
        """,
        (status, time.time(), session_id),
    )
    conn.commit()


def update_session_title(
    conn: sqlite3.Connection, session_id: str, title: str
) -> bool:
    """Update the title and updated_at for a session. Returns ``True`` if a row was modified."""
    cur = conn.execute(
        "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
        (title, time.time(), session_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_session(conn: sqlite3.Connection, session_id: str) -> bool:
    """Delete a session row. Returns ``True`` if a row was removed."""
    cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    return cur.rowcount > 0


def has_resume_write(conn: sqlite3.Connection, thread_id: str) -> bool:
    """Return ``True`` if a ``__resume__`` write exists for *thread_id*.

    Used to decide whether a checkpointed session is ``paused`` or
    ``completed`` — presence of the resume write means the interrupt
    was already answered.
    """
    cur = conn.execute(
        "SELECT 1 FROM writes WHERE thread_id = ? AND channel = '__resume__' LIMIT 1",
        (thread_id,),
    )
    return cur.fetchone() is not None
