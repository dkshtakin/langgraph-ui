"""SSE streaming wrapper over LangGraph ``stream_events`` v3.

Iterates the LangGraph event stream, parses reasoning boundaries via
:py:mod:`backend.streaming_parser`, and yields structured SSE events for the
frontend.

Example usage in a FastAPI route::

    from backend.sse_streaming import stream_langgraph_events

    async def event_iterator():
        for sse_chunk in stream_langgraph_events(graph, initial_state):
            yield format_sse(sse_chunk) + "\\\\n\\\\n"
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from backend.streaming_parser import flush_buffer, parse_reasoning


def _make_event(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Construct an SSE event payload."""
    return {"event": event_type, "data": data}


def stream_langgraph_events(
    graph: Any,
    initial_state: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Stream structured SSE chunks from a LangGraph graph.

    Wraps ``graph.stream_events(state, version="v3")``, filters the ``messages``
    channel for ``text-delta`` and ``content-block-finish`` events, feeds text
    through the reasoning parser, and emits typed SSE events.

    Yields
    ------
    dict with keys ``event`` (str) and ``data`` (dict).
    """
    from langgraph.types import StreamMode

    output_buffer = ""
    in_reasoning = False
    all_chunks: list[dict] = []

    stream = graph.stream_events(initial_state, version="v3")

    for event in stream:
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

        # ── text-delta → parse_reasoning ───────────────────────────
        if msg_data.get("event") == "content-block-delta":
            delta = msg_data.get("delta", {}) or {}
            if delta.get("type") == "text-delta":
                text = delta.get("text", "")
                output_buffer, in_reasoning, new_chunks = parse_reasoning(
                    text, output_buffer, in_reasoning
                )
                all_chunks.extend(new_chunks)
                for chunk in new_chunks:
                    yield _make_event(chunk["type"], {"content": chunk["content"]})

        # ── content-block-finish → flush + tool call ───────────────
        elif msg_data.get("event") == "content-block-finish":
            output_buffer, in_reasoning, flushed = flush_buffer(
                output_buffer, in_reasoning
            )
            all_chunks.extend(flushed)
            for chunk in flushed:
                yield _make_event(chunk["type"], {"content": chunk["content"]})

            # Check for tool call in the completed block.
            content_block = msg_data.get("content") or {}
            if content_block.get("type") == "tool_call":
                name = content_block.get("name", "")
                args = content_block.get("args", {})
                yield _make_event(
                    "tool_call", {"name": name, "args": json.dumps(args)}
                )

    # Final flush at stream end.
    output_buffer, in_reasoning, final_flushed = flush_buffer(
        output_buffer, in_reasoning
    )
    all_chunks.extend(final_flushed)
    for chunk in final_flushed:
        yield _make_event(chunk["type"], {"content": chunk["content"]})
