"""FastAPI router with SSE streaming and session management endpoints.

``create_router()`` returns a configured ``APIRouter``.  Call it from the
application factory (e.g. ``app.include_router(create_router())``).

Endpoints
---------
GET     /api/graphs                        — list registered graphs (id + name).
POST    /api/sessions                      — create a new session, return session_id + thread_id.
GET    /api/sessions/{session_id}/messages — load normalized message history from checkpoints.
POST    /api/resume/{session_id}           — send a user message and stream the graph response via SSE.
PATCH /api/sessions/{session_id}          — rename a session (update title).
DELETE /api/sessions/{session_id}         — delete a session and its checkpoint data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from backend.graph_registry import GRAPH_REGISTRY, get_graph_name

logger = logging.getLogger(__name__)


class CreateSessionRequest(BaseModel):
    """Request body for POST /api/sessions.

    ``graph_id`` defaults to the first registered graph (``examples`` load
    before ``user``), so the endpoint works without a hardcoded graph id.
    """

    graph_id: str | None = None


class RenameSessionRequest(BaseModel):
    """Request body for PATCH /api/sessions/{session_id}."""

    title: str


class ResumeRequest(BaseModel):
    """Request body for POST /api/resume/{session_id}."""

    text: str = ""


def create_router(
    session_manager_factory: Any | None = None,
) -> APIRouter:
    """Build and return the API router with all endpoints.

    Parameters
    ----------
    session_manager_factory : callable | SessionManager | None
        A factory function returning a SessionManager (production — called
        lazily inside each request so AsyncSqliteSaver can acquire its
        event loop), or a pre-built instance/``None`` for tests where
        each test creates its own isolated router.
    """
    import inspect

    from backend.session_manager import SessionManager

    router = APIRouter(prefix="/api")

    # Mutable container: read by inner functions, set once on first access.
    _session_manager: list[Any | None] = [session_manager_factory]

    async def _get_session_manager() -> Any:
        """Return a SessionManager instance.

        Async because the production factory (main.py) needs a running event
        loop to initialise AsyncSqliteSaver; FastAPI's sync Depends runs
        sync-dependencies through anyio's worker-thread pool where no loop
        exists. An async dependency is awaited in-place and stays on the
        event-loop thread.

        The result is cached after first call — this preserves session state
        across requests within a single TestClient lifespan (tests) or server
        process (production). When a production factory is used, the manager
        is recreated if its AsyncSqliteSaver's loop has closed (e.g. after
        TestClient cleanup in pytest) so subsequent requests keep working.
        """
        if _session_manager[0] is None:
            mgr = SessionManager()
            _session_manager[0] = mgr
            return mgr

        obj = _session_manager[0]
        # Production factory — call it, but invalidate cache if the saved
        # manager's saver was built for a different loop (e.g. after
        # TestClient exits and pytest starts a new loop).
        if inspect.isfunction(obj) or inspect.isbuiltin(obj) or inspect.ismethod(obj):
            result = obj()
            if inspect.isawaitable(result):
                result = await result
            if hasattr(result, "_checkpointer"):
                saver = result._checkpointer
                # Compare loop id, not is_closed(): TestClient keeps the old
                # loop object alive until GC, so is_closed() may still be False
                # while we are already running on a brand-new loop.
                import asyncio

                current_loop_id = id(asyncio.get_running_loop())
                if hasattr(saver, "loop") and id(saver.loop) != current_loop_id:
                    _session_manager[0] = session_manager_factory  # restore factory so next call recreates with fresh loop
            _session_manager[0] = result
            return result
        return obj

    # ── graph listing ────────────────────────────────────────────────────

    @router.get("/graphs")
    async def list_graphs() -> dict[str, Any]:
        """Return a dict of registered graph IDs to their metadata."""
        from backend.graph_registry import list_graphs as list_registered_graphs

        graphs = list_registered_graphs()
        return {"graphs": graphs}

    # ── session management ───────────────────────────────────────────────

    @router.get("/sessions")
    async def list_sessions(
        mgr: Any = Depends(_get_session_manager),
    ) -> dict[str, Any]:
        """Return the list of sessions with lazy-computed status.

        Status is determined read-only by inspecting checkpoint history;
        graph state is not modified.
        """
        rows = mgr.list_all_sessions()
        statuses = await asyncio.gather(
            *(mgr.get_session_status(r["session_id"]) for r in rows)
        )
        for row, status in zip(rows, statuses):
            row["status"] = status or row["status"]
        return {"sessions": rows}

    @router.post("/sessions")
    async def create_session(
        body: CreateSessionRequest,
        mgr: Any = Depends(_get_session_manager),
    ) -> dict[str, str]:
        """Create a new session for *body.graph_id*.

        Returns
        -------
        dict with ``session_id``, ``thread_id``, ``graph_id``, and ``graph_name``.
        """
        if not GRAPH_REGISTRY:
            raise HTTPException(
                status_code=503,
                detail="No graphs are registered — cannot create a session.",
            )
        return mgr.create_session(body.graph_id)

    @router.patch("/sessions/{session_id}")
    async def rename_session(
        session_id: str,
        body: RenameSessionRequest,
        mgr: Any = Depends(_get_session_manager),
    ) -> dict[str, Any]:
        """Rename *session_id* to *body.title*.

        Returns the updated session metadata on success (200) or 404 if not found.
        """
        session = mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        result = mgr.rename_session(session_id, body.title)
        return result

    @router.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        mgr: Any = Depends(_get_session_manager),
    ) -> dict[str, bool]:
        """Delete a session and its checkpoint data.

        Returns
        -------
        dict with ``deleted`` set to ``True`` on success.
        """
        session = mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        mgr.delete_session(session_id)
        return {"deleted": True}

    @router.get("/sessions/{session_id}/messages")
    async def get_session_messages(
        session_id: str,
        mgr: Any = Depends(_get_session_manager),
    ) -> dict[str, Any]:
        """Return the normalised message history for *session_id*.

        Loads the latest checkpoint via ``aget_tuple()``, extracts
        ``channel_values["messages"]``, serialises each message, and returns
        them as ``{"messages": [...]}``.  Falls back to scanning all
        checkpoints with ``alist()`` when the latest checkpoint has no
        messages (e.g. terminal node cleared the channel).

        Returns 404 if the session does not exist.
        """
        session = mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        thread_id = session["thread_id"]

        # Lazy-compile the graph if it hasn't been created yet (restored session).
        if "graph" not in session:
            compiled_graph = GRAPH_REGISTRY[session["graph_id"]]
            session["graph"] = compiled_graph.builder.compile(
                checkpointer=mgr._checkpointer
            )

        graph = session["graph"]
        config = {"configurable": {"thread_id": thread_id}}

        from backend.api.serializers import serialize_messages

        # Try the latest checkpoint first.
        try:
            latest = await graph.checkpointer.aget_tuple(config)
        except Exception:
            latest = None

        if latest is not None:
            channel_values = latest.checkpoint.get("channel_values", {})
            raw_messages = channel_values.get("messages", [])
        else:
            raw_messages = []

        # Fallback: scan all checkpoints for the last one with messages.
        if not raw_messages:
            all_checkpoints = []
            async for cp in graph.checkpointer.alist(config):
                all_checkpoints.append(cp)
            for cp in reversed(all_checkpoints):
                msgs = cp.checkpoint.get("channel_values", {}).get("messages", [])
                if msgs:
                    raw_messages = msgs
                    break

        return {"messages": serialize_messages(raw_messages)}

    @router.post("/resume/{session_id}")
    async def resume_session(
        session_id: str,
        body: ResumeRequest,
        request: Request,
        mgr: Any = Depends(_get_session_manager),
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

        session = mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        thread_id = session["thread_id"]

        # Lazy-compile the graph if it hasn't been created yet (restored session).
        if "graph" not in session:
            compiled_graph = GRAPH_REGISTRY[session["graph_id"]]
            session["graph"] = compiled_graph.builder.compile(
                checkpointer=mgr._checkpointer
            )

        graph = session["graph"]
        config = {"configurable": {"thread_id": thread_id}}

        async def event_iterator() -> AsyncIterator[bytes]:
            from backend.streaming_parser import flush_buffer, parse_reasoning

            try:
                history = [c async for c in graph.checkpointer.alist(config)]

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
                                    {"event": sse_event, "data": {"name": name, "args": args}}
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
