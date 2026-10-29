"""
Embedding generation for hybrid RAG.

Voyage AI voyage-3 (1024 dims) when VOYAGE_API_KEY is set. Without a key,
nothing is embedded: vectors stay NULL (ingestion.reembed_missing fills them
once a key exists) and search runs keyword-only. There is deliberately no
fake fallback vector: the old hash vector made semantic search return random
passages blended in at full weight.
"""
from typing import Optional
import logging
import os
from config import api_key

log = logging.getLogger(__name__)

# voyage-3 is 1024-dim (matches database.py:EMBEDDING_DIM and the
# vector(1024) columns). voyage-3-lite is 512-dim — DO NOT use without
# also changing the column type, or every UPDATE rejects with
# "expected 1024 dimensions, not 512".
EMBEDDING_MODEL = "voyage-3"
EMBEDDING_DIM = 1024


def _voyage_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    import requests
    if not api_key("VOYAGE_API_KEY"):
        raise RuntimeError("VOYAGE_API_KEY not configured")
    resp = requests.post(
        "https://api.voyageai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key('VOYAGE_API_KEY')}", "Content-Type": "application/json"},
        json={"model": EMBEDDING_MODEL, "input": texts, "input_type": input_type},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Voyage API error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()

    # Record usage on a fresh short-lived session. Voyage returns
    # usage.total_tokens — stash that as input_tokens (embeddings have no
    # output side). Safe to skip silently if SessionLocal can't bind.
    try:
        total_tokens = int(((data.get("usage") or {}).get("total_tokens")) or 0)
        if total_tokens > 0:
            from database import SessionLocal
            from services.usage import record_usage
            sess = SessionLocal()
            try:
                # voyage-3 is $0.06/1M; voyage-3-lite is $0.02/1M. Use a
                # tighter rate than the catch-all in usage.py for accuracy.
                rate = 0.06 if EMBEDDING_MODEL == "voyage-3" else 0.02
                cost = (total_tokens * rate) / 1_000_000
                record_usage(
                    sess, source="embeddings", model=EMBEDDING_MODEL,
                    input_tokens=total_tokens, output_tokens=0,
                    estimated_cost_usd=cost,
                    metadata={"input_type": input_type, "batch_size": len(texts)},
                )
            finally:
                sess.close()
    except Exception:
        log.debug("voyage usage record skipped", exc_info=True)

    return [d["embedding"] for d in data["data"]]


def semantic_available() -> bool:
    """Real embeddings need a Voyage key; without one search is keyword-only."""
    return bool(api_key("VOYAGE_API_KEY"))


# A missing key or failed call returns None (stored as NULL and retried by
# ingestion.reembed_missing) rather than a vector that would poison ranking.

def embed_document(text: str) -> Optional[list[float]]:
    truncated = text[:32000]
    if api_key("VOYAGE_API_KEY"):
        try:
            return _voyage_embed([truncated], input_type="document")[0]
        except Exception as exc:
            log.warning("Voyage embed failed; leaving NULL for retry: %s", exc)
            return None
    return None


def embed_documents_batch(texts: list[str], batch_size: int = 32) -> list[Optional[list[float]]]:
    out: list[Optional[list[float]]] = []
    for i in range(0, len(texts), batch_size):
        batch = [t[:32000] for t in texts[i:i + batch_size]]
        if api_key("VOYAGE_API_KEY"):
            try:
                out.extend(_voyage_embed(batch, input_type="document"))
            except Exception as exc:
                log.warning("Voyage batch embed failed at offset %d; leaving NULL: %s", i, exc)
                out.extend([None] * len(batch))
            continue
        out.extend([None] * len(batch))
    return out


def embed_query(query: str) -> list[float]:
    """Raises without a key or when Voyage fails; callers fall back to keyword
    search (check semantic_available() first to skip the attempt)."""
    return _voyage_embed([query], input_type="query")[0]


def to_pgvector_literal(vec: list[float]) -> str:
    """Format a Python float list as the string literal pgvector expects."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
