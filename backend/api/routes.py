"""FastAPI router with SSE streaming endpoint.

``create_router()`` returns a configured ``APIRouter``.  Call it from the
application factory (e.g. ``app.include_router(create_router())``).

Endpoints
---------
GET /stream — stream structured chunks from LangGraph via SSE.

Query params
~~~~~~~~~~~~
- ``graph_id``: registered graph identifier (default ``book_planner``)
- ``state_json``: JSON-encoded initial state dict
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse


def create_router() -> APIRouter:
    """Build and return the API router with SSE endpoints."""
    router = APIRouter()

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
