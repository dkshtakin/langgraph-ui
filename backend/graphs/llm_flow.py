"""LLM flow graph — interrupt + real LLM node.

Used for E2E session lifecycle tests with a real model call.

Graph structure::

    START → pause ───(interrupt when stage=="dialog")──→ (resume signal)
                                            ↓
                                    real_llm_node → END

State: ``{messages, result, stage}``
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.config.llm import chat
from backend.graphs.common import FlowState, pause_node


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


def real_llm_node(state: FlowState) -> dict:
    """Real LLM node — calls the configured model via ``chat.invoke(...)``."""
    response = chat.invoke(state["messages"])
    return {
        "messages": [response],
        "result": "ok",
        "stage": "done",
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build() -> object:
    """Build and compile the llm-flow graph.

    Returns a compiled LangGraph graph ready to run.
    """
    builder = StateGraph(FlowState)

    builder.add_node("pause", pause_node)
    builder.add_node("real_llm", real_llm_node)

    builder.add_edge(START, "pause")
    builder.add_edge("pause", "real_llm")
    builder.add_edge("real_llm", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Graph identity (for registry auto-discovery)
# ---------------------------------------------------------------------------

id: str = "llm_flow"
name: str = "LLM Flow"
