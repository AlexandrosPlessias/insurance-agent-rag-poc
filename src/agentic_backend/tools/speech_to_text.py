"""Tool: speech_to_text — transcribe audio bytes to text via faster-whisper."""
from __future__ import annotations

from agentic_backend.tools import AgentTool


def _run(audio_bytes: bytes, language: str | None = None) -> dict:
    """Transcribe audio.

    Args:
        audio_bytes: Raw audio file bytes.
        language: ISO-639-1 hint; None for auto-detect.

    Returns:
        {"transcript": str, "language": str, "duration_ms": int}
    """
    from agentic_backend.voice import stt

    return stt.transcribe(audio_bytes, language=language)


tool = AgentTool(
    name="speech_to_text",
    description=(
        "Transcribe audio bytes to text using a local Whisper model. "
        "Returns transcript, detected language, and audio duration."
    ),
    input_fields={
        "audio_bytes": "raw audio file bytes (WAV, MP3, OGG, …)",
        "language": "ISO-639-1 hint e.g. 'en'; omit for auto-detect",
    },
    run=_run,
)
