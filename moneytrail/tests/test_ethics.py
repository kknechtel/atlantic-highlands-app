"""Disclosure-statement parser on a synthetic statement (no real filings in
the repo). Builds the same layout two ways: fillable (widgets) and flattened
to text, and checks both parse to the same rows."""
import pymupdf
import pytest

from moneytrail import ethics

HEAD_Y = 540
COLS = [47, 182, 370, 469, 565]
HEADERS = ["NAME OF SOURCE", "ADDRESS FOR", "RECIPIENT OF", "RELATIONSHIP"]
ROWS = [591, 642, 706]
VALUES = [["Gull Engineering LLC", "3 Dune Rd\nSea Bright, NJ 07760", "Pat Official", "Spouse"],
          ["Example Borough", "1 Main St\nExample, NJ 07716", "Pat Official", "Self"]]


def _build(path, fillable):
    doc = pymupdf.open()
    for i in range(11):
        doc.new_page(width=612, height=792)
    p0 = doc[0]
    p0.insert_text((50, 100), "Role of School Official:", fontsize=11)
    p0.insert_text((50, 130), "First Name:", fontsize=11)
    p0.insert_text((300, 130), "Middle Initial:", fontsize=11)
    p0.insert_text((50, 160), "Last Name:", fontsize=11)
    p0.insert_text((50, 220), "First Name:", fontsize=11)
    p0.insert_text((50, 250), "Last Name:", fontsize=11)
    page1 = [((180, 88, 330, 104), "Board Member"), ((120, 118, 280, 134), "Pat"),
             ((120, 148, 280, 164), "Official"), ((120, 208, 280, 224), "Sam"), ((120, 238, 280, 254), "Official")]
    p4 = doc[4]
    for x, h in zip(COLS, HEADERS):
        p4.insert_text((x + 20, HEAD_Y + 12), h, fontsize=10)
    for x in COLS:
        p4.draw_line((x, HEAD_Y), (x, ROWS[-1]))
    for y in [HEAD_Y] + ROWS:
        p4.draw_line((COLS[0], y), (COLS[-1], y))
    cells = []
    for (top, bot), vals in zip(zip(ROWS, ROWS[1:]), VALUES):
        for (x0, x1), v in zip(zip(COLS, COLS[1:]), vals):
            cells.append(((x0 + 2, top + 2, x1 - 2, bot - 2), v))
    for page, items in ((p0, page1), (p4, cells)):
        for rect, v in items:
            if fillable:
                w = pymupdf.Widget()
                w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                w.field_name = f"f{rect[0]}_{rect[1]}"
                w.rect = pymupdf.Rect(rect)
                w.field_value = v
                w.field_flags = pymupdf.PDF_TX_FIELD_IS_MULTILINE
                w.text_fontsize = 9
                page.add_widget(w)
            else:
                for k, line in enumerate(v.split("\n")):
                    page.insert_text((rect[0] + 2, rect[1] + 10 + 12 * k), line, fontsize=9)
    doc.save(path)


@pytest.fixture
def pdfs(tmp_path):
    f, t = tmp_path / "fill.pdf", tmp_path / "text.pdf"
    _build(f, True)
    _build(t, False)
    return f, t


def _norm(rows):
    return [(r["business_name"], r["street"], r["zip"], r["related_person"], r["relationship"])
            for r in rows if r["item"] == "income_source"]


def test_widgets(pdfs):
    r = ethics.parse(str(pdfs[0]))
    assert r["method"] == "widgets"
    assert r["official"]["name"] == "Pat Official" and r["official"]["spouse"] == "Sam Official"
    assert r["official"]["role"] == "Board Member"
    assert _norm(r["rows"]) == [("Gull Engineering LLC", "3 Dune Rd", "07760", "Pat Official", "Spouse"),
                                ("Example Borough", "1 Main St", "07716", "Pat Official", "Self")]


def test_flattened_text_matches_widgets(pdfs):
    fill, text = pdfs
    r = ethics.parse(str(text), template_path=str(fill))
    assert r["method"] == "text"
    assert r["official"]["name"] == "Pat Official"
    assert _norm(r["rows"]) == _norm(ethics.parse(str(fill))["rows"])
