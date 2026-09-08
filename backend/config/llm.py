"""LLM client configuration for graph nodes."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from backend.config.tools import TOOLS


# Shared LLM instance — configured once, reused across graphs.
chat = ChatOpenAI(
    base_url="http://127.0.0.1:8081/v1",
    api_key=os.environ.get("LLM_API_KEY", "empty"),
    model="KAT-Coder-V2.5-Dev-APEX-I-Compact",
    streaming=True,
    extra_body={
        "chat_template_kwargs": {
            "enable_thinking": True,
            "reasoning_effort": "medium",
        },
        "reasoning_format": "none"
    },
    reasoning={"effort": "max", "summary": None},
    output_version="responses/v1",
)
chat = chat.bind_tools(TOOLS)
