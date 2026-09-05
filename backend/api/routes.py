"""FastAPI router with SSE streaming and session management endpoints.

``create_router()`` returns a configured ``APIRouter``.  Call it from the
application factory (e.g. ``app.include_router(create_router())``).

Endpoints
---------
GET     /api/graphs            — list registered graphs (id + name).
POST    /api/sessions          — create a new session, return session_id + thread_id.
POST    /api/resume/{session_id} — send a user message and stream the graph response via SSE.
DELETE  /api/sessions/{session_id} — delete a session and its checkpoint data.
GET     /stream                — legacy SSE streaming endpoint (query-param based).
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


class ResumeRequest(BaseModel):
    """Request body for POST /api/resume/{session_id}."""

    text: str


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

    @router.delete("/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, bool]:
        """Delete a session and its checkpoint data.

        Returns
        -------
        dict with ``deleted`` set to ``True`` on success.
        """
        from backend.session_manager import SessionManager

        mgr = SessionManager()
        session = mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        mgr.delete_session(session_id)
        return {"deleted": True}

    @router.post("/resume/{session_id}")
    async def resume_session(
        session_id: str,
        body: ResumeRequest,
        request: Request,
    ) -> StreamingResponse:
        """Send a user message into *session_id* and stream the graph response via SSE.

        The endpoint wraps *body.text* in a ``HumanMessage``, adds it to the
        graph state, then starts or resumes execution.  If the graph pauses at
        an interrupt an ``interrupt`` event is emitted; otherwise a ``result``
        event carries the final output.

        Parameters
        ----------
        session_id : str
            The session ID returned by ``POST /api/sessions``.
        body : ResumeRequest
            A single user message string (wrapped internally as HumanMessage).
        """
        from langchain_core.messages import HumanMessage
        from langgraph.types import Command

        from backend.session_manager import SessionManager

        mgr = SessionManager()
        session = mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        thread_id = session["thread_id"]
        graph = session["graph"]
        human_msg = HumanMessage(content=body.text)
        config = {"configurable": {"thread_id": thread_id}}

        async def event_iterator() -> AsyncIterator[bytes]:
            try:
                # Determine whether this is a fresh invocation or a resume after
                # an interrupt by checking if the thread already has checkpoint
                # history.  A thread with history is either mid-interrupt (resume)
                # or post-completion (fresh logical run — still use Command).
                history = list(graph.checkpointer.list(config))

                if history:
                    result = graph.invoke(
                        Command(resume=body.text, update={"messages": [human_msg]}),
                        config=config,
                    )
                else:
                    # First invocation — start the graph with initial state.
                    result = graph.invoke(
                        {"messages": [human_msg], "stage": "dialog"},
                        config=config,
                    )

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
                # Convert LangChain messages to dicts for JSON serialization.
                serializable_result = {
                    k: _serialize_messages(v) if k == "messages" else v
                    for k, v in result.items()
                }
                yield _format_sse(
                    {"event": "result", "data": serializable_result}
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


def _serialize_messages(value: Any) -> Any:
    """Convert LangChain message objects to JSON-serializable dicts."""
    from langchain_core.messages import AIMessage, HumanMessage, MessageLikeRepresentation

    if isinstance(value, list):
        return [_serialize_single_message(m) for m in value]
    return value


def _serialize_single_message(msg: MessageLikeRepresentation) -> dict:
    """Serialize a single LangChain message to a plain dict."""
    from langchain_core.messages import AIMessage, HumanMessage

    if isinstance(msg, (HumanMessage, AIMessage)):
        return msg.model_dump()
    return msg


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
