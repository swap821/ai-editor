"""Characterization tests for ``aios/api/routes/voice.py``.

Exercises the voice endpoints through ``TestClient`` with the module's
lazy singletons reset per test. The optional STT/TTS dependencies are
absent-or-faked (``sys.modules`` stubs / dependency overrides), so no
model is ever loaded and there are no network, shell, or real-file side
effects — conftest.py already isolates ``AIOS_DATA_DIR`` into a temp dir.
Covered: 501 gating when disabled, real singleton construction when
enabled, ImportError → VoiceError → 503 mapping, 413 oversize guard,
wav/json response formats, and the models-introspection endpoint.
"""
from __future__ import annotations

import base64
import sys
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import aios.api.routes.voice as voice_routes
from aios import config
from aios.api.main import app
from aios.core.voice import SpeakResult


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    # Reset the module-level singletons so each test exercises the lazy
    # build path deterministically; monkeypatch restores them afterwards.
    monkeypatch.setattr(voice_routes, "_stt_service", None)
    monkeypatch.setattr(voice_routes, "_tts_service", None)
    with TestClient(
        app, raise_server_exceptions=False, client=("127.0.0.1", 12345)
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class _FakeTTS:
    def __init__(self) -> None:
        self._voice = object()

    def speak(self, text: str) -> SpeakResult:
        return SpeakResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x01\x02",
            sample_rate=8000,
            duration_ms=42,
        )

    def available_voices(self) -> list[dict[str, str]]:
        return [{"id": "v", "name": "v"}]


def _wav_upload(payload: bytes = b"xx"):
    return {"file": ("clip.wav", payload, "audio/wav")}


def test_transcribe_501_when_stt_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "VOICE_STT_ENABLED", False)
    response = client.post("/api/v1/voice/transcribe", files=_wav_upload())
    assert response.status_code == 501
    assert "STT not enabled" in response.json()["detail"]


def test_transcribe_builds_singleton_then_503_without_dependency(client, monkeypatch):
    monkeypatch.setattr(config, "VOICE_STT_ENABLED", True)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    response = client.post("/api/v1/voice/transcribe", files=_wav_upload())
    assert response.status_code == 503
    assert "faster-whisper" in response.json()["detail"]
    assert voice_routes._stt_service is not None, "real singleton must be built"
    # Second call takes the cached-singleton early-return branch.
    second = client.post("/api/v1/voice/transcribe", files=_wav_upload())
    assert second.status_code == 503


def test_transcribe_413_when_audio_too_large(client, monkeypatch):
    monkeypatch.setattr(config, "VOICE_STT_ENABLED", True)
    monkeypatch.setattr(config, "VOICE_MAX_AUDIO_BYTES", 4)
    response = client.post("/api/v1/voice/transcribe", files=_wav_upload(b"way too large"))
    assert response.status_code == 413


def test_speak_501_when_tts_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "VOICE_TTS_ENABLED", False)
    response = client.post("/api/v1/voice/speak", json={"text": "hi"})
    assert response.status_code == 501
    assert "TTS not enabled" in response.json()["detail"]


def test_speak_builds_singleton_then_503_without_dependency(client, monkeypatch):
    monkeypatch.setattr(config, "VOICE_TTS_ENABLED", True)
    monkeypatch.setitem(sys.modules, "piper", None)
    response = client.post("/api/v1/voice/speak", json={"text": "hi"})
    assert response.status_code == 503
    assert "piper-tts" in response.json()["detail"]
    assert voice_routes._tts_service is not None, "real singleton must be built"


def test_speak_wav_and_json_formats_with_fake_engine(client):
    app.dependency_overrides[voice_routes._get_tts_service] = lambda: _FakeTTS()
    wav = client.post("/api/v1/voice/speak", json={"text": "hi", "format": "wav"})
    assert wav.status_code == 200
    assert wav.headers["content-type"].startswith("audio/wav")
    assert wav.content[:4] == b"RIFF"
    as_json = client.post("/api/v1/voice/speak", json={"text": "hi", "format": "json"})
    assert as_json.status_code == 200
    body = as_json.json()
    assert base64.b64decode(body["audio"])[:4] == b"RIFF"
    assert body["sample_rate"] == 8000
    assert body["duration_ms"] == 42


def test_speak_rejects_overlong_text(client):
    app.dependency_overrides[voice_routes._get_tts_service] = lambda: _FakeTTS()
    response = client.post("/api/v1/voice/speak", json={"text": "x" * 5001})
    assert response.status_code == 422


def test_voice_models_reports_disabled_state(client, monkeypatch):
    monkeypatch.setattr(config, "VOICE_STT_ENABLED", False)
    monkeypatch.setattr(config, "VOICE_TTS_ENABLED", False)
    body = client.get("/api/v1/voice/models").json()
    assert body["stt"]["enabled"] is False
    assert body["stt"]["loaded"] is False
    assert body["tts"]["available_voices"] == []


def test_voice_models_reports_loaded_fakes(client):
    class _FakeSTT:
        _model = object()

    app.dependency_overrides[voice_routes._get_stt_service] = lambda: _FakeSTT()
    app.dependency_overrides[voice_routes._get_tts_service] = lambda: _FakeTTS()
    body = client.get("/api/v1/voice/models").json()
    assert body["stt"]["loaded"] is True
    assert body["tts"]["loaded"] is True
    assert body["tts"]["available_voices"] == [{"id": "v", "name": "v"}]
