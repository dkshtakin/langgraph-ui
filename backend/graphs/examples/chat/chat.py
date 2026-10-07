"""LangGraph chat template.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from typing_extensions import TypedDict

from langgraph.graph import MessagesState

from pathlib import Path
from datetime import date
from collections.abc import Callable
from pydantic import BaseModel, Field
from typing import Optional, TypedDict, List
from typing_extensions import Annotated

from langgraph.runtime import Runtime
from langgraph.prebuilt import ToolNode
from langgraph.graph import MessagesState
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain.messages import ToolMessage
from langchain.messages import AnyMessage
from langchain_core.messages import messages_to_dict
from langchain.tools import tool, ToolRuntime
from langchain.tools.tool_node import ToolCallRequest
from langchain.agents import create_agent, AgentState
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import wrap_tool_call, AgentMiddleware
from langchain_deepseek import ChatDeepSeek


import os
from dotenv import load_dotenv


load_dotenv()


chat = ChatDeepSeek(
    base_url=os.environ.get('LLM_BASE_URL', 'http://127.0.0.1:8081/v1'),
    api_key=os.environ.get('LLM_API_KEY', 'empty'),
    model=os.environ.get('LLM_NAME', ''),
    streaming=True,
    extra_body={
        "chat_template_kwargs": {
            "enable_thinking": True,
            "reasoning_effort": "medium",
        },
        "reasoning_format": "deepseek"
    },
)


class ToolCallMiddleware(AgentMiddleware):
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        try:
            return handler(request)
        except Exception as e:
            return ToolMessage(
                content=f'Tool error during tool execution: ({e})',
                tool_call_id=request.tool_call['id'],
            )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        try:
            return await handler(request)
        except Exception as e:
            return ToolMessage(
                content=f'Tool error during tool execution: ({e})',
                tool_call_id=request.tool_call['id'],
            )


@tool
def end_dialog(runtime: ToolRuntime) -> Command:
    """Call when the user is satisfied with the current work and wants to finish the conversation."""
    return Command(
        update={
            'messages': runtime.state['messages'] +
                [ToolMessage(
                    'Successfully called end_dialog tool', tool_call_id=runtime.tool_call_id
                )],
            'stage': 'finish',
        },
        graph=Command.PARENT
    )


@tool
def today_tool() -> str:
    """Return today's date in ISO format."""
    return date.today().isoformat()


@tool
def multiply_tool(a: int, b: int) -> int:
    """Return dot product of a and b"""
    return a * b


TOOLS = [end_dialog, today_tool, multiply_tool]


class ChatState(MessagesState):
    stage: str


def init_node(state: ChatState) -> dict:
    return {
        'messages': [
            SystemMessage(content='You are helpful assistant'),
        ],
        'stage': 'dialog',
    }


async def user_input_node(state: ChatState) -> Dict[str, Any]:
    interrupt({'reason': f'Waiting for user input'})
    return


def should_finish(state: ChatState) -> str:
    return state['stage'] == 'finish'


agent = create_agent(
    model=chat,
    tools=TOOLS,
    middleware=[ToolCallMiddleware()]
)


graph = StateGraph(ChatState)

graph.add_node('init', init_node)
graph.add_node('agent', agent)
graph.add_node('user_input', user_input_node)

graph.add_edge(START, 'init')
graph.add_edge('init', 'user_input')
graph.add_edge('user_input', 'agent')

graph.add_conditional_edges(
    'agent',
    should_finish,
    {
        True: END,
        False: 'user_input'
    }
)
graph = graph.compile()
