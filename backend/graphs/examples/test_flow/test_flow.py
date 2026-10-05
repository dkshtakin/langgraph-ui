"""Test flow graph — interrupt + fake LLM node.

Used for E2E session lifecycle tests without requiring a real LLM.

Graph structure::

    START → pause ───(interrupt when stage=="dialog")──→ (resume signal)
                                            ↓
                                    fake_llm_node → END

State: ``{messages, result, stage}``
"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from backend.graphs.examples.common import FlowState, pause_node


# Node implementations


def fake_llm_node(state: FlowState) -> dict:
    """Fake LLM node — returns a canned AIMessage without calling any model."""
    return {
        "messages": [AIMessage(content="message received")],
        "result": "ok",
        "stage": "done",
    }


# Graph builder


def build() -> object:
    """Build and compile the test-flow graph.

    Returns a compiled LangGraph graph ready to run.
    """
    builder = StateGraph(FlowState)

    builder.add_node("pause", pause_node)
    builder.add_node("fake_llm", fake_llm_node)

    builder.add_edge(START, "pause")
    builder.add_edge("pause", "fake_llm")
    builder.add_edge("fake_llm", END)

    return builder.compile()


# Graph identity (for registry auto-discovery)

name: str = "Test Flow"
