"""Tests for interrupt detection in stream_events(version='v3').

Covers:
- Detecting interrupt via run.interrupted() after iterating events
- Retrieving interrupt payload via run.interrupts()
- Distinguishing "graph paused" vs "graph completed" at end of stream
"""

from __future__ import annotations

import asyncio
from typing import TypedDict

import pytest
from langchain.messages import AnyMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from typing_extensions import Annotated


# Minimal test graph — same pattern as pause_node in common.py


class _MsgState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    stage: str


def _pause_node(state: _MsgState) -> dict:
    """Node that interrupts when stage is 'dialog'."""
    if state["stage"] == "dialog":
        interrupt({"reason": "waiting_for_input"})
    return {"messages": [], "stage": "next"}


def _finish_node(state: _MsgState) -> dict:
    """Terminal node."""
    return {"messages": [], "stage": "done"}


_test_builder = StateGraph(_MsgState)
_test_builder.add_node("pause", _pause_node)
_test_builder.add_node("finish", _finish_node)
_test_builder.add_edge(START, "pause")
_test_builder.add_conditional_edges(
    "pause",
    lambda s: "finish" if s["stage"] == "next" else "pause",
    {"pause": "pause", "finish": "finish"},
)
_test_builder.add_edge("finish", END)


@pytest.fixture(scope="module")
def interrupt_graph():
    """Compile a graph with a pause node."""
    from langgraph.checkpoint.memory import InMemorySaver

    return _test_builder.compile(checkpointer=InMemorySaver())


# Helpers


async def collect_events(graph, input_state, config):
    """Run stream_events(v3) and collect all events + final status."""
    run = await graph.astream_events(input_state, version="v3", config=config)
    events = []
    async for event in run:
        events.append(event)

    interrupted = await run.interrupted()
    interrupts_list = await run.interrupts()
    return events, interrupted, interrupts_list


# Tests


@pytest.mark.asyncio
async def test_stream_events_v3_detects_interrupt(interrupt_graph):
    """After iterating stream_events(v3), interrupted() returns True."""
    import uuid

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    events, was_interrupted, interrupts_list = await collect_events(
        interrupt_graph,
        {"messages": [], "stage": "dialog"},
        config,
    )
    assert was_interrupted is True
    assert len(interrupts_list) == 1
    # Interrupt objects expose their payload via .value
    interrupt_value = interrupts_list[0].value if hasattr(interrupts_list[0], "value") else interrupts_list[0]
    assert interrupt_value["reason"] == "waiting_for_input"


@pytest.mark.asyncio
async def test_stream_events_v3_completed_graph_returns_false(interrupt_graph):
    """After a completed run, interrupted() returns False."""
    import uuid

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    # First invoke to reach the interrupt (pause) state.
    await collect_events(
        interrupt_graph,
        {"messages": [], "stage": "dialog"},
        config,
    )
    # Now resume — graph should complete.
    events, was_interrupted, interrupts_list = await collect_events(
        interrupt_graph,
        Command(resume="user reply"),
        config,
    )
    assert was_interrupted is False
    assert interrupts_list == []


@pytest.mark.asyncio
async def test_stream_events_v3_no_history_is_not_interrupted(interrupt_graph):
    """A fresh graph with no prior history runs to completion."""
    import uuid

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    events, was_interrupted, interrupts_list = await collect_events(
        interrupt_graph,
        {"messages": [], "stage": "next"},  # stage != dialog, so no interrupt
        config,
    )
    assert was_interrupted is False
    assert interrupts_list == []
