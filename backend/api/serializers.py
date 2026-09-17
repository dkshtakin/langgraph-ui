"""Message serialization utilities for API responses.

Transforms LangChain / LangGraph message objects stored in checkpoints
into a normalised JSON-friendly schema the frontend expects.
"""

from __future__ import annotations

from typing import Any

def _extract_text_from_content(content: Any) -> str | None:
    """Pull plain text from LangChain structured content (list of dicts).

    LangChain AIMessage / ToolMessage can store content as a list of blocks
    like ``[{"type": "text", "text": "..."}]`` instead of a plain string.
    Returns the concatenated text, or None if no text blocks are found.
    """
    if not isinstance(content, list):
        return str(content) if content else None

    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
            elif "text" in block and isinstance(block["text"], str):
                parts.append(block["text"])
        elif isinstance(block, str) and block:
            parts.append(block)
    return "".join(parts) if parts else None


_ROLE_MAP: dict[str, str] = {
    "system": "system",
    "human": "user",
    "ai": "assistant",
    "tool": "tool",
}


def serialize_message(message: Any) -> dict[str, Any]:
    """Normalise a single LangChain message to API schema.

    Parameters
    ----------
    message : AnyMessage
        A LangChain message instance (SystemMessage, HumanMessage, AIMessage,
        ToolMessage, etc.).

    Returns
    -------
    dict
        Normalised message with keys ``role``, ``text``, ``reasoning``,
        ``toolCalls``.
    """
    role = _ROLE_MAP.get(message.type, message.type)

    content = message.content
    if content is None:
        text = None
    elif isinstance(content, str):
        text = content
    else:
        # ToolMessage / AIMessage can carry non-string content (dict, list).
        # Extract plain text from LangChain structured format.
        text = _extract_text_from_content(content)

    tool_calls: list[dict[str, Any]] = []
    if hasattr(message, "tool_calls") and message.tool_calls:
        for tc in message.tool_calls:
            tool_calls.append(
                {
                    "name": tc["name"],
                    "args": tc["args"],
                }
            )

  # Parse reasoning tags from assistant text — mirrors the streaming parser.
    reasoning_text: str | None = None
    clean_answer: str | None = None
    if role == "assistant" and text:
        from backend.streaming_parser import flush_buffer, parse_reasoning

        buf = ""
        in_reasoning = False
        answer_parts: list[str] = []
        for chunk_text in [text]:
            buf, in_reasoning, chunks = parse_reasoning(
                chunk_text, buf, in_reasoning
            )
            for c in chunks:
                if c["type"] == "reasoning":
                    reasoning_text = (reasoning_text or "") + c["content"]
                else:
                    answer_parts.append(c["content"])
        # Flush any trailing buffered text.
        _, _, final_chunks = flush_buffer(buf, in_reasoning)
        for c in final_chunks:
            if c["type"] == "reasoning":
                reasoning_text = (reasoning_text or "") + c["content"]
            else:
                answer_parts.append(c["content"])
        if not reasoning_text:
            reasoning_text = None
        clean_answer = "".join(answer_parts) if answer_parts else text

    return {
        "role": role,
        "text": clean_answer or text,
        "reasoning": reasoning_text,
        "toolCalls": tool_calls,
    }


def serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Normalise a list of LangChain messages to API schema.

    Parameters
    ----------
    messages : list[AnyMessage]
        Raw messages from a LangGraph checkpoint.

    Returns
    -------
    list[dict]
        Normalised message dicts sorted in chronological order (as stored).
    """
    return [serialize_message(m) for m in messages]
