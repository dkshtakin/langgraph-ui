"""Test flow graph
"""

from __future__ import annotations

from typing_extensions import TypedDict, Annotated

from langchain.messages import AnyMessage
from langchain_core.messages import AIMessage

from langgraph.types import interrupt
from langgraph.graph.message import add_messages
from langgraph.graph import END, START, StateGraph


class FlowState(TypedDict):
    """Shared state shape for test-flow and llm-flow graphs."""

    messages: Annotated[list[AnyMessage], add_messages]
    result: str
    stage: str


def pause_node(state: FlowState) -> dict:
    """Pause the graph when ``stage == 'dialog'``.

    On resume the graph continues past this node without re-interrupting.
    """
    if state.get('stage', 'dialog') == 'dialog':
        interrupt({'reason': 'waiting_for_user_input'})
    return {'messages': [], 'result': '', 'stage': 'next'}



def fake_llm_node(state: FlowState) -> dict:
    """Fake LLM node — returns a canned AIMessage without calling any model."""
    return {
        'messages': [AIMessage(content='message received')],
        'result': 'ok',
        'stage': 'done',
    }


graph = StateGraph(FlowState)

graph.add_node('pause', pause_node)
graph.add_node('fake_llm', fake_llm_node)

graph.add_edge(START, 'pause')
graph.add_edge('pause', 'fake_llm')
graph.add_edge('fake_llm', END)

graph = graph.compile()
