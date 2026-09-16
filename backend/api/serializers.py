"""Message serialization utilities for API responses.

Transforms LangChain / LangGraph message objects stored in checkpoints
into a normalised JSON-friendly schema the frontend expects.
"""

from __future__ import annotations

from typing import Any

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
    text = message.content if message.content else None

    tool_calls: list[dict[str, Any]] = []
    if hasattr(message, "tool_calls") and message.tool_calls:
        for tc in message.tool_calls:
            tool_calls.append(
                {
                    "name": tc["name"],
                    "args": tc["args"],
                }
            )

    return {
        "role": role,
        "text": text,
        "reasoning": None,
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
