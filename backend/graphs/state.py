"""LangGraph state definition shared across graph modules."""

from __future__ import annotations

from typing import Optional, TypedDict

from langchain.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated

from backend.config.pydantic_models import BookSummary


class MessagesState(TypedDict):
    """Shared state for graph nodes."""

    messages: Annotated[list[AnyMessage], add_messages]
    stage: str
    summary: Optional[BookSummary]
