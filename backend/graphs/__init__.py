"""Graphs package — each module exports ``id``, ``name``, ``build()``."""

from __future__ import annotations

from backend.graphs.book_planner import id as book_planner_id, name as book_planner_name, build as build_book_planner

__all__ = ["book_planner_id", "book_planner_name", "build_book_planner"]
