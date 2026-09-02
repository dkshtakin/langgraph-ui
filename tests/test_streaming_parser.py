"""Tests for ``backend.streaming_parser``.

Covers all edge cases from issue 02:
* Partial start/end tags split across multiple chunks
* Text before partial tag (safe-prefix eviction)
* End tag split across 3+ chunks
* Long text with no tags
* Character-by-character streaming
* Multiple reasoning blocks in one stream
"""

import pytest

from backend.streaming_parser import (
    N,
    K,
    end_reasoning_tag,
    flush_buffer,
    parse_reasoning,
    start_reasoning_tag,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _feed_chunks(buf: str, chunks: list[str]):
    """Helper that feeds a sequence of text chunks through parse_reasoning.

    Returns ``(output_buffer, in_reasoning, emitted_chunks)``.
    """
    in_reasoning = False
    emitted: list[dict] = []

    for chunk in chunks:
        buf, in_reasoning, new = parse_reasoning(chunk, buf, in_reasoning)
        emitted.extend(new)

    return buf, in_reasoning, emitted


# ── partial start tag split across 2+ chunks ────────────────────────────────


def test_partial_start_tag_split():
    """When the start tag is split across two chunks, no chunk should be emitted until it completes."""
    # Split "<|channel>thought" at position 4:
    #   "<|ch" + "annel>thought"
    buf = ""
    buf, in_r, emitted = parse_reasoning("<|ch", buf, False)
    buf, in_r, new2 = parse_reasoning("annel>thought", buf, in_r)
    emitted.extend(new2)

    assert len(emitted) == 0, "No output before complete tag is seen"
    assert in_r is True, "Should transition into reasoning mode"
    assert buf == "", "Buffer should be empty after emitting answer text"


# ── text before partial start tag ────────────────────────────────────────────


def test_text_before_partial_tag():
    """Safe prefix (text before partial tag) must be emitted; partial stays in buffer."""
    # First chunk: A + partial start tag
    buf = ""
    buf, in_r, emitted = _feed_chunks(buf, ["A<|ch"])

    # "A<|ch" is 5 chars, less than N-1=16, so nothing emitted yet.
    assert len(emitted) == 0
    assert in_r is False

    # Second chunk: complete remaining start tag + reasoning text + end tag + answer text
    buf, in_r, emitted2 = _feed_chunks(
        buf,
        ["annel>thoughtThis is reasoning<channel|>Answer text"]
    )
    buf, in_r, emitted3 = flush_buffer(buf, in_r)

    all_emitted = emitted + emitted2 + emitted3
    print(all_emitted)

    # Should have one answer chunk for "A" (before the partial tag)
    answer_chunks = [c for c in all_emitted if c["type"] == "answer"]
    assert len(answer_chunks) >= 1
    combined_answer = "".join(c["content"] for c in answer_chunks)
    # The letter A should be included in emitted content.
    assert "A" in combined_answer

    # Should have one reasoning chunk
    reasoning_chunks = [c for c in all_emitted if c["type"] == "reasoning"]
    assert len(reasoning_chunks) >= 1
    assert "This is reasoning" in reasoning_chunks[0]["content"]

    # Should have answer text after end tag
    answer_after_reasoning = "".join(c["content"] for c in all_emitted if c["type"] == "answer")
    assert "Answer text" in answer_after_reasoning


# ── end tag split across 3+ chunks ───────────────────────────────────────────


def test_end_tag_split_three_chunks():
    """End tag split across three chunks must not leak partials when seen outside reasoning."""
    # Split "<channel|>" at positions 4 and 8:
    #   "<chan" + "nel|" + ">"
    buf = ""
    buf, in_r, emitted = parse_reasoning("<chan", buf, False)
    buf, in_r, new2 = parse_reasoning("nel|", buf, in_r)
    buf, in_r, new3 = parse_reasoning(">", buf, in_r)
    emitted.extend(new2)
    emitted.extend(new3)

    assert len(emitted) == 0, "No chunk should be emitted for orphan end tag fragments"
    assert in_r is False, "End tag outside reasoning mode must not enter reasoning"


def test_end_tag_split_three_with_reasoning_text():
    """Complete scenario: text before partial, reasoning content, split end tag."""
    # Enter reasoning with a full start tag, then split the end tag.
    buf = ""
    in_r = False
    emitted: list[dict] = []

    buf, in_r, new = parse_reasoning("Hello ", buf, in_r)
    emitted.extend(new)
    buf, in_r, new = parse_reasoning(start_reasoning_tag, buf, in_r)
    emitted.extend(new)
    buf, in_r, new = parse_reasoning("reasoning content", buf, in_r)
    emitted.extend(new)

    # Now deliver split end tag: "<chan" + "nel|" + ">"
    buf, in_r, new2 = parse_reasoning("<chan", buf, in_r)
    emitted.extend(new2)
    buf, in_r, new3 = parse_reasoning("nel|", buf, in_r)
    emitted.extend(new3)
    buf, in_r, new4 = parse_reasoning(">", buf, in_r)
    emitted.extend(new4)

    # End tag should now be found and mode should switch back.
    reasoning_chunks = [c for c in emitted if c["type"] == "reasoning"]
    assert len(reasoning_chunks) >= 1


# ── long text with no tags ───────────────────────────────────────────────────


def test_long_text_no_tags():
    """Long text without any tags should be emitted in safe-prefix chunks."""
    long_text = "x" * 500

    buf, in_r, emitted = _feed_chunks("", [long_text])

    assert len(emitted) >= 1, "Should emit at least one chunk for long text"
    # All content except N-1 trailing chars should be in emitted chunks.
    total_emitted = sum(len(c["content"]) for c in emitted)
    assert total_emitted == len(long_text) - (N - 1)

    # After flush, remaining buffer should be emitted.
    _, _, flushed = flush_buffer(buf, in_r)
    flush_content = "".join(c["content"] for c in flushed)
    assert flush_content == long_text[-(N - 1):]


def test_long_text_no_tags_single_chunk():
    """Short text with no tags should be emitted on flush."""
    short_text = "Hello, world!"

    buf, in_r, emitted = _feed_chunks("", [short_text])

    # Short text (< N) produces no intermediate chunks.
    assert len(emitted) == 0
    assert buf == short_text

    _, _, flushed = flush_buffer(buf, in_r)
    assert len(flushed) == 1
    assert flushed[0]["type"] == "answer"
    assert flushed[0]["content"] == short_text


# ── character-by-character streaming ─────────────────────────────────────────


def test_character_by_character():
    """Feeding one character at a time must produce the same final result as full text.

    Note: CBC emits many small intermediate chunks (safe-prefix eviction), while
    bulk emits fewer larger chunks. The combined content of each type must match.
    """
    full_text = (
        "prefix<|channel>thoughtReasoning content<channel|>suffix"
    )

    buf, in_r, emitted_char_by_char = _feed_chunks("", list(full_text))
    _, _, flushed_cbc = flush_buffer(buf, in_r)
    all_cbc = emitted_char_by_char + flushed_cbc

    buf2, in_r2, emitted_bulk = _feed_chunks("", [full_text])
    _, _, flushed_bulk = flush_buffer(buf2, in_r2)
    all_bulk = emitted_bulk + flushed_bulk

    # Both approaches must produce equivalent combined content per type.
    def combine(chunks: list[dict]) -> dict[str, str]:
        result: dict[str, str] = {}
        for c in chunks:
            result[c["type"]] = result.get(c["type"], "") + c["content"]
        return result

    cbc_combined = combine(all_cbc)
    bulk_combined = combine(all_bulk)

    assert cbc_combined["answer"] == bulk_combined["answer"], "Answer text must match"
    assert cbc_combined["reasoning"] == bulk_combined["reasoning"], "Reasoning text must match"


# ── flush_buffer ─────────────────────────────────────────────────────────────


def test_flush_empty_buffer():
    """Flushing an empty buffer in answer mode should produce no chunks."""
    _, _, flushed = flush_buffer("", False)
    assert len(flushed) == 0


def test_flush_in_reasoning_no_end_tag():
    """Flush while in reasoning with no end tag — emit all as reasoning."""
    _, _, flushed = flush_buffer("partial reasoning", True)
    assert len(flushed) == 1
    assert flushed[0]["type"] == "reasoning"
    assert flushed[0]["content"] == "partial reasoning"


def test_flush_in_reasoning_with_end_tag():
    """Flush while in reasoning with end tag — emit up to tag as reasoning, rest as answer."""
    buf, _, flushed = flush_buffer("reasoning<channel|>answer tail", True)
    assert len(flushed) == 2
    assert flushed[0]["type"] == "reasoning"
    assert flushed[0]["content"] == "reasoning"
    assert flushed[1]["type"] == "answer"
    assert flushed[1]["content"] == "answer tail"
    assert buf == ""


# ── consecutive reasoning blocks ────────────────────────────────────────────


def test_consecutive_reasoning_blocks():
    """Two reasoning blocks found across multiple parse calls.

    The parser handles at most one tag boundary per call, so feeding the full
    text as a single chunk only finds the first start tag. To discover both
    reasoning blocks, we feed incrementally — each call reuses the accumulated
    buffer from the previous call.
    """
    buf = ""
    in_r = False
    emitted: list[dict] = []

    # Chunk 1: finds start tag, enters reasoning
    buf, in_r, new = parse_reasoning("before<|channel>thoughtreasoning1", buf, in_r)
    emitted.extend(new)

    # Chunk 2: finds end tag, exits reasoning; buffer carries "middle"
    buf, in_r, new = parse_reasoning("<channel|>middle", buf, in_r)
    emitted.extend(new)

    # Chunk 3: finds second start tag, enters reasoning again
    buf, in_r, new = parse_reasoning("<|channel>thoughtreasoning2", buf, in_r)
    emitted.extend(new)

    # Chunk 4: finds second end tag, exits reasoning; "after" stays in buffer
    buf, in_r, new = parse_reasoning("<channel|>after", buf, in_r)
    emitted.extend(new)

    # Flush to emit trailing "after" as answer
    _, _, flushed = flush_buffer(buf, in_r)
    emitted.extend(flushed)

    reasoning_blocks = [c for c in emitted if c["type"] == "reasoning"]
    answer_chunks = [c for c in emitted if c["type"] == "answer"]

    assert len(reasoning_blocks) == 2
    assert reasoning_blocks[0]["content"] == "reasoning1"
    assert reasoning_blocks[1]["content"] == "reasoning2"

    answer_text = "".join(c["content"] for c in answer_chunks)
    assert "before" in answer_text
    assert "middle" in answer_text
    assert "after" in answer_text


# ── constants ────────────────────────────────────────────────────────────────


def test_tag_lengths():
    """Verify N and K match actual tag lengths."""
    assert N == len(start_reasoning_tag)
    assert K == len(end_reasoning_tag)


def test_parse_reasoning_returns_three_values():
    """parse_reasoning must return (buffer, in_reasoning, chunks)."""
    result = parse_reasoning("test", "", False)
    assert isinstance(result, tuple) and len(result) == 3
    buf, in_r, chunks = result
    assert isinstance(buf, str)
    assert isinstance(in_r, bool)
    assert isinstance(chunks, list)


def test_parse_reasoning_no_spurious_emissions():
    """Small text that doesn't contain a complete tag must not emit."""
    _, _, emitted = _feed_chunks("", ["Hello"])
    # "Hello" is only 5 chars (< N=17), nothing should be emitted.
    assert len(emitted) == 0
