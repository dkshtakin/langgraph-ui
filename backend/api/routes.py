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
import logging
import traceback
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CreateSessionRequest(BaseModel):
    """Request body for POST /api/sessions."""

    graph_id: str = "book_planner"


class ResumeRequest(BaseModel):
    """Request body for POST /api/resume/{session_id}."""

    text: str = ""


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
        graph state, then starts or resumes execution using
        ``astream_events(version="v3")``.  If the graph pauses at an interrupt
        an ``interrupt`` event is emitted; otherwise a ``done`` event signals
        completion after streaming any ``answer``/``reasoning`` chunks.

        Parameters
        ----------
        session_id : str
            The session ID returned by ``POST /api/sessions``.
        body : ResumeRequest
            A single user message string (wrapped internally as HumanMessage).
        """
        from langchain_core.messages import HumanMessage

        from backend.session_manager import SessionManager

        mgr = SessionManager()
        session = mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        thread_id = session["thread_id"]
        graph = session["graph"]
        config = {"configurable": {"thread_id": thread_id}}

        async def event_iterator() -> AsyncIterator[bytes]:
            from backend.streaming_parser import flush_buffer, parse_reasoning

            try:
                history = list(graph.checkpointer.list(config))

                if body.text and history:
                    human_msg = HumanMessage(content=body.text)
                    input_val = Command(
                        resume=body.text, update={"messages": [human_msg]}
                    )
                else:
                    # Fresh session or init-only call — the graph
                    # self-initialises state via its TypedDict; no user
                    # message is injected.
                    input_val = {}

                run = await graph.astream_events(
                    input_val, version="v3", config=config
                )

                output_buffer = ""
                in_reasoning = False
                graph_error: Exception | None = None

                try:
                    async for event in run:
                        channel = event.get("method", "")
                        if channel != "messages":
                            continue

                        params = event.get("params", {})
                        data_list = params.get("data", [])
                        if not data_list:
                            continue

                        msg_data = data_list[0]
                        if not isinstance(msg_data, dict):
                            continue

                        logger.debug("[resume] event from graph: %s", msg_data.get("event"))

                        if msg_data.get("event") == "content-block-delta":
                            delta = msg_data.get("delta", {}) or {}
                            if delta.get("type") == "text-delta":
                                text = delta.get("text", "")
                                (
                                    output_buffer,
                                    in_reasoning,
                                    new_chunks,
                                ) = parse_reasoning(
                                    text, output_buffer, in_reasoning
                                )
                                for chunk in new_chunks:
                                    logger.debug("[resume] yielding SSE event=%s content=%r", chunk["type"], chunk["content"][:50])
                                    yield _format_sse(
                                        {"event": chunk["type"], "data": {"content": chunk["content"]}}
                                    ) + "\n\n"

                        elif msg_data.get("event") == "content-block-finish":
                            (
                                output_buffer,
                                in_reasoning,
                                flushed,
                            ) = flush_buffer(output_buffer, in_reasoning)
                            for chunk in flushed:
                                yield _format_sse(
                                    {"event": chunk["type"], "data": {"content": chunk["content"]}}
                                ) + "\n\n"

                            # Emit tool call events — mirrors sse_streaming.py handler.
                            # Valid calls use event "tool_call"; invalid ones keep their
                            # original type so the frontend can distinguish them.
                            content_block = msg_data.get("content") or {}
                            ct = content_block.get("type", "")
                            if ct in ("tool_call", "invalid_tool_call"):
                                name = content_block.get("name", "")
                                args = content_block.get("args", {})
                                sse_event = "tool_call" if ct == "tool_call" else "invalid_tool_call"
                                yield _format_sse(
                                    {"event": sse_event, "data": {"name": name, "args": json.dumps(args)}}
                                ) + "\n\n"
                except Exception as exc:
                    tb = traceback.format_exc()
                    logger.error("[resume] graph iteration error:\n%s", tb)
                    graph_error = (exc, tb)

                # Flush any remaining buffered text — mirrors the final flush
                # in sse_streaming.py before yielding the end marker.
                if graph_error is None:
                    output_buffer, in_reasoning, final_flushed = flush_buffer(
                        output_buffer, in_reasoning
                    )
                    for chunk in final_flushed:
                        logger.debug("[resume] final flush SSE event=%s", chunk["type"])
                        yield _format_sse(
                            {"event": chunk["type"], "data": {"content": chunk["content"]}}
                            ) + "\n\n"

                # Determine final event — error takes priority over done/interrupt
                if graph_error is not None:
                    exc, tb = graph_error
                    yield _format_sse(
                        {"event": "error", "data": {"detail": f"{type(exc).__name__}: {exc}\n\n{tb}"}}
                    ) + "\n\n"
                else:
                    try:
                        was_interrupted = await run.interrupted()
                        logger.debug("[resume] interrupted=%s", was_interrupted)
                    except Exception as ierr:
                        logger.error("[resume] interrupted() raised: %s", ierr)
                        was_interrupted = False

                    if was_interrupted:
                        interrupts_list = await run.interrupts()
                        if interrupts_list:
                            interrupt_value = (
                                interrupts_list[0].value if hasattr(interrupts_list[0], "value") else interrupts_list[0]
                            ) or {}
                            reason = interrupt_value.get("reason", "unknown") if isinstance(interrupt_value, dict) else str(interrupt_value)
                        else:
                            reason = "unknown"
                        logger.debug("[resume] yielding interrupt event, reason=%s", reason)
                        yield _format_sse(
                            {"event": "interrupt", "data": {"reason": reason}}
                        ) + "\n\n"
                    else:
                        logger.debug("[resume] yielding done event")
                        yield _format_sse({"event": "done", "data": {}}) + "\n\n"

            except Exception as exc:
                tb = traceback.format_exc()
                yield _format_sse(
                    {"event": "error", "data": {"detail": f"{type(exc).__name__}: {exc}\n\n{tb}"}}
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
                tb = traceback.format_exc()
                yield _format_sse({"event": "error", "data": {"detail": f"{type(exc).__name__}: {exc}\n\n{tb}"}}) + "\n\n"

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
