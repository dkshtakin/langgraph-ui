"""Integration test that mirrors how main.py uses the app in production.

Exercises the full path: importing backend.main (same code as uvicorn),
creating a TestClient, and hitting endpoints — which is where AsyncSqliteSaver
needs a running event loop inside _get_session_manager().
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def prod_app():
    """Import and expose the real production app (same code path as uvicorn)."""
    from backend.main import app
    return app


@pytest.fixture(scope="module")
def _clear_test_db():
    """Point the production persistence layer at an in-memory DB.

    Avoids Windows PermissionError when trying to unlink a file that
    aiosqlite connections (from previous test runs) still hold open.
    Also resets the lazy singletons so the next call to get_async_db() /
    get_db() creates fresh connections against the new :memory: path.
    """
    import backend.persistence as persistence

    original = persistence._DB_PATH
    persistence._DB_PATH = ":memory:"
    # Lazy singletons cache a connection to the old file; reset them so
    # subsequent calls re-open against the in-memory database.
    persistence._async_db_conn = None
    persistence._db_conn = None
    try:
        yield
    finally:
        persistence._DB_PATH = original
        persistence._async_db_conn = None
        persistence._db_conn = None


@pytest.mark.asyncio
async def test_create_session_via_prod_app(prod_app, _clear_test_db):
    """POST /api/sessions works through the real app.

    This catches issues where AsyncSqliteSaver needs an event loop — e.g.
    if _get_session_manager is called outside an async context (it would
    be dispatched to a worker thread by anyio's run_in_threadpool and
    fail with 'no running event loop').
    """
    with TestClient(prod_app) as client:
        response = client.post(
            "/api/sessions", json={"graph_id": "book_planner"}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "session_id" in data
        assert "thread_id" in data
        assert "graph_id" in data


@pytest.mark.asyncio
async def test_list_sessions_via_prod_app(prod_app, _clear_test_db):
    """GET /api/sessions returns sessions created during this TestClient scope."""
    with TestClient(prod_app) as client:
        # Create a session first so we have something to list.
        create_resp = client.post(
            "/api/sessions", json={"graph_id": "book_planner"}
        )
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        # List should return that session.
        list_resp = client.get("/api/sessions")
        assert list_resp.status_code == 200
        sessions = list_resp.json()["sessions"]
        assert len(sessions) >= 1
        ids = {s["session_id"] for s in sessions}
        assert session_id in ids
