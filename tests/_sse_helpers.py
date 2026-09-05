"""Shared helpers for SSE-related tests."""

from __future__ import annotations


def parse_sse_events(text: str) -> list[dict]:
    """Parse SSE text into a list of ``{event, data}`` dicts."""
    import json

    events: list[dict] = []
    current_event: str | None = None
    current_data_lines: list[str] = []
    for line in text.split("\n"):
        if line.startswith("event:"):
            if current_event is not None:
                events.append({"event": current_event, "data": json.loads("\n".join(current_data_lines))})
            current_event = line[len("event:") :].strip()
            current_data_lines = []
        elif line.startswith("data:") and current_event is not None:
            current_data_lines.append(line[len("data:") :])
    if current_event is not None:
        events.append({"event": current_event, "data": json.loads("\n".join(current_data_lines))})
    return events
