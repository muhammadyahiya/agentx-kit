"""Tests for the voice module (STT/TTS auto-detect + backends), fully mocked."""
from __future__ import annotations

import sys
import types

import pytest

from agentx.voice import (
    SpeechToText,
    TextToSpeech,
    available_stt_backends,
    available_tts_backends,
)


def test_available_backends_return_dicts():
    stt = available_stt_backends()
    tts = available_tts_backends()
    assert set(stt) == {"faster-whisper", "openai", "whisper"}
    assert set(tts) == {"edge", "openai", "pyttsx3"}
    assert all(isinstance(v, bool) for v in {**stt, **tts}.values())


def test_stt_auto_raises_when_nothing_available(monkeypatch):
    monkeypatch.setattr("agentx.voice.stt.available_stt_backends", lambda: {
        "faster-whisper": False, "openai": False, "whisper": False,
    })
    with pytest.raises(RuntimeError, match="No speech-to-text backend"):
        SpeechToText(backend="auto")


def test_tts_auto_raises_when_nothing_available(monkeypatch):
    monkeypatch.setattr("agentx.voice.tts.available_tts_backends", lambda: {
        "edge": False, "openai": False, "pyttsx3": False,
    })
    with pytest.raises(RuntimeError, match="No text-to-speech backend"):
        TextToSpeech(backend="auto")


def test_stt_auto_prefers_local(monkeypatch):
    monkeypatch.setattr("agentx.voice.stt.available_stt_backends", lambda: {
        "faster-whisper": True, "openai": True, "whisper": True,
    })
    assert SpeechToText(backend="auto").backend == "faster-whisper"


def test_tts_auto_prefers_edge(monkeypatch):
    monkeypatch.setattr("agentx.voice.tts.available_tts_backends", lambda: {
        "edge": True, "openai": True, "pyttsx3": True,
    })
    assert TextToSpeech(backend="auto").backend == "edge"


def test_stt_openai_backend_mocked(monkeypatch, tmp_path):
    # Fake the openai SDK so we exercise the code path without network/keys.
    fake_openai = types.ModuleType("openai")

    class _Resp:
        text = "transcribed text"

    class _Client:
        def __init__(self, *a, **k):
            self.audio = types.SimpleNamespace(
                transcriptions=types.SimpleNamespace(create=lambda **kw: _Resp())
            )

    fake_openai.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    stt = SpeechToText(backend="openai")
    result = stt.transcribe(audio)
    assert result.text == "transcribed text"
    assert result.backend == "openai"


def test_tts_openai_backend_mocked(monkeypatch):
    fake_openai = types.ModuleType("openai")

    class _Resp:
        content = b"MP3BYTES"

    class _Client:
        def __init__(self, *a, **k):
            self.audio = types.SimpleNamespace(
                speech=types.SimpleNamespace(create=lambda **kw: _Resp())
            )

    fake_openai.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    tts = TextToSpeech(backend="openai")
    result = tts.synthesize("hello")
    assert result.audio == b"MP3BYTES"
    assert result.backend == "openai"
    assert result.format == "mp3"


def test_tts_bytes_from_bytes_input_stt_mocked(monkeypatch):
    # STT should accept raw bytes (writes a temp file under the hood).
    fake_openai = types.ModuleType("openai")

    class _Resp:
        text = "from bytes"

    class _Client:
        def __init__(self, *a, **k):
            self.audio = types.SimpleNamespace(
                transcriptions=types.SimpleNamespace(create=lambda **kw: _Resp())
            )

    fake_openai.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    result = SpeechToText(backend="openai").transcribe(b"RIFFfakebytes")
    assert result.text == "from bytes"
