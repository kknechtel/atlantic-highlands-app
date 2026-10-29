"""Citation checking and follow-up extraction on a streamed answer."""
from services.chat_citations import AnswerFilter, CitationIndex, unverified_figures

ID = "9c28f277-7c27-4b13-b7de-18d14b6af6a9"


def _index():
    idx = CitationIndex()
    idx.add_tool_result({"chunks": [{"filename": "2024 Audit Report.pdf", "document_id": ID}],
                         "documents": [{"filename": "753224801.pdf", "title": "Adopted Budget 2025"}]})
    return idx


def _stream(text, idx, step=3):
    f = AnswerFilter(idx)
    out = "".join(f.feed(text[i:i + step]) for i in range(0, len(text), step)) + f.flush()
    return out, f


def test_tags_rewritten_across_chunk_boundaries():
    out, f = _stream("Debt is $4,180,000 [source: 2024 Audit Report.pdf, p. 16]. Done.", _index())
    assert out == "Debt is $4,180,000 [source: 2024 Audit Report.pdf]. Done."
    assert f.cited == ["2024 Audit Report.pdf"]


def test_id_title_and_unknown_sources():
    out, f = _stream(f"A [source: {ID}] B [source: Adopted Budget 2025] C [source: made up.pdf]", _index())
    assert out == "A [source: 2024 Audit Report.pdf] B [source: 753224801.pdf] C"
    assert f.dropped == ["made up.pdf"]


def test_plain_brackets_and_links_pass_through():
    text = "See [the budget](https://x.test) and item [3] or <b>bold</b>."
    out, _ = _stream(text, _index(), step=1)
    assert out == text


def test_followups_block_is_lifted_out():
    out, f = _stream('Answer.\n<!--followups:["How about 2023?", "Who voted no?"]-->', _index())
    assert out == "Answer.\n"
    assert f.followups == ["How about 2023?", "Who voted no?"]


def test_earlier_answers_seed_the_index():
    idx = CitationIndex()
    idx.add_from_text("Earlier [source: Minutes March 2026.pdf]")
    assert _stream("Again [source: Minutes March 2026.pdf]", idx)[0] == "Again [source: Minutes March 2026.pdf]"


def test_unverified_figures_ignore_comma_spelling_and_flag_missing():
    docs = {"2024 Audit Report.pdf": "Serial bonds 4180000.00 outstanding; total 4,244,349.53"}
    answer = ("Bonds were $4,180,000 and net debt $4,244,349.53 [source: 2024 Audit Report.pdf].\n"
              "Surplus was $1,251,681 [source: 2024 Audit Report.pdf].\n"
              "Uncited line with $999,999.")
    assert unverified_figures(answer, docs) == [
        {"figure": "$1,251,681", "sources": ["2024 Audit Report.pdf"]}]
