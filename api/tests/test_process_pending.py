"""A crash on one document must not stop the batch."""
import asyncio
from types import SimpleNamespace

from services import document_processor as dp


def test_one_crashing_doc_does_not_stop_the_batch(monkeypatch):
    ids = ["a", "bad", "c"]

    class _Q:
        def with_entities(self, *_): return self
        def limit(self, _): return self
        def all(self): return [(i,) for i in ids]

    class _DB:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, _model, doc_id): return SimpleNamespace(id=doc_id)

    import database
    monkeypatch.setattr(database, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(dp, "pending_query", lambda db: _Q())
    failed = []
    monkeypatch.setattr(dp, "_mark_failed", lambda doc_id, exc: failed.append(doc_id))

    async def fake_process_one(db, doc):
        if doc.id == "bad":
            raise ValueError("A string literal cannot contain NUL (0x00) characters.")
        return SimpleNamespace(status="processed", cost_usd=0.01)

    monkeypatch.setattr(dp, "process_one", fake_process_one)
    totals = asyncio.run(dp.process_pending(limit=10, concurrency=2))
    assert totals["processed"] == 2 and totals["error"] == 1
    assert failed == ["bad"]
