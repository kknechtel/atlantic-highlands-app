"""
Document chunking. Splits extracted text into ~1000-token windows with
~150-token overlap on paragraph boundaries when possible. Cheap, sync,
no LLM required — runs at ingestion time.
"""
import re
from typing import Iterable

# 1 token ≈ 4 chars for English prose. Use char-based windows so we don't
# pull in a tokenizer dependency just for chunking.
TARGET_CHARS = 4000      # ~1000 tokens
OVERLAP_CHARS = 600      # ~150 tokens
MIN_CHUNK_CHARS = 200    # discard tiny tail chunks


_PARA_SPLIT = re.compile(r"\n\s*\n")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_into_paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]
    # If there are no paragraph breaks (common with raw OCR), fall back to sentences.
    if len(paras) <= 1 and len(text) > TARGET_CHARS * 2:
        return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    return paras


def chunk_text(text: str) -> Iterable[str]:
    """Yield ~TARGET_CHARS-sized chunks with OVERLAP_CHARS overlap. Greedy:
    accumulates whole paragraphs until the next would push past target."""
    if not text:
        return
    text = text.replace("\x00", "")  # nul bytes break tsvector
    if len(text) <= TARGET_CHARS:
        yield text
        return

    paras = _split_into_paragraphs(text)
    buf: list[str] = []
    buf_len = 0

    def emit() -> str:
        return "\n\n".join(buf).strip()

    for p in paras:
        # If a single paragraph is itself huge, hard-split it on char boundary.
        if len(p) > TARGET_CHARS:
            if buf_len > MIN_CHUNK_CHARS:
                yield emit()
                buf, buf_len = [], 0
            for i in range(0, len(p), TARGET_CHARS - OVERLAP_CHARS):
                yield p[i:i + TARGET_CHARS]
            continue

        if buf_len + len(p) + 2 > TARGET_CHARS and buf_len > MIN_CHUNK_CHARS:
            yield emit()
            # Carry tail of last buffer as overlap so semantic continuity isn't lost.
            tail = emit()[-OVERLAP_CHARS:]
            buf, buf_len = ([tail], len(tail)) if tail else ([], 0)

        buf.append(p)
        buf_len += len(p) + 2

    if buf_len >= MIN_CHUNK_CHARS:
        yield emit()
