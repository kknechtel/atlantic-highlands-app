"""Transcription for meeting recordings.

Three sources, one normalized result:

  - Town audio (.wma/.wav/.m4a/.dcr) → faster-whisper (local CPU, base model),
    OpenAI Whisper API fallback if OPENAI_API_KEY is set.
  - YouTube videos → youtube-transcript-api auto-captions (no download).

Returns segments with float-second offsets so the UI can render a clickable
transcript that seeks the player. The full text is stored on
Document.extracted_text so the existing RAG ingest pipeline can chunk + embed
it without changes.
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    segments: list[TranscriptSegment]
    engine: str
    language: str = "en"
    duration_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in self.segments
            ],
            "warnings": self.warnings,
        }


# ─── faster-whisper (local) ─────────────────────────────────────────
# Lazy singleton — loading the model is expensive (~200ms + first-run download).
# Module-level so successive calls in one process reuse it.
_whisper_model = None
_WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")  # base | small | tiny


def _get_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        logger.error("faster-whisper not installed: %s", e)
        return None
    # int8 quantization keeps memory low on CPU; on first run faster-whisper
    # downloads ~150MB to ~/.cache/huggingface/hub.
    try:
        _whisper_model = WhisperModel(
            _WHISPER_MODEL_SIZE, device="cpu", compute_type="int8"
        )
        logger.info("Loaded faster-whisper model: %s (int8 CPU)", _WHISPER_MODEL_SIZE)
    except Exception as e:
        logger.error("Failed to initialize faster-whisper: %s", e)
        _whisper_model = None
    return _whisper_model


def transcribe_local(audio_path: str) -> Optional[TranscriptionResult]:
    """Run faster-whisper against a local audio file. Returns None on failure."""
    model = _get_whisper()
    if model is None:
        return None
    try:
        # vad_filter=True drops silences which speeds up meeting audio noticeably.
        # word_timestamps=False — we only need segment-level for click-to-seek.
        segments_iter, info = model.transcribe(
            audio_path,
            vad_filter=True,
            beam_size=1,
            language=None,  # let it detect
        )
        segs: list[TranscriptSegment] = []
        for seg in segments_iter:
            text = (seg.text or "").strip()
            if not text:
                continue
            segs.append(TranscriptSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=text,
            ))
        return TranscriptionResult(
            text=" ".join(s.text for s in segs),
            segments=segs,
            engine=f"faster-whisper-{_WHISPER_MODEL_SIZE}",
            language=getattr(info, "language", "en") or "en",
            duration_seconds=float(getattr(info, "duration", 0.0) or 0.0),
        )
    except Exception as e:
        logger.exception("faster-whisper transcription failed: %s", e)
        return None


# ─── OpenAI Whisper API (fallback) ──────────────────────────────────

def transcribe_openai(audio_path: str) -> Optional[TranscriptionResult]:
    """Cloud fallback. Only fires when OPENAI_API_KEY is set."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError as e:
        logger.error("openai package missing: %s", e)
        return None
    try:
        client = OpenAI(api_key=api_key)
        with open(audio_path, "rb") as fh:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=fh,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        # SDK returns either a dict-like or object depending on version.
        data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        segs = []
        for s in data.get("segments") or []:
            text = (s.get("text") or "").strip()
            if not text:
                continue
            segs.append(TranscriptSegment(
                start=float(s.get("start", 0)),
                end=float(s.get("end", 0)),
                text=text,
            ))
        return TranscriptionResult(
            text=data.get("text") or " ".join(s.text for s in segs),
            segments=segs,
            engine="openai-whisper-1",
            language=data.get("language") or "en",
            duration_seconds=float(data.get("duration") or 0.0),
        )
    except Exception as e:
        logger.exception("OpenAI Whisper API failed: %s", e)
        return None


# ─── Public entrypoint for audio ────────────────────────────────────

def transcribe_audio_bytes(audio_bytes: bytes, *, filename_hint: str = "audio") -> TranscriptionResult:
    """Local-first with OpenAI fallback. Raises if both fail."""
    # Preserve the original extension so faster-whisper/PyAV can sniff the codec
    # (.wma needs the right hint to decode correctly).
    suffix = ""
    for ext in (".wma", ".wav", ".m4a", ".mp3", ".mp4", ".mov", ".dcr"):
        if filename_hint.lower().endswith(ext):
            suffix = ext
            break
    with tempfile.NamedTemporaryFile(suffix=suffix or ".bin", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        result = transcribe_local(tmp_path)
        if result and result.text.strip():
            return result
        logger.warning("Local Whisper produced empty/failed result for %s — trying OpenAI", filename_hint)
        result = transcribe_openai(tmp_path)
        if result and result.text.strip():
            return result
        raise RuntimeError(
            "Transcription failed: faster-whisper unavailable or produced no text, "
            "and OPENAI_API_KEY is unset / API call failed."
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ─── YouTube captions ───────────────────────────────────────────────

def transcribe_youtube(video_id: str, prefer_langs: tuple[str, ...] = ("en", "en-US")) -> TranscriptionResult:
    """Pull auto- or manually-generated captions for a YouTube video.

    Prefers manual transcripts over auto-generated when available (they're
    cleaner for civic content with named speakers and motion language)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            TranscriptsDisabled, NoTranscriptFound,
        )
    except ImportError as e:
        raise RuntimeError(f"youtube-transcript-api not installed: {e}")

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_manually_created_transcript(list(prefer_langs))
            engine = "youtube-captions-manual"
        except NoTranscriptFound:
            transcript = transcript_list.find_generated_transcript(list(prefer_langs))
            engine = "youtube-captions-auto"
        raw = transcript.fetch()
    except TranscriptsDisabled as e:
        raise RuntimeError(f"YouTube has captions disabled for {video_id}: {e}")
    except NoTranscriptFound as e:
        raise RuntimeError(f"No usable transcript found for {video_id}: {e}")
    except Exception as e:
        raise RuntimeError(f"YouTube transcript fetch failed for {video_id}: {e}")

    segs: list[TranscriptSegment] = []
    last_end = 0.0
    for entry in raw:
        # entry items are {text, start, duration}
        start = float(entry.get("start", 0.0))
        dur = float(entry.get("duration", 0.0))
        text = (entry.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        segs.append(TranscriptSegment(start=start, end=start + dur, text=text))
        last_end = max(last_end, start + dur)
    return TranscriptionResult(
        text=" ".join(s.text for s in segs),
        segments=segs,
        engine=engine,
        language=transcript.language_code or "en",
        duration_seconds=last_end,
    )
