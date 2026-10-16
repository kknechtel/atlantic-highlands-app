"""Keyword retrieval weighting and keyword-only embeddings (no database needed)."""


def test_no_voyage_key_means_no_vectors(monkeypatch):
    import services.embeddings as e
    monkeypatch.setattr(e, "api_key", lambda name: "")
    assert e.model_id() is None and not e.is_semantic()
    assert e.embed_query("anything") is None
    assert e.embed_documents_batch(["a", "b"]) == [None, None]


class _FakeDB:
    """Just enough of a Session for keyword_search.build."""
    def __init__(self, df, n):
        self.df, self.n = df, n

    def execute(self, stmt, params=None):
        sql = str(stmt)
        outer = self

        class R:
            def scalar(self):
                return outer.n

            def fetchall(self):
                return list(outer.df.items())

            def scalars(self):
                class S:
                    def all(self_inner):
                        import re
                        stop = {"how", "much", "did", "the", "to", "on", "a"}
                        words = re.findall(r"[a-z]+", (params or {}).get("q", "").lower())
                        return [w[:-1] if w.endswith("s") else w for w in words if w not in stop]
                return S()
        return R()


def test_keyword_weights_rare_terms_and_drops_ubiquitous_ones():
    from services import keyword_search
    keyword_search.reset_cache()
    db = _FakeDB({"town": 9000, "pay": 900, "wall": 40, "prospect": 12, "retaining": 8, "fix": 300}, 10000)
    kq = keyword_search.build(db, "how much did the town pay to fix the retaining wall on Upper Prospect")
    terms = dict(kq.terms)
    assert "town" not in terms  # in 90% of chunks: noise
    assert "upper" not in terms  # not in the corpus at all
    assert terms["retaining"] > terms["wall"] > terms["pay"]
    assert kq.websearch is None
    keyword_search.reset_cache()


def test_operators_keep_websearch_semantics():
    from services import keyword_search
    keyword_search.reset_cache()
    db = _FakeDB({"fireworks": 5, "contract": 500}, 10000)
    kq = keyword_search.build(db, '"fireworks contract" -2019')
    assert kq.websearch == '"fireworks contract" -2019'
    keyword_search.reset_cache()
