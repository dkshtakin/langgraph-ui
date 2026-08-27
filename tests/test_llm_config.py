"""Tests for LLM config env-var resolution and repo layout.

Per issue 06-code-review-fixes.md:
1. Default fallback when ``LLM_API_KEY`` is unset → ``"empty"``.
2. Custom value when ``LLM_API_KEY`` is set in the environment.
3. ``.env.example`` exists and documents required variables.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _run_subprocess(env_extra: dict[str, str] | None = None) -> tuple[int, str]:
    """Run a minimal Python snippet in a fresh interpreter with optional env vars."""
    extra_env = {**os.environ} if env_extra is None else {**os.environ, **env_extra}

    # Clear any cached LLM module to avoid cross-test pollution.
    extra_env["PYTHONDONTWRITEBYTECODE"] = "1"

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-c", "from backend.config.llm import chat; print(chat.openai_api_key.get_secret_value())"],
        capture_output=True,
        text=True,
        env=extra_env,
        cwd=repo_root,
    )
    return result.returncode, (result.stdout.strip() or result.stderr.strip())


# ---------------------------------------------------------------------------
# Config resolution tests
# ---------------------------------------------------------------------------


def test_default_fallback_when_llm_api_key_unset():
    """When ``LLM_API_KEY`` is not set, ``chat.openai_api_key`` defaults to ``"empty"``."""
    # Remove LLM_API_KEY if present.
    env = {k: v for k, v in os.environ.items() if k != "LLM_API_KEY"}
    code, out = _run_subprocess(env)
    assert code == 0, f"Import failed: {out}"
    assert out == "empty", f"Expected default 'empty', got '{out}'."


def test_custom_api_key_from_env():
    """When ``LLM_API_KEY`` is set, ``chat.openai_api_key`` resolves to that value."""
    env = {**os.environ}
    env["LLM_API_KEY"] = "test-key-123"
    code, out = _run_subprocess(env)
    assert code == 0, f"Import failed: {out}"
    assert out == "test-key-123", f"Expected 'test-key-123', got '{out}'."


# ---------------------------------------------------------------------------
# Repo layout test
# ---------------------------------------------------------------------------


def test_env_example_exists_and_contains_vars(tmp_path):
    """``.env.example`` exists at repo root and documents required variables."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_example = os.path.join(repo_root, ".env.example")

    assert os.path.isfile(env_example), ".env.example must exist at repo root."

    content = open(env_example, encoding="utf-8").read()
    assert "LLM_API_KEY" in content, ".env.example must document LLM_API_KEY."
    assert "PLANNER_DIR" in content, ".env.example must document PLANNER_DIR."
