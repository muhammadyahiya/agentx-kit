"""Text-to-Speech with auto-detected backends.

Backends (auto order):
    1. edge-tts   — free, no API key, high quality (uses Microsoft's online voices)
    2. OpenAI TTS — cloud, needs OPENAI_API_KEY
    3. pyttsx3    — fully offline (OS voices), last-resort fallback

Usage::

    from agentx.voice import synthesize
    result = synthesize("Hello there!")
    Path("out.mp3").write_bytes(result.audio)
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["synthesize", "TTSResult", "available_tts_backends", "TextToSpeech"]

# Sensible default voices per backend.
_DEFAULT_VOICES = {
    "edge": "en-US-AriaNeural",
    "openai": "alloy",
    "pyttsx3": "",
}


@dataclass
class TTSResult:
    audio: bytes
    backend: str
    format: str  # "mp3" | "wav"


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def available_tts_backends() -> dict[str, bool]:
    """Report which TTS backends are usable right now."""
    return {
        "edge": _has("edge_tts"),
        "openai": _has("openai") and bool(os.getenv("OPENAI_API_KEY")),
        "pyttsx3": _has("pyttsx3"),
    }


def _resolve_auto() -> str:
    avail = available_tts_backends()
    for name in ("edge", "openai", "pyttsx3"):
        if avail.get(name):
            return name
    raise RuntimeError(
        "No text-to-speech backend available. Install one with:\n"
        "    uv pip install 'agentx-kit[voice]'   # edge-tts (free, no key) + pyttsx3\n"
        "or set OPENAI_API_KEY and `uv pip install openai` for the cloud backend."
    )


class TextToSpeech:
    """Reusable synthesizer."""

    def __init__(self, backend: str = "auto", voice: str | None = None, model: str | None = None):
        self.backend = _resolve_auto() if backend == "auto" else backend
        self.voice = voice
        self.model = model

    def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
        v = voice or self.voice or _DEFAULT_VOICES.get(self.backend, "")
        if self.backend == "edge":
            return self._edge(text, v)
        if self.backend == "openai":
            return self._openai(text, v)
        if self.backend == "pyttsx3":
            return self._pyttsx3(text)
        raise ValueError(f"Unknown TTS backend: {self.backend!r}")

    # ---- backends ----
    def _edge(self, text: str, voice: str) -> TTSResult:
        import edge_tts  # type: ignore

        async def _gen() -> bytes:
            communicate = edge_tts.Communicate(text, voice or _DEFAULT_VOICES["edge"])
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        # Run the async generator on a private loop (safe from sync callers).
        try:
            audio = asyncio.run(_gen())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                audio = loop.run_until_complete(_gen())
            finally:
                loop.close()
        return TTSResult(audio=audio, backend="edge", format="mp3")

    def _openai(self, text: str, voice: str) -> TTSResult:
        from openai import OpenAI  # type: ignore

        client = OpenAI()
        resp = client.audio.speech.create(
            model=self.model or "tts-1", voice=voice or _DEFAULT_VOICES["openai"], input=text
        )
        return TTSResult(audio=resp.content, backend="openai", format="mp3")

    def _pyttsx3(self, text: str) -> TTSResult:
        import pyttsx3  # type: ignore

        engine = pyttsx3.init()
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            engine.save_to_file(text, tmp.name)
            engine.runAndWait()
            audio = Path(tmp.name).read_bytes()
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        return TTSResult(audio=audio, backend="pyttsx3", format="wav")


def synthesize(
    text: str,
    *,
    backend: str = "auto",
    voice: str | None = None,
    model: str | None = None,
) -> TTSResult:
    """Synthesize ``text`` to speech audio bytes. One-shot convenience."""
    return TextToSpeech(backend=backend, voice=voice, model=model).synthesize(text)
