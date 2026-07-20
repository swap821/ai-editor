"""Local/private voice services: STT (faster-whisper) and TTS (piper).

Lazily imports heavy audio dependencies only when a voice endpoint is first
hit. Models auto-download to VOICE_MODELS_DIR on first use. Audio never
leaves the machine.
"""

from __future__ import annotations

import io
import logging
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aios import config

logger = logging.getLogger(__name__)


class VoiceError(Exception):
    """Raised when a voice operation fails."""


@dataclass(frozen=True)
class TranscribeResult:
    text: str
    language: str
    confidence: float


@dataclass(frozen=True)
class SpeakResult:
    audio: bytes
    sample_rate: int
    duration_ms: int


class STTService:
    """Speech-to-text via faster-whisper. Thread-safe, lazily loaded."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "int8",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: object | None = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise VoiceError(
                    "faster-whisper not installed; "
                    "pip install -r requirements-optional.txt"
                ) from e
            device = self._device
            if device == "auto":
                try:
                    import torch

                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"
            logger.info(
                "Loading whisper model %s (device=%s, compute=%s)",
                self._model_size,
                device,
                self._compute_type,
            )
            self._model = WhisperModel(
                self._model_size,
                device=device,
                compute_type=self._compute_type,
            )

    def transcribe(
        self, audio_bytes: bytes, *, language: Optional[str] = None
    ) -> TranscribeResult:
        self._ensure_model()
        buf = io.BytesIO(audio_bytes)
        kwargs: dict = {}
        if language:
            kwargs["language"] = language
        segments, info = self._model.transcribe(buf, **kwargs)  # type: ignore[union-attr]
        text = " ".join(seg.text.strip() for seg in segments)
        return TranscribeResult(
            text=text,
            language=info.language,
            confidence=round(info.language_probability, 3),
        )


class TTSService:
    """Text-to-speech via piper. Thread-safe, lazily loaded."""

    def __init__(
        self,
        model_name: str = "en_US-lessac-medium",
        models_dir: Optional[Path] = None,
    ) -> None:
        self._model_name = model_name
        self._models_dir = models_dir or config.VOICE_MODELS_DIR
        self._voice: object | None = None
        self._lock = threading.Lock()

    def _ensure_voice(self) -> None:
        if self._voice is not None:
            return
        with self._lock:
            if self._voice is not None:
                return
            try:
                from piper import PiperVoice
            except ImportError as e:
                raise VoiceError(
                    "piper-tts not installed; pip install -r requirements-optional.txt"
                ) from e
            self._models_dir.mkdir(parents=True, exist_ok=True)
            model_path = self._models_dir / f"{self._model_name}.onnx"
            if not model_path.exists():
                self._download_model(model_path)
            logger.info("Loading piper voice %s", self._model_name)
            self._voice = PiperVoice.load(str(model_path))

    def _download_model(self, model_path: Path) -> None:
        try:
            from piper.download import find_voice, ensure_voice_exists
        except ImportError:
            raise VoiceError(
                f"Piper model {self._model_name} not found at {model_path} "
                "and auto-download is unavailable."
            )
        logger.info("Downloading piper voice %s ...", self._model_name)
        ensure_voice_exists(
            self._model_name,
            data_dirs=[self._models_dir],
            download_dir=self._models_dir,
        )

    def speak(self, text: str) -> SpeakResult:
        self._ensure_voice()
        buf = io.BytesIO()
        sample_rate = self._voice.config.sample_rate  # type: ignore[union-attr]
        with _wav_writer(buf, sample_rate) as wav:
            self._voice.synthesize(text, wav)  # type: ignore[union-attr]
        audio = buf.getvalue()
        num_samples = (len(audio) - 44) // 2
        duration_ms = int(num_samples / sample_rate * 1000) if sample_rate else 0
        return SpeakResult(
            audio=audio,
            sample_rate=sample_rate,
            duration_ms=duration_ms,
        )

    def available_voices(self) -> list[dict[str, str]]:
        if not self._models_dir.exists():
            return []
        return [
            {"id": p.stem, "name": p.stem.replace("-", " ").replace("_", " ")}
            for p in sorted(self._models_dir.glob("*.onnx"))
        ]


class _wav_writer:
    """Context manager that writes raw PCM int16 mono into a WAV buffer."""

    def __init__(self, buf: io.BytesIO, sample_rate: int) -> None:
        self._buf = buf
        self._sample_rate = sample_rate
        self._data_start = 0

    def __enter__(self) -> "_wav_writer":
        self._buf.write(b"\x00" * 44)
        self._data_start = 44
        return self

    def __exit__(self, *_: object) -> None:
        data_size = self._buf.tell() - self._data_start
        self._buf.seek(0)
        self._buf.write(b"RIFF")
        self._buf.write(struct.pack("<I", 36 + data_size))
        self._buf.write(b"WAVEfmt ")
        self._buf.write(
            struct.pack(
                "<IHHIIHH", 16, 1, 1, self._sample_rate, self._sample_rate * 2, 2, 16
            )
        )
        self._buf.write(b"data")
        self._buf.write(struct.pack("<I", data_size))

    def write(self, data: bytes) -> None:
        self._buf.write(data)
