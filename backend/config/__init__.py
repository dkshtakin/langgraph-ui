"""Backend configuration package — models, tools, and LLM client."""

from __future__ import annotations

from backend.config.pydantic_models import BookSummary, ChapterSummary, Character
from backend.config.tools import TOOLS, end_dialog, today_tool
from backend.config.llm import chat

__all__ = [
    "BookSummary",
    "ChapterSummary",
    "Character",
    "TOOLS",
    "end_dialog",
    "today_tool",
    "chat",
]
