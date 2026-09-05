"""FastAPI demo server — mount the API router and serve Swagger UI.

Run from the project root with::

    conda run -n lang python -m backend.main

Then open http://127.0.0.1:8000/docs in a browser to test every endpoint.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.api.routes import create_router

app = FastAPI(title="Book Planner API")
app.include_router(create_router())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
