"""LLM client configuration for graph nodes."""

from __future__ import annotations

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()


# Default LLM instance can be used by multiple graphs
chat = ChatOpenAI(
    base_url=os.environ.get('LLM_BASE_URL', 'http://127.0.0.1:8081/v1') ,
    api_key=os.environ.get('LLM_API_KEY', 'empty'),
    model=os.environ.get('LLM_NAME', ''),
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
