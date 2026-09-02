"""FastAPI router with SSE streaming and session management endpoints.

``create_router()`` returns a configured ``APIRouter``.  Call it from the
application factory (e.g. ``app.include_router(create_router())``).

Endpoints
---------
GET  /api/graphs          — list registered graphs (id + name).
POST /api/sessions        — create a new session, return session_id + thread_id.
POST /api/messages/{session_id} — send a message into a session and stream the response.
GET  /stream              — legacy SSE streaming endpoint (query-param based).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    """Request body for POST /api/sessions."""

    graph_id: str = "book_planner"


def create_router() -> APIRouter:
    """Build and return the API router with all endpoints."""
    router = APIRouter(prefix="/api")

    # ── graph listing ────────────────────────────────────────────────────

    @router.get("/graphs")
    async def list_graphs() -> dict[str, Any]:
        """Return a dict of registered graph IDs to their metadata."""
        from backend import list_graphs

        graphs = list_graphs()
        return {"graphs": graphs}

    # ── session management ───────────────────────────────────────────────

    @router.post("/sessions")
    async def create_session(body: CreateSessionRequest) -> dict[str, str]:
        """Create a new session for *body.graph_id*.

        Returns
        -------
        dict with ``session_id``, ``thread_id``, and ``graph_id``.
        """
        from backend.session_manager import SessionManager

        mgr = SessionManager()
        return mgr.create_session(body.graph_id)

    @router.post("/messages/{session_id}")
    async def send_message(
        session_id: str,
        message: dict[str, Any],
        request: Request,
    ) -> StreamingResponse:
        """Send a message into *session_id* and stream the graph response via SSE.

        Parameters
        ----------
        session_id : str
            The session ID returned by ``POST /api/sessions``.
        message : dict
            A state fragment to merge into the graph (e.g. ``{"messages": [...]}``).
        """
        from backend.session_manager import SessionManager
        from langgraph.types import Command

        mgr = SessionManager()
        session = mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        thread_id = session["thread_id"]
        graph = session["graph"]

        async def event_iterator() -> AsyncIterator[bytes]:
            try:
                result = graph.invoke(message, config={"configurable": {"thread_id": thread_id}})

                # If the graph paused, yield an interrupt event and stop.
                if "__interrupt__" in result:
                    yield _format_sse(
                        {
                            "event": "interrupt",
                            "data": {"reason": result["__interrupt__"][0].value},
                        }
                    ) + "\n\n"
                    return

                # Otherwise stream the final result as JSON.
                yield _format_sse(
                    {"event": "result", "data": result}
                ) + "\n\n"
            except Exception as exc:
                yield _format_sse(
                    {"event": "error", "data": {"detail": str(exc)}}
                ) + "\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── legacy SSE stream endpoint ───────────────────────────────────────

    @router.get("/stream")
    async def stream(
        request: Request,
        graph_id: str = Query("book_planner", description="Registered graph ID"),
        state_json: str | None = Query(None, description="Initial JSON-encoded state"),
    ) -> StreamingResponse:
        """SSE endpoint — streams structured chunks from LangGraph."""
        from backend.graph_registry import registry

        # Parse optional initial state
        if state_json:
            initial_state = json.loads(state_json)
        else:
            initial_state = {"messages": [], "stage": "dialog", "summary": None}

        # Resolve graph — raises 404 if not found (handled by middleware)
        try:
            graph_instance = registry.get(graph_id)
        except KeyError:
            available = ", ".join(registry.list())
            return StreamingResponse(
                _error_stream(f"Unknown graph: {graph_id}. Available: {available}"),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )

        # Iterate SSE events — abort on client disconnect
        async def event_iterator() -> AsyncIterator[bytes]:
            try:
                from backend.sse_streaming import stream_langgraph_events

                for sse_chunk in stream_langgraph_events(graph_instance, initial_state):
                    if request.client_disconnected:
                        break
                    yield _format_sse(sse_chunk) + "\n\n"
            except Exception as exc:
                yield _format_sse({"event": "error", "data": {"detail": str(exc)}}) + "\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # disable nginx buffering
            },
        )

    return router


# ── SSE helpers ──────────────────────────────────────────────────────────


def _format_sse(data: dict[str, Any]) -> str:
    """Format a chunk as an SSE message with ``event`` + ``data`` fields."""
    lines = []
    if event := data.get("event"):
        lines.append(f"event: {event}")
    # Serialize the payload (handles nested dicts / lists).
    lines.append(f"data: {json.dumps(data['data'], ensure_ascii=False)}")
    return "\n".join(lines)


async def _error_stream(message: str) -> AsyncIterator[str]:
    """Yield a single SSE error event."""
    yield _format_sse({"event": "error", "data": {"detail": message}}) + "\n\n"
