"""Audio proxy routes for the api-gateway pod.

Forwards /audio/* requests to the voice-service container so that the gateway
does not need faster-whisper or piper-tts installed. The voice-service owns
all STT/TTS logic; the gateway is a pure HTTP proxy for these endpoints.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)
router = APIRouter()

_VOICE_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0)


def _require_voice() -> None:
    if not settings.voice_enabled:
        raise HTTPException(404, "Voice I/O is disabled — set VOICE_ENABLED=true in .env")


@router.post("/audio/transcribe")
async def transcribe_proxy(
    file: UploadFile = File(...),
    language: str = Form("en"),
    user_id: str = Form("anonymous"),
) -> dict:
    """Forward audio upload to voice-service for STT transcription."""
    _require_voice()
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    async with httpx.AsyncClient(timeout=_VOICE_TIMEOUT) as client:
        try:
            r = await client.post(
                f"{settings.voice_service_url}/audio/transcribe",
                files={"file": (file.filename or "audio", audio_bytes, file.content_type or "audio/webm")},
                data={"language": language, "user_id": user_id},
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            log.error(
                "Voice service transcribe failed %d: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise HTTPException(
                exc.response.status_code, "Transcription failed — see voice-service logs"
            ) from exc
        except Exception as exc:
            log.exception("Voice service unreachable during transcribe")
            raise HTTPException(503, "Voice service unavailable") from exc


@router.post("/audio/synthesize")
async def synthesize_proxy(request: Request) -> Response:
    """Forward TTS synthesis request to voice-service; returns audio/wav."""
    _require_voice()
    body = await request.body()

    async with httpx.AsyncClient(timeout=_VOICE_TIMEOUT) as client:
        try:
            r = await client.post(
                f"{settings.voice_service_url}/audio/synthesize",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            return Response(content=r.content, media_type="audio/wav")
        except httpx.HTTPStatusError as exc:
            log.error(
                "Voice service synthesize failed %d: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise HTTPException(
                exc.response.status_code, "Synthesis failed — see voice-service logs"
            ) from exc
        except Exception as exc:
            log.exception("Voice service unreachable during synthesize")
            raise HTTPException(503, "Voice service unavailable") from exc


@router.post("/audio/correction")
async def correction_proxy(request: Request) -> dict:
    """Forward WER correction report to voice-service for audit logging."""
    _require_voice()
    body = await request.body()

    async with httpx.AsyncClient(timeout=_VOICE_TIMEOUT) as client:
        try:
            r = await client.post(
                f"{settings.voice_service_url}/audio/correction",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            log.error(
                "Voice service correction failed %d: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise HTTPException(
                exc.response.status_code, "Correction logging failed — see voice-service logs"
            ) from exc
        except Exception as exc:
            log.exception("Voice service unreachable during correction")
            raise HTTPException(503, "Voice service unavailable") from exc
