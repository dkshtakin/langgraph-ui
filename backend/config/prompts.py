"""Shared prompt loading for graph nodes.

Reads SOUL.md and OUTPUT.md from a configurable directory (default: ``planner``).
Falls back to minimal defaults when files are absent.
"""

from __future__ import annotations

import os
from pathlib import Path

_PLANNER_DIR = os.environ.get("PLANNER_DIR", "planner")

_DEFAULT_SOUL = "You are a helpful assistant."
_DEFAULT_SUMMARY = "Please summarize what was discussed."


def _load_prompt(filename: str) -> str:
    path = Path(_PLANNER_DIR) / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


SYSTEM_PROMPT: str = _load_prompt("SOUL.md") or _DEFAULT_SOUL
SUMMARY_PROMPT: str = _load_prompt("OUTPUT.md") or _DEFAULT_SUMMARY
