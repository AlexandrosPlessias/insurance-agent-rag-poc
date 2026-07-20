"""Voice I/O routes.

POST /audio/transcribe   — upload audio → transcript text
POST /audio/synthesize   — text → WAV audio
POST /audio/correction   — report voice transcript correction (WER metric)

Both transcribe and synthesize return 404 when VOICE_ENABLED=false so the
rest of the stack is unaffected by the feature flag.
"""
from __future__ import annotations

import asyncio
import hashlib
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from agentic_backend.audit.events import VOICE_CORRECTION, VOICE_SYNTHESIZE, VOICE_TRANSCRIBE
from agentic_backend.audit.middleware import get_audit_store
from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.metrics import record_voice_request
from agentic_backend.voice import stt, tts

log = get_logger(__name__)
router = APIRouter()


class SynthesizeRequest(BaseModel):
    text: str
    language: str = "en"


class CorrectionRequest(BaseModel):
    original: str
    corrected: str
    language: str = "en"


def _require_voice() -> None:
    if not settings.voice_enabled:
        raise HTTPException(404, "Voice I/O is disabled — set VOICE_ENABLED=true in .env")


def _wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate via word-level Levenshtein distance."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    if not ref_words:
        return 0.0
    n, m = len(ref_words), len(hyp_words)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[j] = prev[j - 1]
            else:
                dp[j] = 1 + min(prev[j - 1], prev[j], dp[j - 1])
    return round(dp[m] / len(ref_words), 4)


def _cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate via character-level Levenshtein distance."""
    ref_chars = list(reference.lower())
    hyp_chars = list(hypothesis.lower())
    if not ref_chars:
        return 0.0
    n, m = len(ref_chars), len(hyp_chars)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, m + 1):
            if ref_chars[i - 1] == hyp_chars[j - 1]:
                dp[j] = prev[j - 1]
            else:
                dp[j] = 1 + min(prev[j - 1], prev[j], dp[j - 1])
    return round(dp[m] / len(ref_chars), 4)


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
        result = await asyncio.to_thread(stt.transcribe, audio_bytes, language=language or None)
    except Exception as exc:
        log.exception("STT transcription failed")
        raise HTTPException(500, "Transcription failed — see server logs") from exc

    record_voice_request("transcribe", result.get("duration_ms", 0))
    audio_sha256 = hashlib.sha256(audio_bytes).hexdigest()

    if settings.audit_retain_audio:
        audio_dir = settings.audit_audio_dir
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.joinpath(f"{audio_sha256}.wav").write_bytes(audio_bytes)

    get_audit_store().log(
        event_type=VOICE_TRANSCRIBE,
        user_id=user_id,
        payload={
            "audio_sha256": audio_sha256,
            "audio_bytes": len(audio_bytes),
            "audio_retained": settings.audit_retain_audio,
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
        wav_bytes = await asyncio.to_thread(tts.synthesize, body.text, language=body.language)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        log.exception("TTS synthesis failed")
        raise HTTPException(500, "Synthesis failed — see server logs") from exc

    record_voice_request("synthesize", int((time.perf_counter() - t0) * 1000))
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


@router.post("/audio/correction")
async def record_voice_correction(body: CorrectionRequest) -> dict:
    """Record a voice transcript correction and compute WER/CER.

    Called by the frontend when a user edits a voice-filled transcript before
    sending. The original and corrected texts are compared to compute Word
    Error Rate (WER) and Character Error Rate (CER), which are persisted to
    the audit log as a quality signal for the STT model.

    Returns:
        ``{"wer": float, "cer": float}``
    """
    _require_voice()
    wer_score = _wer(body.original, body.corrected)
    cer_score = _cer(body.original, body.corrected)

    get_audit_store().log(
        event_type=VOICE_CORRECTION,
        user_id="anonymous",
        payload={
            "original": body.original,
            "corrected": body.corrected,
            "language": body.language,
            "wer": wer_score,
            "cer": cer_score,
        },
    )
    return {"wer": wer_score, "cer": cer_score}
