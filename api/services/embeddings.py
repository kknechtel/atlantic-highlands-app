"""
Embedding generation for hybrid RAG.

Order of preference:
  1. Voyage AI voyage-3-lite (1024 dims, $0.02/1M tokens) if VOYAGE_API_KEY set
  2. Nothing. Without a key, search is keyword-only (services.keyword_search
     handles plain-English questions) and vectors stay NULL.

Every stored vector is tagged with model_id() (embedding_model column) and
semantic search only compares vectors from the current model. There is no
non-semantic fallback: the old SHA-512 "hash vector" overflowed to all-zero
vectors and ranked by NaN.
"""
from typing import Optional
import logging

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


def model_id() -> Optional[str]:
    """Tag stored with every vector; None when search is keyword-only."""
    return EMBEDDING_MODEL if api_key("VOYAGE_API_KEY") else None


def is_semantic() -> bool:
    return model_id() is not None


# A failed Voyage call returns None (stored as NULL and retried by
# ingestion.reembed_missing), never a placeholder vector.
def embed_document(text: str) -> Optional[list[float]]:
    if not is_semantic():
        return None
    try:
        return _voyage_embed([text[:32000]], input_type="document")[0]
    except Exception as exc:
        log.warning("Voyage embed failed; leaving NULL for retry: %s", exc)
        return None


def embed_documents_batch(texts: list[str], batch_size: int = 32) -> list[Optional[list[float]]]:
    if not is_semantic():
        return [None] * len(texts)
    out: list[Optional[list[float]]] = []
    for i in range(0, len(texts), batch_size):
        batch = [t[:32000] for t in texts[i:i + batch_size]]
        try:
            out.extend(_voyage_embed(batch, input_type="document"))
        except Exception as exc:
            log.warning("Voyage batch embed failed at offset %d; leaving NULL: %s", i, exc)
            out.extend([None] * len(batch))
    return out


def embed_query(query: str) -> Optional[list[float]]:
    """None when keyword-only. Raises if Voyage fails (callers drop to keyword)."""
    if not is_semantic():
        return None
    return _voyage_embed([query], input_type="query")[0]


def to_pgvector_literal(vec: list[float]) -> str:
    """Format a Python float list as the string literal pgvector expects."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
