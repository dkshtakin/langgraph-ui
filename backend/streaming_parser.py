"""Streaming parser with dual-length buffer math for reasoning tags.

Extracts ``reasoning``, ``answer`` chunks from a stream of text tokens that may
contain partial, split, or multi-chunk reasoning delimiters without losing any
characters.

Buffer contract
---------------
``parse_reasoning`` is a **state reducer**. It always accepts the *current*
accumulated buffer, appends new text to it, and returns an updated buffer plus
any newly emitted chunks. It processes at most one tag boundary per call — if a
single chunk contains multiple boundaries they will be discovered across
subsequent calls as the buffer grows.

**Correct usage pattern:**

1. Initialize: ``output_buffer = ""``, ``in_reasoning = False``
2. For every incoming chunk, **always reassign**:
   ``output_buffer, in_reasoning, new_chunks = parse_reasoning(chunk, output_buffer, in_reasoning)``
   Do not pass an old or empty buffer — the function expects the *accumulated*
   one.
3. At stream end (or on ``content-block-finish``), call
   ``flush_buffer(output_buffer, in_reasoning)`` to emit any trailing text.

This pattern is implemented in ``streaming.py`` (reference impl) and
``backend/sse_streaming.py`` (production SSE wrapper). Tests in
``tests/test_streaming_parser.py`` exercise it explicitly.
"""


from __future__ import annotations
from dotenv import load_dotenv
import os


start_reasoning_tag: str = os.environ.get('START_REASONING_TAG', '<think>')
end_reasoning_tag: str = os.environ.get('END_REASONING_TAG', '</think>')
N: int = len(start_reasoning_tag)
K: int = len(end_reasoning_tag)


def _safe_emit(chunks: list[dict], chunk_type: str, content: str) -> None:
    """Append a chunk only if it has non-empty content."""
    if content:
        chunks.append({"type": chunk_type, "content": content})


def parse_reasoning(
    text: str,
    output_buffer: str,
    in_reasoning: bool,
) -> tuple[str, bool, list[dict]]:
    """Parse ``text`` for reasoning boundaries.

    Args:
        text: Next token from the event stream (may be partial).
        output_buffer: Accumulator that preserves incomplete delimiters.
        in_reasoning: Whether we are currently inside a reasoning block.

    Returns:
        ``(output_buffer, in_reasoning, new_chunks)`` — updated state plus any
        newly emitted chunks.
    """
    new_chunks: list[dict] = []
    output_buffer += text

    if not in_reasoning:
        # ── outside reasoning ──────────────────────────────────────
        if len(output_buffer) >= N:
            idx = output_buffer.find(start_reasoning_tag)
            if idx != -1:
                # Full start tag found — switch into reasoning mode.
                in_reasoning = True
                _safe_emit(new_chunks, "answer", output_buffer[:idx])
                output_buffer = output_buffer[idx + N :]
            else:
                # Check for orphan end tag to avoid emitting it as answer text.
                end_idx = output_buffer.find(end_reasoning_tag)
                if end_idx != -1:
                    # Emit text before orphan end tag, keep remainder buffered.
                    _safe_emit(new_chunks, "answer", output_buffer[:end_idx])
                    output_buffer = output_buffer[end_idx + K :]
                else:
                    # No delimiter in sight — emit safe prefix.
                    cutoff = len(output_buffer) - (N - 1)
                    _safe_emit(
                        new_chunks, "answer", output_buffer[:cutoff]
                    )
                    output_buffer = output_buffer[cutoff:]

    else:
        # inside reasoning
        if len(output_buffer) >= K:
            idx = output_buffer.find(end_reasoning_tag)
            if idx != -1:
                # End tag found — switch back to answer mode.
                in_reasoning = False
                _safe_emit(new_chunks, "reasoning", output_buffer[:idx])
                output_buffer = output_buffer[idx + K :]
            else:
                cutoff = len(output_buffer) - (K - 1)
                _safe_emit(
                    new_chunks, "reasoning", output_buffer[:cutoff]
                )
                output_buffer = output_buffer[cutoff:]

    return output_buffer, in_reasoning, new_chunks


def flush_buffer(
    output_buffer: str,
    in_reasoning: bool,
) -> tuple[str, bool, list[dict]]:
    """Emit remaining buffered text and reset state.

    ``parse_reasoning`` resolves at most one boundary per call, so a buffer can
    still hold complete tags when its block ends — a model retrying an invalid
    tool call emits a block carrying two reasoning pairs. Every complete tag is
    resolved here; only a partial trailing tag is emitted verbatim, so no
    characters are lost.

    Args:
        output_buffer: Remaining buffer content.
        in_reasoning: Whether we are inside a reasoning block.

    Returns:
        ``(output_buffer, in_reasoning, chunks)`` — empty buffer, ``False``, and
        list of flushed chunks.
    """
    chunks: list[dict] = []

    while True:
        tag = end_reasoning_tag if in_reasoning else start_reasoning_tag
        idx = output_buffer.find(tag)
        if idx == -1:
            break
        _safe_emit(
            chunks, "reasoning" if in_reasoning else "answer", output_buffer[:idx]
        )
        output_buffer = output_buffer[idx + len(tag) :]
        in_reasoning = not in_reasoning

    # A partial trailing tag, or plain text after the last boundary.
    if output_buffer:
        chunks.append(
            {"type": "reasoning" if in_reasoning else "answer", "content": output_buffer}
        )

    return "", False, chunks

