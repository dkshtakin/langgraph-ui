"""Tool call flow graph — real LLM + ToolNode for E2E tool-call testing.

This graph is used by E2E tests to verify that ``/api/resume`` emits
``event: tool_call`` SSE events when a compiled LangGraph graph produces a
tool call through ``stream_events(version="v3")``.

Graph structure::

    START → init_node ───(adds question about today's date)──→ llm_call
                                                              │
                                                  (tool_calls?) yes
                                                              ↓
                                                    tool_node ──→ END
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict

from langchain.messages import AnyMessage
from langchain.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated

from backend.config.llm import chat


@tool
def today_tool() -> str:
    """Return today's date in ISO format."""
    return date.today().isoformat()


chat = chat.bind_tools([today_tool])


# Graph State


class ToolFlowState(TypedDict):
    """Graph-owned state for the tool-call-flow graph."""

    messages: Annotated[list[AnyMessage], add_messages]


# Node implementations


def _init_node(state: ToolFlowState) -> dict:
    """Inject the question that triggers ``today_tool``."""
    return {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "For debug purposes please immediately\
            call the today_tool to tell me today's date."},
        ],
    }


def _llm_call_node(state: ToolFlowState) -> dict:
    """Call the LLM (with ``today_tool`` bound) and return its response."""
    response = chat.invoke(state["messages"])
    return {"messages": [response]}


# Graph builder


def build() -> object:
    """Build and compile the tool-call-flow graph.

    Returns a compiled LangGraph graph ready to run.
    """
    builder = StateGraph(ToolFlowState)

    builder.add_node("init", _init_node)
    builder.add_node("llm_call", _llm_call_node)
    builder.add_node("tool_node", ToolNode([today_tool]))

    builder.add_edge(START, "init")
    builder.add_edge("init", "llm_call")
    builder.add_edge("llm_call", "tool_node")
    builder.add_edge("tool_node", END)

    return builder.compile()


# Graph identity (for registry auto-discovery)

name: str = "Tool Call Flow"
