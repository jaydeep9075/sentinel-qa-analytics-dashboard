"""Deterministic text chunking for document ingestion.

A whole PDF/log/markdown file used to become a single embedded document,
which both truncates the embedding (MiniLM only attends to ~256 tokens)
and makes retrieval coarse. Chunking splits on paragraph boundaries first,
then sentences, with a small overlap so context isn't lost at chunk edges.
"""

import re
from typing import Dict, List

DEFAULT_TARGET_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 40

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_long_block(block: str, target: int) -> List[str]:
    """Split an over-long paragraph on sentence boundaries, hard-wrapping
    only when a single sentence itself exceeds the target size."""
    sentences = _SENTENCE_SPLIT.split(block)
    pieces: List[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > target:
            if current:
                pieces.append(current)
                current = ""
            for i in range(0, len(sentence), target):
                pieces.append(sentence[i : i + target])
            continue
        if current and len(current) + len(sentence) + 1 > target:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(
    text: str,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> List[Dict]:
    """Split text into chunk dicts: {text, chunk_index, chunk_count, char_start}.

    Short texts come back as a single chunk unchanged, so structured row
    documents and small notes are unaffected by chunking.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [{"text": text, "chunk_index": 0, "chunk_count": 1, "char_start": 0}]

    blocks = [b.strip() for b in _PARAGRAPH_SPLIT.split(text) if b.strip()]
    pieces: List[str] = []
    for block in blocks:
        if len(block) <= target_chars:
            pieces.append(block)
        else:
            pieces.extend(_split_long_block(block, target_chars))

    # Greedily pack pieces up to target size.
    chunks: List[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > target_chars:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}".strip()
    if current:
        chunks.append(current)

    # Prepend a small overlap from the previous chunk for context continuity.
    results: List[Dict] = []
    offset = 0
    for i, chunk in enumerate(chunks):
        body = chunk
        if i > 0 and overlap_chars > 0:
            tail = chunks[i - 1][-overlap_chars:]
            body = f"{tail} {chunk}"
        if len(body) < MIN_CHUNK_CHARS and results:
            # Merge a tiny trailing chunk into the previous one instead of
            # emitting a near-empty embedding target.
            results[-1]["text"] = f"{results[-1]['text']}\n\n{chunk}"
            continue
        results.append({"text": body, "chunk_index": len(results), "char_start": offset})
        offset += len(chunk)

    for r in results:
        r["chunk_count"] = len(results)
    return results
