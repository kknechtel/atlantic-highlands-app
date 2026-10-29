"""Date bounds, dollar-figure spellings, and document paging / find."""
from services.doc_reader import find_lines, read_window
from services.query_expansion import amount_variants
from services.rag_search import date_bounds

DOC = "\n".join([
    "## Page 1",
    "# Current Fund Appropriations",
    "Salaries and wages",
    "41,206.13",
    "Other expenses 9,000.00",
    "## Page 2",
    "# Capital Fund",
    "Road improvements 120,000.00",
])


def test_date_bounds_accept_partial_dates():
    b = date_bounds("2024", "2024-03")
    assert (b["date_from"], b["date_to"]) == ("2024-01-01", "2024-03-99")
    assert (b["year_from"], b["year_to"]) == (2024, 2024)
    assert "2024-03-31" <= b["date_to"] < "2024-04-01"


def test_date_bounds_ignore_garbage():
    assert date_bounds("last spring", None)["date_from"] is None


def test_amount_variants_both_ways_and_skip_years():
    assert amount_variants("paid 41,206.13 to vendor") == ["41206.13"]
    assert amount_variants("check 41206.13") == ["41,206.13"]
    assert amount_variants("FY 2024 budget") == []
    assert amount_variants("$1,000 and 1000.50") == ["1000", "1,000.50"]


def test_find_matches_other_spelling_with_page_and_heading():
    res = find_lines(DOC, "41206.13")
    assert res["match_count"] == 1
    m = res["matches"][0]
    assert m["page"] == 1 and m["heading"] == "Current Fund Appropriations"


def test_find_carries_next_line_for_split_label():
    m = find_lines(DOC, "salaries")["matches"][0]
    assert "41,206.13" in m["line"]


def test_find_no_match_says_so():
    assert find_lines(DOC, "sewer")["match_count"] == 0


def test_read_window_pages_through_whole_doc_on_line_breaks():
    parts, offset = [], 0
    while offset is not None:
        w = read_window(DOC, offset, 40)
        parts.append(w["excerpt"])
        offset = w["next_offset"]
    assert "".join(parts) == DOC
    assert read_window(DOC, 80, 40)["start_page"] == 1


def test_no_embedding_key_means_no_fake_vectors(monkeypatch):
    import pytest
    from services import embeddings
    monkeypatch.setattr(embeddings, "api_key", lambda name: "")
    assert not embeddings.semantic_available()
    assert embeddings.embed_documents_batch(["a", "b"]) == [None, None]
    assert embeddings.embed_document("a") is None
    with pytest.raises(RuntimeError):
        embeddings.embed_query("police budget")
