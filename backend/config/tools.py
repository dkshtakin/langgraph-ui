"""Shared tools and tool registry."""

from __future__ import annotations

from datetime import date

from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command


@tool
def end_dialog(runtime: ToolRuntime) -> Command:
    """Call when the user is satisfied with the current work and wants to finalize."""
    return Command(
        update={
            "messages": [
                ToolMessage(
                    "Stage updated finished", tool_call_id=runtime.tool_call_id
                )
            ],
            "stage": "summary",
        }
    )


@tool
def today_tool() -> str:
    """Return today's date in ISO format."""
    return date.today().isoformat()


TOOLS = [end_dialog]
