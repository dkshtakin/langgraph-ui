"""Pydantic domain models for the book-planner graph."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Character(BaseModel):
    """Character information."""

    name: str = Field(description="Character name")
    age: int = Field(description="Age")
    description: str = Field(description="Brief character description")


class ChapterSummary(BaseModel):
    """Chapter summary."""

    title: str = Field(description="Chapter title")
    description: str = Field(description="Brief chapter description")
    pages: int = Field(description="Chapter length in pages")
    words: int = Field(description="Chapter word count")
    characters: List[Character] = Field(
        description="New characters appearing in this chapter"
    )


class BookSummary(BaseModel):
    """Book summary."""

    title: str = Field(description="Book title")
    description: str = Field(description="Brief plot setup description")
    chapters: List[ChapterSummary] = Field(
        description="Chapter list with descriptions"
    )
    characters: List[Character] = Field(description="All character list")
