"""
Prompt loading for graph nodes.
"""

from __future__ import annotations

from pathlib import Path


_DEFAULT_SOUL = "You are a helpful assistant."


def _load_graph_prompt(graph_dir: Path, filename: str) -> str:
    """Read *filename* from *graph_dir*, returning ``""`` on failure."""
    path = graph_dir / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""
