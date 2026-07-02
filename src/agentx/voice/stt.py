"""Speech-to-Text with auto-detected backends.

Backends (auto order):
    1. faster-whisper  — local, no API key (CTranslate2; downloads model on first use)
    2. OpenAI Whisper   — cloud, needs OPENAI_API_KEY
    3. openai-whisper   — local reference implementation (heavier), optional

Usage::

    from agentx.voice import transcribe
    result = transcribe("hello.wav")          # path or raw bytes
    print(result.text, result.backend)
"""
from __future__ import annotations

import importlib.util
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["transcribe", "STTResult", "available_stt_backends", "SpeechToText"]


@dataclass
class STTResult:
    text: str
    backend: str
    language: str | None = None


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def available_stt_backends() -> dict[str, bool]:
    """Report which STT backends are usable right now."""
    return {
        "faster-whisper": _has("faster_whisper"),
        "openai": _has("openai") and bool(os.getenv("OPENAI_API_KEY")),
        "whisper": _has("whisper"),
    }


def _resolve_auto() -> str:
    avail = available_stt_backends()
    for name in ("faster-whisper", "openai", "whisper"):
        if avail.get(name):
            return name
    raise RuntimeError(
        "No speech-to-text backend available. Install one with:\n"
        "    uv pip install 'agentx-kit[voice]'   # faster-whisper (local, no key)\n"
        "or set OPENAI_API_KEY and `uv pip install openai` for the cloud backend."
    )


def _as_path(audio: bytes | str | Path) -> tuple[Path, bool]:
    """Return (path, is_temp). Writes bytes to a temp .wav if needed."""
    if isinstance(audio, (str, Path)):
        return Path(audio), False
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.write(audio)
    tmp.close()
    return Path(tmp.name), True


class SpeechToText:
    """Reusable transcriber (caches a loaded local model between calls)."""

    def __init__(self, backend: str = "auto", model: str | None = None, device: str = "auto"):
        self.backend = _resolve_auto() if backend == "auto" else backend
        self.model = model
        self.device = device
        self._model_obj = None  # lazily loaded local model

    def transcribe(self, audio: bytes | str | Path, language: str = "en") -> STTResult:
        if self.backend == "faster-whisper":
            return self._faster_whisper(audio, language)
        if self.backend == "openai":
            return self._openai(audio, language)
        if self.backend == "whisper":
            return self._whisper(audio, language)
        raise ValueError(f"Unknown STT backend: {self.backend!r}")

    # ---- backends ----
    def _faster_whisper(self, audio, language: str) -> STTResult:
        from faster_whisper import WhisperModel  # type: ignore

        if self._model_obj is None:
            device = self.device if self.device != "auto" else "cpu"
            self._model_obj = WhisperModel(
                self.model or "base", device=device, compute_type="int8"
            )
        path, is_temp = _as_path(audio)
        try:
            segments, info = self._model_obj.transcribe(str(path), language=language or None)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return STTResult(text=text, backend="faster-whisper", language=getattr(info, "language", language))
        finally:
            if is_temp:
                path.unlink(missing_ok=True)

    def _openai(self, audio, language: str) -> STTResult:
        from openai import OpenAI  # type: ignore

        client = OpenAI()
        path, is_temp = _as_path(audio)
        try:
            with open(path, "rb") as fh:
                resp = client.audio.transcriptions.create(
                    model=self.model or "whisper-1", file=fh, language=language or None
                )
            return STTResult(text=resp.text, backend="openai", language=language)
        finally:
            if is_temp:
                path.unlink(missing_ok=True)

    def _whisper(self, audio, language: str) -> STTResult:
        import whisper  # type: ignore

        if self._model_obj is None:
            self._model_obj = whisper.load_model(self.model or "base")
        path, is_temp = _as_path(audio)
        try:
            result = self._model_obj.transcribe(str(path), language=language or None)
            return STTResult(text=str(result.get("text", "")).strip(), backend="whisper",
                             language=result.get("language", language))
        finally:
            if is_temp:
                path.unlink(missing_ok=True)


def transcribe(
    audio: bytes | str | Path,
    *,
    backend: str = "auto",
    model: str | None = None,
    language: str = "en",
) -> STTResult:
    """Transcribe ``audio`` (a path or raw bytes) to text. One-shot convenience."""
    return SpeechToText(backend=backend, model=model).transcribe(audio, language=language)
