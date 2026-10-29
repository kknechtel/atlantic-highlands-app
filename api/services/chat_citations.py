"""Citation checking for the chat answer stream.

The model cites facts as `[source: <filename>]`. This module makes sure each
tag points at a document the chat actually retrieved this turn (or cited in
an earlier turn), rewrites near-misses (a page suffix, a title, a document
id) to the exact filename the frontend resolves, and drops tags that match
nothing. It also lifts the hidden `<!--followups:[...]-->` block out of the
text, and after the answer checks that cited dollar figures appear in the
cited document.

Everything here is pure (no DB, no HTTP) so it can be unit tested.
"""
from __future__ import annotations

import json
import re
from typing import Iterable, Optional

_SOURCE_OPEN = "[source:"
_FOLLOWUPS_OPEN = "<!--followups:"
_MARKERS = (_SOURCE_OPEN, _FOLLOWUPS_OPEN)
_MAX_TAG = 600  # an "open" marker with no close after this many chars is plain text

_PAGE_SUFFIX = re.compile(r"\s*[,;(]?\s*(?:p|pp|pg|page|pages)\.?\s*\d+(?:\s*[-–]\s*\d+)?\)?\s*$", re.I)
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_TAG_IN_TEXT = re.compile(r"\[source:\s*([^\]]+)\]", re.I)


class CitationIndex:
    """Documents the model may cite, keyed several ways."""

    def __init__(self) -> None:
        self._by_key: dict[str, str] = {}

    @staticmethod
    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().strip("`'\"").lower())

    def add(self, filename: Optional[str], title: Optional[str] = None,
            document_id: Optional[str] = None) -> None:
        if not filename:
            return
        for key in (filename, title, document_id, re.sub(r"\.[a-z0-9]{2,4}$", "", filename, flags=re.I)):
            if key:
                self._by_key.setdefault(self._norm(str(key)), filename)

    def add_from_text(self, text: str) -> None:
        """Seed with filenames already cited in earlier (already checked) answers."""
        for m in _TAG_IN_TEXT.finditer(text or ""):
            for part in m.group(1).split(";"):
                self.add(part.strip())

    def add_tool_result(self, result) -> None:
        """Walk a tool result and register every document it mentions."""
        if isinstance(result, dict):
            if result.get("filename"):
                self.add(result["filename"], result.get("title"), result.get("document_id"))
            for v in result.values():
                if isinstance(v, (dict, list)):
                    self.add_tool_result(v)
        elif isinstance(result, list):
            for item in result:
                self.add_tool_result(item)

    def resolve(self, raw: str) -> Optional[str]:
        cand = self._norm(raw)
        for attempt in (cand, self._norm(_PAGE_SUFFIX.sub("", raw))):
            if attempt in self._by_key:
                return self._by_key[attempt]
        # Unique containment either way ("2024 Audit Report" ⊂ "Town 2024 Audit Report.pdf").
        if len(cand) >= 8 and not _UUID.match(cand):
            hits = {f for k, f in self._by_key.items() if cand in k or (len(k) >= 8 and k in cand)}
            if len(hits) == 1:
                return hits.pop()
        return None


class AnswerFilter:
    """Feed streamed text in, get checked text out.

    Holds back only what might be the start of a tag, so the answer still
    streams. Each `[source: a; b]` tag is rewritten to verified filenames or
    removed; a followups block is captured into `.followups`."""

    def __init__(self, index: CitationIndex) -> None:
        self.index = index
        self.buf = ""
        self.space = ""
        self.followups: list[str] = []
        self.dropped: list[str] = []
        self.cited: list[str] = []

    def feed(self, text: str) -> str:
        self.buf += text
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _drain(self, final: bool) -> str:
        out: list[str] = []

        def emit(piece: str) -> None:
            # Spaces are held until we know whether a removed tag follows them.
            if not piece:
                return
            body = piece.rstrip(" ")
            if body:
                out.append(self.space + body)
                self.space = ""
            self.space += piece[len(body):]

        while self.buf:
            starts = [i for i in (self.buf.find("["), self.buf.find("<")) if i >= 0]
            if not starts:
                emit(self.buf)
                self.buf = ""
                break
            i = min(starts)
            emit(self.buf[:i])
            self.buf = self.buf[i:]
            low = self.buf.lower()
            marker = next((m for m in _MARKERS if low.startswith(m)), None)
            if marker is None:
                if not final and any(m.startswith(low) for m in _MARKERS):
                    break  # could still become a marker; wait for more text
                emit(self.buf[0])
                self.buf = self.buf[1:]
                continue
            close = "]" if marker == _SOURCE_OPEN else "-->"
            end = self.buf.find(close)
            if end < 0:
                if not final and len(self.buf) < _MAX_TAG:
                    break
                emit(self.buf[0])  # never closed: treat as plain text
                self.buf = self.buf[1:]
                continue
            body = self.buf[len(marker):end]
            self.buf = self.buf[end + len(close):]
            piece = self._source_tag(body) if marker == _SOURCE_OPEN else self._followups(body)
            if piece:
                emit(piece)
            else:
                self.space = ""  # no "figure ." left behind a removed tag
        if final and self.space:
            out.append(self.space)
            self.space = ""
        return "".join(out)

    def _source_tag(self, body: str) -> str:
        good = []
        for part in re.split(r";|\]\s*\[source:", body):
            part = part.strip()
            if not part:
                continue
            filename = self.index.resolve(part)
            if filename:
                if filename not in good:
                    good.append(filename)
            else:
                self.dropped.append(part)
        for f in good:
            if f not in self.cited:
                self.cited.append(f)
        return " ".join(f"[source: {f}]" for f in good)

    def _followups(self, body: str) -> str:
        try:
            items = json.loads(body)
        except ValueError:
            items = []
        self.followups = [str(q).strip()[:160] for q in items if str(q).strip()][:3] if isinstance(items, list) else []
        return ""


_FIGURE = re.compile(r"\$\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\s?\d+(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+\.\d{2}\b")


def _digits(s: str) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", s).replace("$", "").replace(" ", "")


def unverified_figures(answer: str, doc_texts: dict[str, str]) -> list[dict]:
    """Dollar figures that sit next to a citation but don't appear (in either
    comma spelling) in the cited documents' text. Each paragraph/line is
    checked against the sources cited in it. Calculated totals will show up
    here too — the caller labels them "not found verbatim", not "wrong"."""
    norm_docs = {f: _digits(t) for f, t in doc_texts.items()}
    out: list[dict] = []
    seen = set()
    for block in re.split(r"\n+", answer):
        sources = [s.strip() for m in _TAG_IN_TEXT.finditer(block) for s in m.group(1).split(";")]
        sources = [s for s in sources if s in norm_docs]
        if not sources:
            continue
        for m in _FIGURE.finditer(_TAG_IN_TEXT.sub("", block)):
            fig = m.group(0).strip()
            plain = _digits(fig)
            if len(plain.replace(".", "")) < 3 or (fig, tuple(sources)) in seen:
                continue
            seen.add((fig, tuple(sources)))
            # Match "4180000" or "4180000.00" against "4,180,000" in the source.
            variants = {plain, plain.rstrip("0").rstrip(".") if "." in plain else plain + ".00"}
            if not any(v and v in norm_docs[s] for s in sources for v in variants):
                out.append({"figure": fig, "sources": sources})
    return out


def doc_text_for(filenames: Iterable[str], tool_texts: dict[str, list[str]]) -> dict[str, str]:
    return {f: "\n".join(tool_texts.get(f, [])) for f in filenames}
