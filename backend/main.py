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

from backend.api.routes import create_router

app = FastAPI(title="Book Planner API")
app.include_router(create_router())

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
