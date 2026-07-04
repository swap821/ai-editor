"""Tests for the local voice endpoints (POST /api/v1/voice/transcribe, speak, GET models).

Collaborators are overridden via FastAPI dependency injection — no real
faster-whisper or piper models are loaded.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app, _get_stt_service, _get_tts_service


# ── Fakes ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _FakeTranscribeResult:
    text: str = "hello world"
    language: str = "en"
    confidence: float = 0.95


@dataclass(frozen=True)
class _FakeSpeakResult:
    audio: bytes = b"RIFF" + b"\x00" * 40
    sample_rate: int = 22050
    duration_ms: int = 100


class FakeSTTService:
    _model = "fake"

    def transcribe(self, audio_bytes, *, language=None):
        return _FakeTranscribeResult()


class FakeTTSService:
    _voice = "fake"

    def speak(self, text):
        return _FakeSpeakResult()

    def available_voices(self):
        return [{"id": "en_US-lessac-medium", "name": "en US lessac medium"}]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client_with_voice():
    app.dependency_overrides[_get_stt_service] = lambda: FakeSTTService()
    app.dependency_overrides[_get_tts_service] = lambda: FakeTTSService()
    with TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 12345)) as c:
        yield c
    app.dependency_overrides.pop(_get_stt_service, None)
    app.dependency_overrides.pop(_get_tts_service, None)


@pytest.fixture()
def client_voice_disabled():
    app.dependency_overrides[_get_stt_service] = lambda: None
    app.dependency_overrides[_get_tts_service] = lambda: None
    with TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 12345)) as c:
        yield c
    app.dependency_overrides.pop(_get_stt_service, None)
    app.dependency_overrides.pop(_get_tts_service, None)


# ── STT transcribe tests ─────────────────────────────────────────────────────

def test_transcribe_returns_text(client_with_voice: TestClient) -> None:
    resp = client_with_voice.post(
        "/api/v1/voice/transcribe",
        files={"file": ("audio.wav", b"\x00" * 100, "audio/wav")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "hello world"
    assert data["language"] == "en"
    assert data["confidence"] == 0.95


def test_transcribe_disabled_returns_501(client_voice_disabled: TestClient) -> None:
    resp = client_voice_disabled.post(
        "/api/v1/voice/transcribe",
        files={"file": ("audio.wav", b"\x00" * 10, "audio/wav")},
    )
    assert resp.status_code == 501


def test_transcribe_too_large_returns_413(client_with_voice: TestClient) -> None:
    with patch("aios.api.main.config.VOICE_MAX_AUDIO_BYTES", 50):
        resp = client_with_voice.post(
            "/api/v1/voice/transcribe",
            files={"file": ("audio.wav", b"\x00" * 100, "audio/wav")},
        )
    assert resp.status_code == 413


# ── TTS speak tests ──────────────────────────────────────────────────────────

def test_speak_returns_wav(client_with_voice: TestClient) -> None:
    resp = client_with_voice.post(
        "/api/v1/voice/speak",
        json={"text": "hello there"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content[:4] == b"RIFF"


def test_speak_json_format_returns_base64(client_with_voice: TestClient) -> None:
    resp = client_with_voice.post(
        "/api/v1/voice/speak",
        json={"text": "hello", "format": "json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    decoded = base64.b64decode(data["audio"])
    assert decoded[:4] == b"RIFF"
    assert data["sample_rate"] == 22050
    assert data["duration_ms"] == 100


def test_speak_disabled_returns_501(client_voice_disabled: TestClient) -> None:
    resp = client_voice_disabled.post(
        "/api/v1/voice/speak",
        json={"text": "hello"},
    )
    assert resp.status_code == 501


# ── Models endpoint ──────────────────────────────────────────────────────────

def test_models_endpoint_shows_status(client_with_voice: TestClient) -> None:
    resp = client_with_voice.get("/api/v1/voice/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stt"]["available_sizes"] == ["tiny", "base", "small", "medium", "large-v3"]
    assert data["tts"]["available_voices"] == [{"id": "en_US-lessac-medium", "name": "en US lessac medium"}]


# ── Rate limiting ────────────────────────────────────────────────────────────

def test_voice_endpoints_rate_limited(client_with_voice: TestClient) -> None:
    from aios.api.main import _RATE_LIMIT_ENDPOINTS
    assert "/api/v1/voice/transcribe" in _RATE_LIMIT_ENDPOINTS
    assert "/api/v1/voice/speak" in _RATE_LIMIT_ENDPOINTS
    assert _RATE_LIMIT_ENDPOINTS["/api/v1/voice/transcribe"] == 30
    assert _RATE_LIMIT_ENDPOINTS["/api/v1/voice/speak"] == 60
