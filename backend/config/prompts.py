"""Shared prompt loading for graph nodes.

Each graph stores its own ``SOUL.md`` (and optionally ``OUTPUT.md``) in its
own directory.  Use :py:func:`_load_graph_prompt` to resolve them with a
fallback to minimal defaults.
"""

from __future__ import annotations

from pathlib import Path

_DEFAULT_SOUL = "You are a helpful assistant."
_DEFAULT_SUMMARY = "Please summarize what was discussed."


def _load_graph_prompt(graph_dir: Path, filename: str) -> str:
    """Read *filename* from *graph_dir*, returning ``""`` on failure."""
    path = graph_dir / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""
