"""Shared graph components for test_flow and llm_flow.

Both graphs use the same ``FlowState`` shape and an identical ``pause_node``
that interrupts when ``stage == "dialog"``.  Each consumer imports these here
instead of duplicating the definitions.
"""

from __future__ import annotations

from typing_extensions import TypedDict

from langchain.messages import AnyMessage
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from typing_extensions import Annotated


class FlowState(TypedDict):
    """Shared state shape for test-flow and llm-flow graphs."""

    messages: Annotated[list[AnyMessage], add_messages]
    result: str
    stage: str


def pause_node(state: FlowState) -> dict:
    """Pause the graph when ``stage == "dialog"``.

    On resume the graph continues past this node without re-interrupting.
    """
    if state.get("stage", "dialog") == "dialog":
        interrupt({"reason": "waiting_for_user_input"})
    return {"messages": [], "result": "", "stage": "next"}
