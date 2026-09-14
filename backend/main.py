"""FastAPI demo server — mount the API router and serve the React SPA.

Run from the project root with::

    conda run -n lang python -m backend.main

Then open http://127.0.0.1:8000 in a browser to use the app, or
http://127.0.0.1:8000/docs for the API reference.

In development (Vite dev server), the frontend runs on port 5173 with a proxy
to FastAPI — start both servers separately::

    cd frontend && npm run dev
    conda run -n lang python -m backend.main
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Enable debug-level logging so SSE streaming internals are visible.
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.api.routes import create_router
from backend.persistence import get_async_db

_prod_saver = None  # lazily initialised when the first request arrives


_prod_loop_id: int | None = None  # id() of the loop that created _prod_saver


def _get_session_manager():
    """Return the production SessionManager (singleton, created lazily).

    The AsyncSqliteSaver is created inside this function so it sees a
    running event loop — FastAPI request handlers always run one.

    If the saved saver was built for a different loop (e.g. after a
    TestClient context exits in pytest and a new loop starts), we recreate
    it bound to the current loop.  The underlying SQLite file from
    ``get_async_db()`` is shared with the sync connection used by the
    persistence CRUD layer, so checkpoint data and session metadata
    persist across saver instances.

    We compare ``id(loop)`` rather than calling ``loop.is_closed()`` —
    TestClient does not close its loop immediately on exit; the loop
    object stays alive until garbage-collected, so ``is_closed()`` may
    report ``False`` while the current request is already running on a
    *different* loop.
    """
    import asyncio

    global _prod_saver, _prod_loop_id
    current_loop_id = id(asyncio.get_running_loop())
    if _prod_saver is None or _prod_loop_id != current_loop_id:
        from backend.session_manager import SessionManager

        _prod_saver = AsyncSqliteSaver(get_async_db())
        _prod_loop_id = current_loop_id
    return SessionManager(checkpointer=_prod_saver)


app = FastAPI(title="Book Planner API")
app.include_router(create_router(session_manager_factory=_get_session_manager))

# ── SPA static file serving ────────────────────────────────────────────────

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get("/{path:path}")
async def spa_fallback(path: str) -> FileResponse:
    """Serve index.html for any non-API route (SPA client-side routing)."""
    if path.startswith("api/") or path.startswith("docs") or path.startswith("openapi.json"):
        # Let FastAPI handle API/docs routes normally.
        from fastapi import HTTPException

        raise HTTPException(status_code=404)

    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)

    # Dev-mode fallback: nothing to serve yet.
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Frontend not built. Run `npm run build` in frontend/.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
