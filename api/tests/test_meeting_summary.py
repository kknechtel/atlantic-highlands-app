"""Meeting summaries: model choice and full-length transcripts."""
import json
from types import SimpleNamespace

import pytest

from services import meeting_summary as ms


class _FakeClient:
    def __init__(self, reply, stop="end_turn"):
        self.calls, self._reply, self._stop = [], reply, stop
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self._stop,
                               content=[SimpleNamespace(type="thinking", text=""),
                                        SimpleNamespace(type="text", text=self._reply)])


@pytest.fixture
def client(monkeypatch):
    fake = _FakeClient(json.dumps({"tldr": "ok", "decisions": []}))
    monkeypatch.setattr(ms, "api_key", lambda name: "k")
    monkeypatch.setattr(ms, "setting", lambda name, default: default)
    monkeypatch.setattr(ms.anthropic, "Anthropic", lambda api_key: fake)
    return fake


def _meeting(n=1445, words=18):
    # Like the 9/9/2026 council recording: 1,445 segments over ~1h54m.
    return [{"start": i * 4.7, "text": " ".join(["word"] * words) + f" seg{i}"} for i in range(n)]


def test_uses_haiku_with_room_for_thinking(client):
    out = ms.summarize_meeting(meeting_body="Council", meeting_date="2026-09-09", segments=_meeting(10))
    assert out["tldr"] == "ok"
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] >= 16000


def test_two_hour_meeting_is_not_truncated(client):
    ms.summarize_meeting(meeting_body="Council", meeting_date="2026-09-09", segments=_meeting())
    prompt = client.calls[0]["messages"][0]["content"]
    assert "seg1444" in prompt and "truncated" not in prompt


def test_cut_off_summary_is_an_error_not_bad_json(monkeypatch, client):
    client._stop = "max_tokens"
    with pytest.raises(RuntimeError, match="max_tokens"):
        ms.summarize_meeting(meeting_body="Council", meeting_date=None, segments=_meeting(5))
