"""Piper TTS engine — per-language voice cache, lazy-loaded on first call."""
from __future__ import annotations

import io
import logging
import time
import wave
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piper.voice import PiperVoice as _PiperVoice

_log = logging.getLogger(__name__)
_voices: dict[str, "_PiperVoice"] = {}


def _voice_id_for_language(language: str) -> str:
    from agentic_backend.config import settings

    return settings.voice_tts_voice_el if language == "el" else settings.voice_tts_voice


def _get_voice(language: str) -> "_PiperVoice":
    voice_id = _voice_id_for_language(language)
    if voice_id not in _voices:
        from piper.voice import PiperVoice

        from agentic_backend.config import settings

        onnx_path = settings.voice_models_dir / f"{voice_id}.onnx"
        if not onnx_path.exists():
            raise FileNotFoundError(
                f"Piper model not found at {onnx_path}. "
                f"Run: bash src/scripts/download_voice_models.sh {voice_id}"
            )
        _log.info("Loading Piper voice %r from %s", voice_id, onnx_path)
        t0 = time.perf_counter()
        _voices[voice_id] = PiperVoice.load(str(onnx_path))
        _log.info("Piper voice loaded in %.1fs", time.perf_counter() - t0)
    return _voices[voice_id]


def synthesize(text: str, language: str = "en") -> bytes:
    """Synthesize text to WAV bytes using the voice for the given language.

    Args:
        text: Plain text to speak.
        language: ISO-639-1 language code (``"en"`` or ``"el"``).

    Returns:
        Raw WAV bytes (RIFF/PCM).
    """
    from agentic_backend.observability.tracing import get_tracer

    voice_id = _voice_id_for_language(language)
    voice = _get_voice(language)
    _log.info("Synthesizing %d chars (lang=%s)", len(text), language)

    tracer = get_tracer("voice.tts")
    with tracer.start_as_current_span("tool.text_to_speech") as span:
        span.set_attribute("voice_id", voice_id)
        span.set_attribute("char_count", len(text))
        span.set_attribute("language", language)

        t0 = time.perf_counter()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_fh:
            voice.synthesize_wav(text, wav_fh)
        wav_bytes = buf.getvalue()
        latency_ms = int((time.perf_counter() - t0) * 1000)

        span.set_attribute("latency_ms", latency_ms)
        span.set_attribute("wav_bytes", len(wav_bytes))

    _log.info(
        "Synthesized %d chars → %d bytes in %dms",
        len(text),
        len(wav_bytes),
        latency_ms,
    )
    return wav_bytes
