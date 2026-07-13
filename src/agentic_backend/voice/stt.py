"""faster-whisper STT engine — singleton model, lazy-loaded on first call."""
from __future__ import annotations

import hashlib
import logging
import pathlib
import tempfile
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faster_whisper import WhisperModel as _WhisperModel

_log = logging.getLogger(__name__)
_model: "_WhisperModel | None" = None


def _get_model() -> "_WhisperModel":
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        from agentic_backend.config import settings

        model_id = settings.voice_stt_model
        _log.info("Loading WhisperModel %r (int8, CPU) — first call only", model_id)
        t0 = time.perf_counter()
        _model = WhisperModel(model_id, device="cpu", compute_type="int8")
        _log.info("WhisperModel %r loaded in %.1fs", model_id, time.perf_counter() - t0)
    return _model


def transcribe(audio_bytes: bytes, language: str | None = None) -> dict:
    """Transcribe raw audio bytes to text.

    Args:
        audio_bytes: Audio file bytes (WAV, MP3, OGG, …).
        language: ISO-639-1 hint (e.g. ``"en"``); ``None`` = auto-detect.

    Returns:
        ``{"transcript": str, "language": str, "duration_ms": int}``
    """
    model = _get_model()
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()[:16]
    _log.info("Transcribing audio sha256prefix=%s bytes=%d", audio_hash, len(audio_bytes))

    tmp = pathlib.Path(tempfile.mktemp(suffix=".wav"))
    try:
        tmp.write_bytes(audio_bytes)
        t0 = time.perf_counter()
        segments, info = model.transcribe(str(tmp), language=language, vad_filter=True)
        transcript = " ".join(s.text.strip() for s in segments)
        latency_ms = int((time.perf_counter() - t0) * 1000)
    finally:
        tmp.unlink(missing_ok=True)

    _log.info(
        "Transcribed: lang=%s duration=%.1fs latency=%dms chars=%d",
        info.language,
        info.duration,
        latency_ms,
        len(transcript),
    )
    return {
        "transcript": transcript,
        "language": info.language,
        "duration_ms": int(info.duration * 1000),
    }
