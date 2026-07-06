"""Characterization tests for ``aios/core/voice.py`` (local STT/TTS wrappers).

The heavy optional dependencies (``faster_whisper``, ``piper``) are faked by
injecting stub modules into ``sys.modules`` — no model is downloaded or
loaded, no audio device is touched, and there are no network, shell, or
file side effects outside ``tmp_path``. Covered behaviours: lazy
double-checked model loading, ImportError → VoiceError guards, transcription
result shaping, WAV synthesis framing/duration math, the auto-download
fallback, and voice discovery.
"""
from __future__ import annotations

import struct
import sys
import types
from pathlib import Path

import pytest

from aios import config
from aios.core.voice import (
    STTService,
    SpeakResult,
    TTSService,
    TranscribeResult,
    VoiceError,
)


class _FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeInfo:
    language = "en"
    language_probability = 0.98765


class _FakeWhisperModel:
    created: list["_FakeWhisperModel"] = []

    def __init__(self, model_size, device=None, compute_type=None) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.calls: list[dict] = []
        _FakeWhisperModel.created.append(self)

    def transcribe(self, buf, **kwargs):
        self.calls.append(kwargs)
        return iter([_FakeSegment(" hello "), _FakeSegment("world")]), _FakeInfo()


@pytest.fixture()
def fake_faster_whisper(monkeypatch):
    _FakeWhisperModel.created = []
    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = _FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    return mod


def test_stt_transcribe_joins_segments_and_rounds_confidence(fake_faster_whisper):
    svc = STTService(model_size="base", device="cpu", compute_type="int8")
    result = svc.transcribe(b"RIFFfakeaudio")
    assert result == TranscribeResult(text="hello world", language="en", confidence=0.988)
    model = _FakeWhisperModel.created[0]
    assert (model.model_size, model.device, model.compute_type) == ("base", "cpu", "int8")


def test_stt_language_hint_forwarded_and_model_loaded_once(fake_faster_whisper):
    svc = STTService(device="cpu")
    svc.transcribe(b"a", language="de")
    svc.transcribe(b"b")
    assert len(_FakeWhisperModel.created) == 1, "double-checked lazy load must build once"
    assert _FakeWhisperModel.created[0].calls[0] == {"language": "de"}
    assert _FakeWhisperModel.created[0].calls[1] == {}


def test_stt_auto_device_resolves_to_concrete_device(fake_faster_whisper):
    svc = STTService(device="auto")
    svc.transcribe(b"x")
    # torch is installed in this venv, so "auto" must resolve via the torch
    # branch to a concrete device string, never stay "auto".
    assert _FakeWhisperModel.created[0].device in {"cpu", "cuda"}


def test_stt_missing_dependency_raises_voice_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    svc = STTService()
    with pytest.raises(VoiceError, match="faster-whisper not installed"):
        svc.transcribe(b"x")


class _FakeVoiceConfig:
    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate


class _FakePiperVoice:
    sample_rate = 16000
    loaded_paths: list[str] = []

    def __init__(self, path: str) -> None:
        self.config = _FakeVoiceConfig(type(self).sample_rate)

    @classmethod
    def load(cls, path: str) -> "_FakePiperVoice":
        cls.loaded_paths.append(path)
        return cls(path)

    def synthesize(self, text: str, wav) -> None:
        wav.write(b"\x01\x00" * 100)  # 100 int16 mono samples


@pytest.fixture()
def fake_piper(monkeypatch):
    _FakePiperVoice.loaded_paths = []
    _FakePiperVoice.sample_rate = 16000
    mod = types.ModuleType("piper")
    mod.PiperVoice = _FakePiperVoice
    monkeypatch.setitem(sys.modules, "piper", mod)
    return mod


def _touch_model(models_dir: Path, name: str) -> Path:
    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / f"{name}.onnx"
    path.write_bytes(b"onnx")
    return path


def test_tts_speak_builds_wav_header_and_duration(fake_piper, tmp_path):
    _touch_model(tmp_path, "en_US-lessac-medium")
    svc = TTSService(model_name="en_US-lessac-medium", models_dir=tmp_path)
    result = svc.speak("hello")
    assert isinstance(result, SpeakResult)
    assert result.audio[:4] == b"RIFF"
    assert result.audio[8:16] == b"WAVEfmt "
    assert result.sample_rate == 16000
    # 100 int16 samples at 16 kHz -> int(100 / 16000 * 1000) == 6 ms
    assert result.duration_ms == 6
    data_size = struct.unpack("<I", result.audio[40:44])[0]
    assert data_size == 200
    svc.speak("again")
    assert len(_FakePiperVoice.loaded_paths) == 1, "voice must load lazily once"


def test_tts_zero_sample_rate_reports_zero_duration(fake_piper, tmp_path):
    _FakePiperVoice.sample_rate = 0
    _touch_model(tmp_path, "m")
    svc = TTSService(model_name="m", models_dir=tmp_path)
    assert svc.speak("x").duration_ms == 0


def test_tts_download_fallback_invoked_when_model_missing(fake_piper, tmp_path, monkeypatch):
    calls: dict = {}

    def fake_ensure(name, data_dirs, download_dir):
        calls["name"] = name
        _touch_model(Path(download_dir), name)

    dl = types.ModuleType("piper.download")
    dl.find_voice = lambda *a, **k: None
    dl.ensure_voice_exists = fake_ensure
    monkeypatch.setitem(sys.modules, "piper.download", dl)
    svc = TTSService(model_name="dl-voice", models_dir=tmp_path / "models")
    result = svc.speak("hi")
    assert calls["name"] == "dl-voice"
    assert result.audio[:4] == b"RIFF"


def test_tts_download_unavailable_raises_voice_error(fake_piper, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "piper.download", None)
    svc = TTSService(model_name="ghost-voice", models_dir=tmp_path)
    with pytest.raises(VoiceError, match="auto-download is unavailable"):
        svc.speak("x")


def test_tts_missing_dependency_raises_voice_error(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "piper", None)
    svc = TTSService(models_dir=tmp_path)
    with pytest.raises(VoiceError, match="piper-tts not installed"):
        svc.speak("x")


def test_tts_default_models_dir_comes_from_config():
    svc = TTSService()
    assert svc._models_dir == config.VOICE_MODELS_DIR


def test_available_voices_empty_when_dir_missing(tmp_path):
    svc = TTSService(models_dir=tmp_path / "does-not-exist")
    assert svc.available_voices() == []


def test_available_voices_lists_sorted_onnx_stems(tmp_path):
    _touch_model(tmp_path, "b_voice-two")
    _touch_model(tmp_path, "a_voice-one")
    svc = TTSService(models_dir=tmp_path)
    voices = svc.available_voices()
    assert [v["id"] for v in voices] == ["a_voice-one", "b_voice-two"]
    assert voices[0]["name"] == "a voice one"
