"""Which engine transcribes, and which old transcripts get redone."""
import os
import shutil
import subprocess

import pytest

from services import transcription_service as ts


def test_engine_rank_orders_stored_engine_names():
    assert ts.engine_rank("faster-whisper-base-chunked") == 0
    assert ts.engine_rank("yt-dlp+faster-whisper-base") == 0
    assert ts.engine_rank("faster-whisper-small.en-chunked") == 1
    assert ts.engine_rank("deepinfra-whisper-large-v3") == 3
    assert ts.engine_rank("yt-dlp+deepinfra-whisper-large-v3") == 3
    assert ts.engine_rank("youtube-captions-auto") < ts.engine_rank("faster-whisper-small.en")
    assert ts.engine_rank("deepinfra-whisper-large-v3-vad") > ts.engine_rank("deepinfra-whisper-large-v3")
    assert ts.engine_rank("youtube-captions-manual") > ts.engine_rank("deepinfra-whisper-large-v3-vad")


def test_speech_only_maps_times_back_to_the_recording(monkeypatch):
    import numpy as np
    from faster_whisper import vad

    sr = 16000
    # Speech at 10-12s and 20-25s of a 30s chunk; the rest is silence.
    stamps = [{"start": 10 * sr, "end": 12 * sr}, {"start": 20 * sr, "end": 25 * sr}]
    monkeypatch.setattr(vad, "get_speech_timestamps", lambda audio: stamps)
    speech, ts_map = ts._speech_only(np.zeros(30 * sr, np.float32))
    assert len(speech) == 7 * sr
    assert ts_map.get_original_time(1.0) == 11.0
    assert ts_map.get_original_time(3.0) == 21.0


def test_speech_only_returns_none_for_silence(monkeypatch):
    import numpy as np
    from faster_whisper import vad

    monkeypatch.setattr(vad, "get_speech_timestamps", lambda audio: [])
    assert ts._speech_only(np.zeros(16000, np.float32)) == (None, None)


def test_filler_runs_collapse_to_one_line():
    S = ts.TranscriptSegment
    segs = [S(0, 1, "Thank you."), S(1, 2, "Thank you."), S(2, 3, "thank you"),
            S(3, 4, "Motion to approve."), S(4, 5, "Thank you."), S(5, 6, "Second."), S(6, 7, "Second.")]
    assert [s.text for s in ts._collapse_filler_runs(segs)] == [
        "Thank you.", "Motion to approve.", "Thank you.", "Second.", "Second."]


@pytest.fixture
def two_chunk_audio(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    path = tmp_path / "meeting.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=25", "-ar", "16000", "-ac", "1", str(path)],
                   check=True)
    monkeypatch.setattr(ts, "_API_CHUNK_SECONDS", 15)  # 25s audio → 2 chunks
    monkeypatch.setattr(ts, "_deepinfra_key", lambda: "test-key")
    monkeypatch.setattr(ts.time, "sleep", lambda s: None)
    # A sine isn't speech to Silero; treat the whole chunk as speech.
    from faster_whisper import vad
    monkeypatch.setattr(vad, "get_speech_timestamps", lambda audio: [{"start": 0, "end": len(audio)}])
    return str(path)


class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body, self.headers, self.text = status, body or {}, {}, "err"

    def json(self):
        return self._body


def test_deepinfra_stitches_chunks_on_one_timeline(two_chunk_audio, monkeypatch):
    calls = []

    def fake_post(url, headers, data, files, timeout):
        calls.append(data)
        assert headers["Authorization"] == "bearer test-key"
        assert files["audio"][2] == "audio/mpeg"
        return _Resp(200, {"segments": [{"start": 1.0, "end": 2.0, "text": f" part {len(calls)}"}],
                           "inference_status": {"cost": 0.001}})

    monkeypatch.setattr("requests.post", fake_post)
    r = ts.transcribe_deepinfra(two_chunk_audio)
    assert r.engine == "deepinfra-whisper-large-v3-vad"
    assert [(s.start, s.text) for s in r.segments] == [(1.0, "part 1"), (16.0, "part 2")]
    assert calls[0]["language"] == "en" and "initial_prompt" in calls[0]
    assert r.text.splitlines()[1] == "[00:00:16] part 2"


def test_deepinfra_retries_rate_limits(two_chunk_audio, monkeypatch):
    replies = iter([_Resp(429), _Resp(200, {"segments": []}), _Resp(200, {"segments": []})])
    monkeypatch.setattr("requests.post", lambda *a, **k: next(replies))
    assert ts.transcribe_deepinfra(two_chunk_audio) is not None


def test_silent_chunks_are_not_sent(two_chunk_audio, monkeypatch):
    from faster_whisper import vad
    monkeypatch.setattr(vad, "get_speech_timestamps", lambda audio: [])
    monkeypatch.setattr("requests.post", lambda *a, **k: pytest.fail("silence was sent"))
    assert ts.transcribe_deepinfra(two_chunk_audio).segments == []


def test_bad_key_gives_up_without_a_partial_transcript(two_chunk_audio, monkeypatch):
    n = []
    monkeypatch.setattr("requests.post", lambda *a, **k: n.append(1) or _Resp(401))
    assert ts.transcribe_deepinfra(two_chunk_audio) is None
    assert len(n) == 1  # 401 isn't retried


def test_api_only_does_not_fall_back_to_local(two_chunk_audio, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: _Resp(402))
    monkeypatch.setattr(ts, "transcribe_local_chunked", lambda p: pytest.fail("local model ran"))
    with open(two_chunk_audio, "rb") as fh:
        with pytest.raises(RuntimeError):
            ts.transcribe_audio_bytes(fh.read(), filename_hint="m.wav", api_only=True)


def test_no_key_means_local_model(monkeypatch):
    monkeypatch.setattr(ts, "_deepinfra_key", lambda: "")
    assert ts.transcribe_deepinfra("/nonexistent.wav") is None
    assert ts.current_engine_name() == ts.whisper_engine_name()
