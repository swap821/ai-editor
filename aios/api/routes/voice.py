"""Voice routes — local STT (faster-whisper) and TTS (piper) endpoints.

Extracted from ``aios/api/main.py`` into its own APIRouter module. Keeps the
same lazy-init singleton pattern (guarded by a lock, double-checked) so the
STT/TTS models are only loaded on first use and only one thread builds them.
"""

from __future__ import annotations

import base64
import threading
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aios import config

router = APIRouter()

#: Voice service singletons — built lazily on first voice request.
_stt_service: Optional[Any] = None
_tts_service: Optional[Any] = None
_stt_lock = threading.Lock()
_tts_lock = threading.Lock()


def _get_stt_service():
    """Provide the local STT service, or None when disabled."""
    if not config.VOICE_STT_ENABLED:
        return None
    global _stt_service
    if _stt_service is None:
        with _stt_lock:
            if _stt_service is None:
                from aios.core.voice import STTService
                _stt_service = STTService(
                    model_size=config.VOICE_STT_MODEL,
                    device=config.VOICE_STT_DEVICE,
                    compute_type=config.VOICE_STT_COMPUTE_TYPE,
                )
    return _stt_service


def _get_tts_service():
    """Provide the local TTS service, or None when disabled."""
    if not config.VOICE_TTS_ENABLED:
        return None
    global _tts_service
    if _tts_service is None:
        with _tts_lock:
            if _tts_service is None:
                from aios.core.voice import TTSService
                _tts_service = TTSService(
                    model_name=config.VOICE_TTS_MODEL,
                    models_dir=config.VOICE_MODELS_DIR,
                )
    return _tts_service


class VoiceSpeakRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    voice: Optional[str] = Field(None, description="Piper voice model name override.")
    format: str = Field("wav", description="'wav' for binary stream, 'json' for base64.")


@router.post("/api/v1/voice/transcribe")
async def voice_transcribe(
    request: Request,
    file: UploadFile = File(...),
    stt=Depends(_get_stt_service),
) -> JSONResponse:
    """Transcribe uploaded audio to text using local faster-whisper."""
    if stt is None:
        raise HTTPException(status_code=501, detail="STT not enabled (set AIOS_VOICE_STT=true)")
    audio_bytes = await file.read()
    if len(audio_bytes) > config.VOICE_MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large")
    from aios.core.voice import VoiceError
    try:
        result = stt.transcribe(audio_bytes)
    except VoiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return JSONResponse(content={
        "text": result.text,
        "language": result.language,
        "confidence": result.confidence,
    })


@router.post("/api/v1/voice/speak")
def voice_speak(
    req: VoiceSpeakRequest,
    tts=Depends(_get_tts_service),
) -> Response:
    """Synthesize text to audio using local piper TTS."""
    if tts is None:
        raise HTTPException(status_code=501, detail="TTS not enabled (set AIOS_VOICE_TTS=true)")
    from aios.core.voice import VoiceError
    try:
        result = tts.speak(req.text)
    except VoiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if req.format == "json":
        return JSONResponse(content={
            "audio": base64.b64encode(result.audio).decode(),
            "sample_rate": result.sample_rate,
            "duration_ms": result.duration_ms,
        })
    return Response(content=result.audio, media_type="audio/wav")


@router.get("/api/v1/voice/models")
def voice_models(
    stt=Depends(_get_stt_service),
    tts=Depends(_get_tts_service),
) -> dict:
    """List available and configured voice models."""
    return {
        "stt": {
            "enabled": config.VOICE_STT_ENABLED,
            "model": config.VOICE_STT_MODEL,
            "loaded": stt is not None and stt._model is not None,
            "available_sizes": ["tiny", "base", "small", "medium", "large-v3"],
        },
        "tts": {
            "enabled": config.VOICE_TTS_ENABLED,
            "model": config.VOICE_TTS_MODEL,
            "loaded": tts is not None and tts._voice is not None,
            "available_voices": tts.available_voices() if tts else [],
        },
    }
