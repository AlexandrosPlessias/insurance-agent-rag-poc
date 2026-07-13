"""Voice I/O routes.

POST /audio/transcribe  — upload audio → transcript text
POST /audio/synthesize  — text → WAV audio

Both endpoints return 404 when VOICE_ENABLED=false so the rest of the
stack is unaffected by the feature flag.
"""
from __future__ import annotations

import hashlib
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from agentic_backend.audit.events import VOICE_SYNTHESIZE, VOICE_TRANSCRIBE
from agentic_backend.audit.middleware import get_audit_store
from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger
from agentic_backend.voice import stt, tts

log = get_logger(__name__)
router = APIRouter()


class SynthesizeRequest(BaseModel):
    text: str
    language: str = "en"


def _require_voice() -> None:
    if not settings.voice_enabled:
        raise HTTPException(404, "Voice I/O is disabled — set VOICE_ENABLED=true in .env")


@router.post("/audio/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form("en"),
    user_id: str = Form("anonymous"),
) -> dict:
    """Transcribe an uploaded audio file.

    Returns:
        ``{"transcript": str, "language": str, "duration_ms": int}``
    """
    _require_voice()
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    try:
        result = stt.transcribe(audio_bytes, language=language or None)
    except Exception as exc:
        log.exception("STT transcription failed")
        raise HTTPException(500, "Transcription failed — see server logs") from exc

    get_audit_store().log(
        event_type=VOICE_TRANSCRIBE,
        user_id=user_id,
        payload={
            "audio_sha256": hashlib.sha256(audio_bytes).hexdigest(),
            "audio_bytes": len(audio_bytes),
            "language": result["language"],
            "duration_ms": result["duration_ms"],
            "transcript": result["transcript"],
        },
    )
    return result


@router.post("/audio/synthesize")
async def synthesize_audio(body: SynthesizeRequest) -> Response:
    """Synthesize text to a WAV audio clip.

    Returns: ``audio/wav`` binary response.
    """
    _require_voice()
    if not body.text.strip():
        raise HTTPException(400, "text must not be empty")

    t0 = time.perf_counter()
    try:
        wav_bytes = tts.synthesize(body.text, language=body.language)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        log.exception("TTS synthesis failed")
        raise HTTPException(500, "Synthesis failed — see server logs") from exc

    get_audit_store().log(
        event_type=VOICE_SYNTHESIZE,
        user_id="anonymous",
        payload={
            "text_sha256": hashlib.sha256(body.text.encode()).hexdigest(),
            "char_count": len(body.text),
            "voice_id": tts._voice_id_for_language(body.language),
            "wav_bytes": len(wav_bytes),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        },
    )
    return Response(content=wav_bytes, media_type="audio/wav")
