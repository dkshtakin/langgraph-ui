from __future__ import annotations

import os
from pathlib import Path
from datetime import date
from dotenv import load_dotenv
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
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import messages_to_dict
from langchain.tools import tool, ToolRuntime
from langchain.tools.tool_node import ToolCallRequest
from langchain.agents import create_agent, AgentState
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import wrap_tool_call, AgentMiddleware


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


def _load_graph_prompt(graph_dir: Path, filename: str) -> str:
    path = graph_dir / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


_GRAPH_DIR = Path(__file__).parent
SYSTEM_PROMPT: str = _load_graph_prompt(_GRAPH_DIR, 'SOUL.md')
SUMMARY_PROMPT: str = _load_graph_prompt(_GRAPH_DIR, 'OUTPUT.md')


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
    '''Call when the user is satisfied with the current work and wants to finish the conversation.'''
    return Command(
        update={
            'messages': runtime.state['messages'] +
                [ToolMessage(
                    'Successfully called end_dialog tool', tool_call_id=runtime.tool_call_id
                )],
            'stage': 'summary',
        },
        graph=Command.PARENT
    )


@tool
def today_tool() -> str:
    '''Return today's date in ISO format.'''
    return date.today().isoformat()


TOOLS = [end_dialog, today_tool]


class Character(BaseModel):
    name: str = Field(description='Character name')
    age: int = Field(description='Age')
    description: str = Field(description='Brief character description')


class ChapterSummary(BaseModel):
    title: str = Field(description='Chapter title')
    description: str = Field(description='Brief chapter description')
    pages: int = Field(description='Chapter length in pages')
    words: int = Field(description='Chapter word count')
    characters: List[str] = Field(
        description='Characters appearing in this chapter'
    )


class BookSummary(BaseModel):
    title: str = Field(description='Book title')
    description: str = Field(description='Brief plot setup description')
    chapters: List[ChapterSummary] = Field(
        description='Chapter list with descriptions'
    )
    characters: List[Character] = Field(description='All character list')


class BookPlannerState(MessagesState):
    stage: str
    structured_response: BookSummary


def should_continue(state: BookPlannerState) -> str:
    return state['stage']


def _init_node(state: BookPlannerState) -> dict:
    return {
        'messages': [
            SystemMessage(content=SYSTEM_PROMPT),
        ],
        'stage': 'dialog',
        'structured_response': None
    }


def _user_input_interrupt_node(state: BookPlannerState) -> dict:
    interrupt({'reason': 'waiting_for_user_input'})
    return


def _create_summary(state: BookPlannerState) -> dict:
    return {
        'messages': [HumanMessage(content=SUMMARY_PROMPT)]
    }


def _save_summary(state: BookPlannerState) -> dict:
    '''Persist summary to disk.'''
    summary = state['structured_response']
    book_title = summary.title
    filename = f'{book_title}.md'
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(summary.model_dump_json(indent=4))
    except Exception:
        pass  # best-effort
    return {'messages': [AIMessage(content=f'Plan saved to {filename}')]}


agent = create_agent(
    model=chat,
    tools=TOOLS,
    middleware=[ToolCallMiddleware()]
)
summary_agent = create_agent(
    model=chat,
    tools=[],
    response_format=ToolStrategy(BookSummary),
    middleware=[ToolCallMiddleware()]
)


graph = StateGraph(BookPlannerState)

graph.add_node('init', _init_node)
graph.add_node('agent', agent)
graph.add_node('summary_agent', summary_agent)
graph.add_node('user_input', _user_input_interrupt_node)
graph.add_node('create_summary', _create_summary)
graph.add_node('save_summary', _save_summary)

graph.add_edge(START, 'init')
graph.add_edge('init', 'user_input')
graph.add_edge('user_input', 'agent')

graph.add_conditional_edges(
    'agent',
    should_continue,
    {
        'dialog': 'user_input',
        'summary': 'create_summary'
    }
)

graph.add_edge('create_summary', 'summary_agent')
graph.add_edge('summary_agent', 'save_summary')
graph.add_edge('save_summary', END)

graph = graph.compile()
